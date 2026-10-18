"""Weighted contributions, factor caps and reconstruction of the decision evidence."""

import json
from dataclasses import asdict, replace

import pytest

from src.constants import FactorWeights, GroupCaps, Policy, RuleFactors, ScoringPolicy
from src.controllers.decision_engine import DecisionEngine
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate


def evaluate(payload, scoring, history=None):
    return DecisionEngine(replace(Policy(), scoring=scoring)).evaluate(
        PixTransactionCreate.model_validate(payload), history or History(0, 0, 0, False, False, 1, 1000)
    )


def test_fractional_factor_weight_is_truncated_before_decision_and_explained(payload):
    payload["amount"] = 5000
    scoring = replace(ScoringPolicy(), factor_weights=replace(FactorWeights(), profile=37))
    status, metadata = evaluate(payload, scoring)
    assert status == "approved"
    assert metadata["risk_score"] == 29  # 80 * 37% = 29.6; rounding up would incorrectly require 2FA.
    assert next(f for f in metadata["risk_factors"] if f["name"] == "profile") == {
        "name": "profile",
        "label": "Perfil de valores",
        "raw_score": 80,
        "weighted_score": 29,
        "score": 29,
        "cap": 80,
        "weight": 37,
        "rules": ["amount_above_customer_profile"],
        "hard_limits": [],
    }
    assert metadata["triggered_rules"][0]["risk_factor"] == "profile"
    assert metadata["triggered_rules"][0]["weighted_points"] == 29


def test_increasing_factor_weights_can_block_a_transaction(payload):
    payload["amount"] = 5000
    payload["source_account"]["opening_date"] = payload["transaction_date"]
    scoring = replace(
        ScoringPolicy(),
        factor_weights=replace(FactorWeights(), profile=100, account=200),
        group_caps=replace(GroupCaps(), account=30),
    )
    status, metadata = evaluate(payload, scoring)
    assert status == "rejected"
    assert metadata["risk_score"] == 100
    assert metadata["hard_limits"] == []


def test_rule_remapping_changes_factor_cap_and_rejection_guard(payload):
    payload["amount"] = 5000
    payload["source_account"]["opening_date"] = payload["transaction_date"]
    scoring = replace(
        ScoringPolicy(),
        rejection_threshold=40,
        rule_factors=replace(RuleFactors(), new_source_account="profile"),
    )
    status, metadata = evaluate(payload, scoring)
    assert status == "two_factor_required"
    assert metadata["risk_score"] == 80
    assert metadata["risk_group_count"] == 1
    assert {f["name"] for f in metadata["risk_factors"]} == {"profile"}
    assert all(r["risk_factor"] == "profile" for r in metadata["triggered_rules"])


@pytest.mark.parametrize(
    "factor,history_changes,young_destination,raw,points,contributions,expected",
    [
        pytest.param(
            "counterparty",
            {"known_destination": False},
            True,
            30,
            25,
            {"new_destination_account": 15, "unfamiliar_destination": 10},
            "approved",
            id="counterparty-tie-break-consumes-cap-25",
        ),
        pytest.param(
            "device",
            {"known_device": False, "device_other_owners": 2, "payer_other_devices": 2},
            False,
            70,
            40,
            {"shared_device": 30, "multiple_devices": 10, "unfamiliar_device": 0},
            "two_factor_required",
            id="three-device-rules-remain-one-factor-capped-at-40",
        ),
    ],
)
def test_related_rules_share_one_factor_and_reconstruct_capped_score(
    payload, factor, history_changes, young_destination, raw, points, contributions, expected
):
    payload["amount"] = 50_000
    if young_destination:
        payload["destination_account"]["opening_date"] = payload["transaction_date"]
    history = replace(History(0, 0, 3, True, True, 3, 60_000), **history_changes)
    status, metadata = evaluate(payload, ScoringPolicy(), history)
    assert status == expected
    assert metadata["decision_source"] == "risk_score"
    assert metadata["raw_score"] == raw
    assert metadata["risk_score"] == metadata["risk_factors_sum"] == points
    assert metadata["risk_group_count"] == 1
    assert metadata["group_scores"] == {factor: {"raw_score": raw, "score": points, "cap": points}}
    assert {rule["code"]: rule["contribution"] for rule in metadata["triggered_rules"]} == contributions
    assert sum(contributions.values()) == points


@pytest.mark.parametrize("value", [-1, 201, True, 0.5, "100"])
def test_invalid_factor_weight(value):
    with pytest.raises(ValueError):
        ScoringPolicy(factor_weights=replace(FactorWeights(), device=value))


def test_every_rule_references_a_valid_factor():
    policy = ScoringPolicy()
    assert set(asdict(policy.rule_factors)) == set(asdict(policy.weights))
    with pytest.raises(ValueError):
        replace(policy, rule_factors=replace(RuleFactors(), unfamiliar_device="typo"))


def test_load_partial_policy_and_default_configuration(tmp_path):
    assert Policy.from_file("config/risk-policy.json") == Policy()
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"scoring": {"factor_weights": {"device": 50}}}))
    policy = Policy.from_file(str(path))
    assert policy.scoring.factor_weights.device == 50
    assert policy.scoring.factor_weights.exposure == 100


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"scoring": []},
        {"scoring": {"factor_weights": []}},
        {"scoring": {"factor_weights": {"typo": 20}}},
        {"scoring": {"rule_factors": {"new_source_account": "typo"}}},
        {"scoring": {"rejection_threshold": 20}},
        {"unknown": 1},
    ],
)
def test_invalid_file_cannot_be_activated(tmp_path, data):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(data))
    with pytest.raises((ValueError, TypeError)):
        Policy.from_file(str(path))
