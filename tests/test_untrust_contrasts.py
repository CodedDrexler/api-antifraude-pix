"""Paired outcomes: change one cause, assert both the decision and its evidence."""

from copy import deepcopy
from dataclasses import replace

import pytest

from src.constants import Policy
from src.controllers.account_untrust import UntrustHistory, assess_untrust
from src.controllers.decision_engine import DecisionEngine
from src.gnn.service import combine_graph_risk
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate

NORMAL = History(0, 0, 3, True, True, 3, 60_000)


def assess(payload, history=NORMAL, accumulated=UntrustHistory(), policy=Policy()):
    status, baseline = DecisionEngine(policy).evaluate(PixTransactionCreate.model_validate(payload), history)
    final, untrust, notice = assess_untrust(
        status, baseline, accumulated, policy.untrust, policy.scoring.two_factor_threshold
    )
    return final, baseline, untrust, notice


@pytest.mark.parametrize(
    "left,right,amount,expected_scores,expected_statuses,expected_increments,changed_rule",
    [
        pytest.param(
            NORMAL,
            replace(NORMAL, known_destination=False),
            100_000,
            (80, 95),
            ("two_factor_required", "rejected"),
            (20, 20),
            "unfamiliar_destination",
            id="same-pix-profile-risk-with-or-without-second-factor",
        ),
        pytest.param(
            NORMAL,
            replace(NORMAL, profile_amount=30_000),
            50_000,
            (0, 80),
            ("approved", "two_factor_required"),
            (0, 20),
            "amount_above_customer_profile",
            id="same-amount-different-customer-reference",
        ),
        pytest.param(
            replace(NORMAL, known_device=False),
            replace(NORMAL, known_device=False, known_destination=False),
            50_000,
            (20, 35),
            ("approved", "two_factor_required"),
            (0, 5),
            "unfamiliar_destination",
            id="new-device-alone-versus-new-device-and-recipient",
        ),
        pytest.param(
            replace(NORMAL, device_other_owners=1),
            replace(NORMAL, device_other_owners=2),
            1000,
            (0, 30),
            ("approved", "two_factor_required"),
            (0, 8),
            "shared_device",
            id="shared-family-device-versus-third-owner",
        ),
    ],
)
def test_same_request_different_context_has_a_specific_cause(
    payload, left, right, amount, expected_scores, expected_statuses, expected_increments, changed_rule
):
    payload["amount"] = amount
    original = deepcopy(payload)
    results = [assess(payload, history) for history in (left, right)]
    assert tuple(row[0] for row in results) == expected_statuses
    assert tuple(row[1]["risk_score"] for row in results) == expected_scores
    assert tuple(row[2]["increment"] for row in results) == expected_increments
    rules = [{r["code"] for r in row[1]["triggered_rules"]} for row in results]
    assert rules[1] - rules[0] == {changed_rule}
    assert not rules[0] - rules[1]
    assert payload == original


def test_identical_clean_pix_changes_only_because_of_accumulated_evidence(payload):
    low = assess(payload, accumulated=UntrustHistory(39, 2))
    high = assess(payload, accumulated=UntrustHistory(40, 2))
    assert (low[0], high[0]) == ("approved", "two_factor_required")
    assert low[1] == high[1]  # No invented transaction risk to explain the escalation.
    assert low[1]["risk_score"] == 0
    assert low[2]["increment"] == high[2]["increment"] == 0
    assert low[2]["decision_override"] is False
    assert high[2]["decision_override"] is True


def test_correlated_device_signals_accumulate_only_the_capped_contribution(payload):
    payload["amount"] = 50_000
    history = replace(NORMAL, known_device=False, device_other_owners=2, payer_other_devices=2)
    _, evidence, untrust, _ = assess(payload, history)
    assert evidence["raw_score"] == 70
    assert evidence["risk_score"] == 40
    assert untrust["increment"] == 10
    assert sum(rule["contribution"] for rule in evidence["triggered_rules"]) == 40


@pytest.mark.parametrize(
    "rule", ["first_transaction", "insufficient_amount_history", "possible_duplicate_payment"]
)
def test_reclassifying_a_noneligible_rule_does_not_create_suspicion(payload, rule):
    policy = Policy()
    policy = replace(
        policy,
        scoring=replace(
            policy.scoring, rule_factors=replace(policy.scoring.rule_factors, **{rule: "device"})
        ),
    )
    if rule == "possible_duplicate_payment":
        history = replace(NORMAL, duplicate_transaction_id="previous", duplicate_elapsed_seconds=1)
    else:
        history = History(0, 0, 0, False, False, registered_count=int(rule != "first_transaction"))
    _, metadata, untrust, _ = assess(payload, history, policy=policy)
    assert metadata["reasons"] == [rule]
    assert metadata["risk_score"] == 30
    assert untrust["increment"] == 0
    assert untrust["eligible_rules"] == []


def test_reclassifying_real_profile_evidence_does_not_erase_suspicion(payload):
    payload["amount"] = 100_000
    normal = assess(payload)
    policy = Policy()
    policy = replace(
        policy,
        scoring=replace(
            policy.scoring,
            rule_factors=replace(policy.scoring.rule_factors, amount_above_customer_profile="exposure"),
        ),
    )
    regrouped = assess(payload, policy=policy)
    assert normal[1]["risk_score"] == regrouped[1]["risk_score"] == 80
    assert normal[2]["increment"] == regrouped[2]["increment"] == 20
    assert regrouped[2]["eligible_rules"] == ["amount_above_customer_profile"]


@pytest.mark.parametrize("mode", ["off", "shadow", "contribute"])
def test_graph_risk_and_restriction_do_not_feed_the_next_own_increment(payload, mode):
    payload["amount"] = 50_000
    history = replace(NORMAL, known_device=False)
    status, baseline = DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload), history
    )
    status, enriched = combine_graph_risk(
        status,
        baseline,
        {
            "mode": mode,
            "status": "scored",
            "proposed_points": 20,
            "gnn_score": 95,
            "threshold": 80,
        },
    )
    assert enriched["risk_score"] == (40 if mode == "contribute" else 20)
    final, untrust, _ = assess_untrust(status, baseline, UntrustHistory(40, 2), Policy().untrust)
    assert final == "two_factor_required"
    assert untrust["increment"] == 0  # A weak device signal cannot inherit graph/account points.
    assert untrust["score"] == 40


@pytest.mark.parametrize("field", ["id", "ip", "geolocation", "equivalent_timezone"])
def test_irrelevant_request_changes_preserve_decision_and_suspicion(payload, field):
    original = assess(payload, accumulated=UntrustHistory(40, 2))
    changed = deepcopy(payload)
    if field == "id":
        changed["id"] = "another-request-id"
    elif field == "ip":
        changed["source"]["ip"] = "203.0.113.17"
    elif field == "geolocation":
        changed["source"]["geolocation"] = {"latitude": 0, "longitude": 0}
    else:
        changed["transaction_date"] = "2026-10-17T11:00:00-03:00"
    assert assess(changed, accumulated=UntrustHistory(40, 2)) == original
