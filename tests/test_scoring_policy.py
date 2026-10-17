from dataclasses import replace

import pytest

from src.constants import Policy, RuleWeights, ScoringPolicy
from src.controllers.decision_engine import DecisionEngine
from src.repositories.pix_repository import History
from src.schemas.pix import PixTransactionCreate


@pytest.mark.parametrize(
    ("points", "expected"),
    [
        (29, "approved"),
        (30, "two_factor_required"),
        (79, "two_factor_required"),
        (80, "two_factor_required"),
    ],
)
def test_score_boundaries_and_single_group_rejection_guard(payload, points, expected):
    weights = replace(RuleWeights(), amount_above_customer_profile=points)
    policy = replace(Policy(), scoring=replace(ScoringPolicy(), weights=weights))
    payload["amount"] = 100_000
    status, metadata = DecisionEngine(policy).evaluate(
        PixTransactionCreate.model_validate(payload), History(0, 0, 0, 0, False, False, 1, 10_000)
    )
    assert status == expected
    assert metadata["risk_score"] == points
    assert metadata["risk_group_count"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"two_factor_threshold": 0},
        {"rejection_threshold": 101},
        {"two_factor_threshold": 80},
        {"minimum_rejection_groups": 0},
        {"minimum_rejection_groups": 8},
        {"rejection_threshold": True},
        {"weights": replace(RuleWeights(), unfamiliar_device=-1)},
        {"weights": replace(RuleWeights(), unfamiliar_device=101)},
        {"weights": replace(RuleWeights(), unfamiliar_device=1.5)},
    ],
)
def test_invalid_policy_cannot_be_activated(changes):
    with pytest.raises(ValueError):
        ScoringPolicy(**changes)
