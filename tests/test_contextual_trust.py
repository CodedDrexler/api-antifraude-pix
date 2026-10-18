"""Contrast the same request with relationship evidence, independent risk and missing data."""

from dataclasses import replace

import pytest

from src.constants import ContextualTrustPolicy, Policy
from src.controllers.account_untrust import UntrustHistory, assess_untrust
from src.controllers.decision_engine import DecisionEngine
from src.risk.contextual_trust import median_twice
from src.risk.types import History, RuleMatch
from src.schemas.pix import PixTransactionCreate

FAMILIAR = History(
    0,
    0,
    20,
    True,
    True,
    10,
    100_000,
    payer_reference_values=(10_000,) * 17 + (200_000,) * 3,
    relationship_reference_values=(200_000,) * 3,
    relationship_received_days=2,
)


def evaluate(payload, history=FAMILIAR, amount=200_000, policy=None):
    payload["amount"] = amount
    return DecisionEngine(policy or Policy()).evaluate(PixTransactionCreate.model_validate(payload), history)


def test_familiar_amount_attenuates_only_profile_and_preserves_original_evidence(payload):
    status, evidence = evaluate(payload)
    assert status == "approved"
    trust = evidence["contextual_trust"]
    assert trust["applied"] is True
    assert (trust["profile_points_before"], trust["profile_points_after"]) == (80, 0)
    assert trust["payer_median_twice_cents"] == 20_000
    assert trust["relationship_median_twice_cents"] == 400_000
    rule = evidence["triggered_rules"][0]
    assert rule["code"] == "amount_above_customer_profile"
    assert rule["points_before_context"] == 80 and rule["contribution"] == 0
    assert evidence["decision_causes"] == []


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"payer_reference_values": (10_000,) * 4}, "insufficient_payer_history"),
        ({"relationship_reference_values": (200_000,) * 2}, "insufficient_relationship_history"),
        ({"relationship_received_days": 1}, "insufficient_received_days"),
        ({"relationship_reference_values": ()}, "insufficient_relationship_history"),
        ({"relationship_reference_values": (0, 200_000, 200_000)}, "invalid_reference"),
    ],
)
def test_insufficient_or_invalid_evidence_cannot_grant_attenuation(payload, changes, reason):
    status, evidence = evaluate(payload, replace(FAMILIAR, **changes))
    assert status == "two_factor_required"
    assert evidence["risk_score"] == 80
    assert evidence["contextual_trust"]["reason"] == reason
    assert evidence["contextual_trust"]["applied"] is False


@pytest.mark.parametrize(
    "amount,applied", [(99_999, False), (100_000, True), (400_000, True), (400_001, False)]
)
def test_relationship_compatibility_boundaries_are_inclusive_and_exact(payload, amount, applied):
    _, evidence = evaluate(payload, amount=amount)
    assert evidence["contextual_trust"]["applied"] is applied


@pytest.mark.parametrize(
    "changes,rule,score,status",
    [
        ({"known_device": False}, "unfamiliar_device", 20, "approved"),
        ({"recent_count": 5}, "velocity_above_limit", 80, "rejected"),
        ({"recent_amount": 2_800_000}, "accumulated_amount_above_limit", 80, "rejected"),
        ({"device_other_owners": 2}, "shared_device", 30, "two_factor_required"),
    ],
)
def test_familiar_relationship_never_neutralizes_independent_controls(payload, changes, rule, score, status):
    result, evidence = evaluate(payload, replace(FAMILIAR, **changes))
    assert result == status and evidence["risk_score"] == score
    assert evidence["contextual_trust"]["applied"] is True
    if status != "approved":
        assert rule in {cause["rule_id"] for cause in evidence["decision_causes"]}
    assert next(r for r in evidence["triggered_rules"] if r["code"] == rule)["contribution"] > 0


def test_microtransactions_and_disabled_policy_cannot_make_large_amount_familiar(payload):
    _, incompatible = evaluate(payload, replace(FAMILIAR, relationship_reference_values=(1,) * 3))
    assert incompatible["contextual_trust"]["reason"] == "incompatible_amount"
    policy = replace(Policy(), contextual_trust=replace(ContextualTrustPolicy(), enabled=False))
    _, disabled = evaluate(payload, policy=policy)
    assert disabled["risk_score"] == 80 and disabled["contextual_trust"]["applied"] is False


def test_half_cent_medians_remain_integer_and_pending_bootstrap_does_not_grant_trust(payload):
    assert median_twice((101, 102)) == 203
    history = History(0, 0, 0, False, False, 1, 10_000, profile_basis="initial_pending_attempt")
    _, evidence = evaluate(payload, history)
    assert evidence["contextual_trust"]["eligible"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"enabled": 1},
        {"history_size": 2},
        {"minimum_received_days": 4},
        {"minimum_ratio_percent": 101},
        {"maximum_ratio_percent": 99},
        {"history_size": True},
    ],
)
def test_invalid_contextual_policy_fails_before_accepting_requests(changes):
    with pytest.raises(ValueError):
        replace(ContextualTrustPolicy(), **changes)


def test_destination_evidence_intervenes_without_accusing_the_sender(payload):
    payload["amount"] = 50_000
    payload["source"]["channel"] = "internet_banking"
    payload["source_account"]["opening_date"] = payload["transaction_date"]
    payload["destination_account"]["opening_date"] = payload["transaction_date"]
    history = History(0, 0, 3, False, True, 3, 60_000)
    status, evidence = DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload), history
    )
    assert status == "two_factor_required" and evidence["risk_score"] == 40
    subjects = {r["code"]: r["subject"] for r in evidence["triggered_rules"]}
    assert subjects["new_destination_account"] == "destination"
    assert subjects["unfamiliar_destination"] == "relationship"
    _, own, _ = assess_untrust(status, evidence, UntrustHistory(), Policy().untrust)
    assert own["increment"] == 0 and own["eligible_rules"] == []


def test_mixed_sender_and_destination_evidence_preserves_only_own_increment(payload):
    status, evidence = evaluate(
        payload,
        replace(
            FAMILIAR,
            known_device=False,
            known_destination=False,
            profile_amount=600_000,
            relationship_reference_values=(),
        ),
        amount=50_000,
    )
    _, own, _ = assess_untrust(status, evidence, UntrustHistory(), Policy().untrust)
    assert evidence["risk_score"] == 35
    assert own["eligible_rules"] == ["unfamiliar_device"]
    assert own["increment"] == 5


def test_hypothetical_critical_destination_detector_cannot_create_own_risk(payload, monkeypatch):
    # Test-only injection: no blacklist, external reputation or new endpoint field is introduced.
    monkeypatch.setattr(
        "src.controllers.decision_engine.evaluate_rules",
        lambda context: iter([RuleMatch("new_destination_account", "test-only-mark", "test-only", True)]),
    )
    status, evidence = evaluate(payload)
    assert status == "rejected" and evidence["decision_source"] == "hard_limit"
    assert {cause["subject"] for cause in evidence["decision_causes"]} == {"destination"}
    _, own, _ = assess_untrust(status, evidence, UntrustHistory(), Policy().untrust)
    assert own["increment"] == 0
