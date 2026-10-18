"""Construction, eligibility and precision of approved and provisional value references."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from conftest import new_transaction, post, seed_profile

from src.constants import Policy
from src.controllers.decision_engine import DecisionEngine
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate


@pytest.mark.parametrize("count", [1, 3, 10], ids=["one-sample", "three-samples", "ten-samples"])
def test_reference_average_is_independent_of_available_sample_count(payload, count):
    payload["amount"] = 5000
    status, metadata = DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload),
        History(0, 0, 0, False, False, count, count * 1000),
    )
    assert metadata["risk_score"] == metadata["risk_factors_sum"] == 80
    assert metadata["profile_transactions"] == count
    assert metadata["profile_average"] == 1000
    assert metadata["profile_limit"] == 5000
    assert status == "two_factor_required"


def test_fractional_average_is_compared_exactly_and_policy_is_configurable(payload):
    policy = replace(Policy(), profile_history_size=2, profile_multiplier=3)
    transaction = PixTransactionCreate.model_validate(payload)
    history = History(0, 0, 0, False, False, 2, 667)
    assert DecisionEngine(policy).evaluate(transaction, history)[1]["risk_score"] == 0
    transaction.amount = 1001
    assert DecisionEngine(policy).evaluate(transaction, history)[1]["risk_score"] == 80


@pytest.mark.parametrize("field", ["profile_history_size", "profile_multiplier"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "10"])
def test_invalid_dynamic_profile_configuration(field, value):
    with pytest.raises(ValueError):
        replace(Policy(), **{field: value})


def test_repository_uses_last_ten_approved_pix_without_day_cutoff(api, payload):
    at = datetime.fromisoformat(payload["transaction_date"])
    first = post(
        api,
        new_transaction(payload, amount=1_000_000, transaction_date=(at - timedelta(days=50)).isoformat()),
    )
    assert first["status"] == "two_factor_required"
    # This approved outlier must be displaced by the ten newer approvals.
    oldest_approved = post(
        api,
        new_transaction(payload, amount=2000, transaction_date=(at - timedelta(days=45)).isoformat()),
    )
    assert oldest_approved["status"] == "approved"
    for index in range(10):
        approved = post(
            api,
            new_transaction(
                payload, amount=1000, transaction_date=(at - timedelta(days=40 - index)).isoformat()
            ),
        )
        assert approved["status"] == "approved"
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
    assert second["metadata"]["profile_basis"] == "initial_pending_attempt"
    assert second["metadata"]["risk_score"] == 80
    assert second["metadata"]["reasons"] == ["amount_above_customer_profile"]
    assert second["status"] == "two_factor_required"


def test_rejected_and_pending_attempts_do_not_inflate_approved_profile(api, payload):
    seed_profile(api, payload, 2, amount=1000)
    at = datetime.fromisoformat(payload["transaction_date"])
    for index, (amount, expected) in enumerate([(10_000, "two_factor_required"), (3_000_000, "rejected")]):
        seed = new_transaction(
            payload, amount=amount, transaction_date=(at - timedelta(minutes=30 - index)).isoformat()
        )
        assert post(api, seed)["status"] == expected
    candidate = post(api, new_transaction(payload, amount=5000))
    metadata = candidate["metadata"]
    assert metadata["profile_amount"] == 2000
    assert metadata["profile_transactions"] == 2
    assert metadata["profile_limit"] == 5000
    assert metadata["profile_basis"] == "approved"
    assert candidate["status"] == "two_factor_required"


def test_pending_bootstrap_survives_old_history_without_establishing_trust(api, payload):
    at = datetime.fromisoformat(payload["transaction_date"])
    for days, amount in [(32, 1000), (31, 10_000)]:
        pending = new_transaction(
            payload, amount=amount, transaction_date=(at - timedelta(days=days)).isoformat()
        )
        assert post(api, pending)["status"] == "two_factor_required"
    metadata = post(api, new_transaction(payload, amount=5000))["metadata"]
    assert metadata["registered_transactions"] == 2
    assert metadata["profile_transactions"] == 1
    assert metadata["profile_amount"] == 1000
    assert metadata["profile_limit"] == 5000
    assert metadata["profile_basis"] == "initial_pending_attempt"
    assert metadata["approved_transactions"] == 0
    assert metadata["known_device"] is False
    assert metadata["known_destination"] is False
