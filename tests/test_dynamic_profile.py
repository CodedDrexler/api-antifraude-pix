from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from conftest import new_transaction
from test_pix import post

from src.constants import FactorWeights, Policy, ScoringPolicy
from src.controllers.decision_engine import DecisionEngine
from src.gnn.service import combine_graph_risk
from src.repositories.pix_repository import History
from src.schemas.pix import PixTransactionCreate


@pytest.mark.parametrize("count", [1, 3, 10])
@pytest.mark.parametrize("amount, expected", [(4999, 0), (5000, 80), (5001, 80)])
def test_dynamic_ceiling_uses_available_history_without_a_minimum(payload, count, amount, expected):
    payload["amount"] = amount
    status, metadata = DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload),
        History(0, 0, 0, 0, False, False, count, count * 1000),
    )
    assert metadata["risk_score"] == expected
    assert metadata["risk_factors_sum"] == expected
    assert metadata["profile_average"] == 1000
    assert metadata["profile_limit"] == 5000
    assert status == ("two_factor_required" if expected else "approved")


def test_fractional_average_is_compared_exactly_and_policy_is_configurable(payload):
    policy = replace(Policy(), profile_history_size=2, profile_multiplier=3)
    transaction = PixTransactionCreate.model_validate(payload)
    history = History(0, 0, 0, 0, False, False, 2, 667)
    assert DecisionEngine(policy).evaluate(transaction, history)[1]["risk_score"] == 0
    transaction.amount = 1001
    assert DecisionEngine(policy).evaluate(transaction, history)[1]["risk_score"] == 80


@pytest.mark.parametrize("field", ["profile_history_size", "profile_multiplier"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "10"])
def test_invalid_dynamic_profile_configuration(field, value):
    with pytest.raises(ValueError):
        replace(Policy(), **{field: value})


def test_first_pix_requires_two_factor_even_with_zero_factor_weight_and_graph(payload):
    policy = replace(
        Policy(),
        scoring=replace(
            ScoringPolicy(),
            factor_weights=replace(FactorWeights(), exposure=0),
        ),
    )
    status, metadata = DecisionEngine(policy).evaluate(
        PixTransactionCreate.model_validate(payload),
        History(0, 0, 0, 0, False, False),
    )
    assert status == "two_factor_required"
    assert metadata["decision_source"] == "first_transaction"
    assert metadata["profile_limit"] is None
    combined, _ = combine_graph_risk(
        status,
        metadata,
        {
            "mode": "contribute",
            "status": "scored",
            "proposed_points": 20,
            "gnn_score": 95,
            "threshold": 80,
        },
    )
    assert combined == "two_factor_required"


def test_repository_uses_last_ten_approved_pix_without_day_cutoff(api, payload):
    at = datetime.fromisoformat(payload["transaction_date"])
    first = post(
        api,
        new_transaction(payload, amount=1_000_000, transaction_date=(at - timedelta(days=50)).isoformat()),
    )
    assert first["status"] == "two_factor_required"
    for index in range(10):
        post(
            api,
            new_transaction(
                payload, amount=1000, transaction_date=(at - timedelta(days=40 - index)).isoformat()
            ),
        )
    # A later event and another payer cannot affect this candidate's baseline.
    post(
        api, new_transaction(payload, amount=2_000_000, transaction_date=(at + timedelta(days=1)).isoformat())
    )
    other = new_transaction(payload, amount=2_000_000)
    other["source_account"]["owner"]["document_number"] = "11122233344"
    post(api, other)
    candidate = post(api, new_transaction(payload, amount=5000))
    assert candidate["metadata"]["profile_transactions"] == 10
    assert candidate["metadata"]["profile_amount"] == 10_000
    assert candidate["metadata"]["profile_basis"] == "approved"
    assert candidate["metadata"]["risk_score"] == 80
    assert candidate["status"] == "two_factor_required"


def test_registered_two_factor_pix_can_bootstrap_amount_history(api, payload):
    first = post(api, payload)
    assert first["status"] == "two_factor_required"
    assert post(api, payload) == first
    second = post(api, new_transaction(payload, amount=5000))
    assert second["metadata"]["profile_transactions"] == 1
    assert second["metadata"]["approved_transactions"] == 0
    assert second["metadata"]["profile_limit"] == 5000
    assert second["status"] == "two_factor_required"
