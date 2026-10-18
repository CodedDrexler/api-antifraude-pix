"""Decision thresholds and precedence, including mandatory challenges and hard limits."""

from dataclasses import replace

import pytest

from src.constants import FactorWeights, Policy, RuleWeights, ScoringPolicy
from src.controllers.decision_engine import DecisionEngine
from src.gnn.service import combine_graph_risk
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate


@pytest.mark.parametrize(
    ("points", "account_points", "expected"),
    [
        pytest.param(29, 0, "approved", id="below-two-factor"),
        pytest.param(30, 0, "two_factor_required", id="at-two-factor"),
        pytest.param(31, 0, "two_factor_required", id="above-two-factor"),
        pytest.param(79, 0, "two_factor_required", id="one-factor-below-rejection"),
        pytest.param(80, 0, "two_factor_required", id="one-factor-at-rejection"),
        pytest.param(64, 15, "two_factor_required", id="two-factors-below-rejection"),
        pytest.param(65, 15, "rejected", id="two-factors-at-rejection"),
        pytest.param(66, 15, "rejected", id="two-factors-above-rejection"),
    ],
)
def test_score_boundaries_and_rejection_factor_guard(payload, points, account_points, expected):
    weights = replace(RuleWeights(), amount_above_customer_profile=points, new_source_account=account_points)
    policy = replace(Policy(), scoring=replace(ScoringPolicy(), weights=weights))
    payload["amount"] = 100_000
    payload["source_account"]["opening_date"] = payload["transaction_date"]
    status, metadata = DecisionEngine(policy).evaluate(
        PixTransactionCreate.model_validate(payload), History(0, 0, 0, False, False, 1, 10_000)
    )
    assert status == expected
    assert metadata["risk_score"] == points + account_points
    assert metadata["risk_group_count"] == (2 if account_points else 1)
    assert metadata["decision_source"] == "risk_score"
    assert metadata["hard_limits"] == []


@pytest.mark.parametrize(
    "points,expected",
    [
        pytest.param(44, "approved", id="below-configured-two-factor"),
        pytest.param(45, "two_factor_required", id="at-configured-two-factor"),
        pytest.param(59, "two_factor_required", id="below-configured-rejection"),
        pytest.param(60, "rejected", id="at-configured-rejection"),
    ],
)
def test_decision_uses_configured_thresholds(payload, points, expected):
    scoring = replace(
        ScoringPolicy(),
        two_factor_threshold=45,
        rejection_threshold=60,
        weights=replace(RuleWeights(), amount_above_customer_profile=points - 15),
    )
    payload["amount"] = 100_000
    payload["source_account"]["opening_date"] = payload["transaction_date"]
    status, metadata = DecisionEngine(replace(Policy(), scoring=scoring)).evaluate(
        PixTransactionCreate.model_validate(payload), History(0, 0, 0, False, False, 1, 10_000)
    )
    assert status == expected
    assert metadata["risk_score"] == points
    assert metadata["risk_group_count"] == 2
    assert metadata["policy"]["scoring"]["two_factor_threshold"] == 45
    assert metadata["policy"]["scoring"]["rejection_threshold"] == 60


@pytest.mark.parametrize(
    "known_destination,expected_groups,expected",
    [
        pytest.param(True, 2, "two_factor_required", id="two-factors-are-insufficient"),
        pytest.param(False, 3, "rejected", id="three-positive-factors-allow-rejection"),
    ],
)
def test_configured_rejection_requires_three_positive_factors(
    payload, known_destination, expected_groups, expected
):
    scoring = replace(ScoringPolicy(), minimum_rejection_groups=3)
    payload["amount"] = 100_000
    payload["source_account"]["opening_date"] = payload["transaction_date"]
    status, metadata = DecisionEngine(replace(Policy(), scoring=scoring)).evaluate(
        PixTransactionCreate.model_validate(payload),
        History(0, 0, 3, known_destination, True, 3, 60_000),
    )
    assert status == expected
    assert metadata["risk_group_count"] == expected_groups
    assert metadata["risk_score"] >= 80


@pytest.mark.parametrize(
    "registered,amount,graph_points,expected,source,exposure_rule",
    [
        pytest.param(
            0,
            1000,
            20,
            "two_factor_required",
            "first_transaction",
            "first_transaction",
            id="first-pix-needs-two-factor-at-zero-score",
        ),
        pytest.param(
            2,
            1000,
            0,
            "two_factor_required",
            "insufficient_history",
            "insufficient_amount_history",
            id="missing-reference-needs-two-factor-at-zero-score",
        ),
        pytest.param(
            0,
            3_000_000,
            20,
            "rejected",
            "hard_limit",
            "first_transaction",
            id="hard-limit-precedes-first-pix-two-factor",
        ),
        pytest.param(
            2,
            3_000_000,
            0,
            "rejected",
            "hard_limit",
            "insufficient_amount_history",
            id="hard-limit-precedes-missing-reference-two-factor",
        ),
    ],
)
def test_missing_reference_priority_survives_zero_weights_and_graph(
    payload, registered, amount, graph_points, expected, source, exposure_rule
):
    scoring = replace(ScoringPolicy(), factor_weights=replace(FactorWeights(), exposure=0, activity=0))
    policy = replace(Policy(), scoring=scoring)
    payload["amount"] = amount
    status, metadata = DecisionEngine(policy).evaluate(
        PixTransactionCreate.model_validate(payload),
        History(0, 0, 0, False, False, registered_count=registered),
    )
    assert status == expected
    assert metadata["decision_source"] == source
    assert metadata["risk_score"] == metadata["risk_group_count"] == 0
    assert metadata["profile_limit"] is None
    assert exposure_rule in metadata["reasons"]
    if source == "hard_limit":
        assert metadata["hard_limits"] == ["accumulated_amount_above_limit"]
        assert metadata["group_scores"]["activity"]["score"] == 0
    else:
        assert metadata["hard_limits"] == []
    combined, enriched = combine_graph_risk(
        status,
        metadata,
        {
            "mode": "contribute",
            "status": "scored",
            "proposed_points": graph_points,
            "gnn_score": 95 if graph_points else 0,
            "threshold": 80,
        },
    )
    assert combined == expected
    assert enriched["decision_source"] == source
    assert enriched["risk_score"] == graph_points
    assert metadata["risk_score"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"two_factor_threshold": 0},
        {"rejection_threshold": 101},
        {"two_factor_threshold": 80},
        {"minimum_rejection_groups": 0},
        {"minimum_rejection_groups": 9},
        {"rejection_threshold": True},
        {"weights": replace(RuleWeights(), unfamiliar_device=-1)},
        {"weights": replace(RuleWeights(), unfamiliar_device=101)},
        {"weights": replace(RuleWeights(), unfamiliar_device=1.5)},
    ],
)
def test_invalid_policy_cannot_be_activated(changes):
    with pytest.raises(ValueError):
        ScoringPolicy(**changes)
