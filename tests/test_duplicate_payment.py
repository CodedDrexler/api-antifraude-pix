import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from conftest import new_transaction, request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from test_pix import post, seed_profile

from src.constants import FactorWeights, Policy, ScoringPolicy
from src.controllers.account_untrust import UntrustHistory, assess_untrust
from src.controllers.decision_engine import DecisionEngine
from src.controllers.pix_controller import fingerprint
from src.repositories.pix_repository import History, PixRepository
from src.schemas.pix import PixTransactionCreate


@pytest.mark.parametrize(
    "seconds, expected", [(0, True), (119, True), (120, True), (121, False), (-1, False)]
)
def test_duplicate_window_and_future_exclusion(api, payload, seconds, expected):
    at = datetime.fromisoformat(payload["transaction_date"])
    previous = new_transaction(payload, transaction_date=(at - timedelta(seconds=seconds)).isoformat())
    post(api, previous)
    result = post(api, payload)
    metadata = result["metadata"]
    assert ("possible_duplicate_payment" in metadata["reasons"]) is expected
    assert ("duplicate_payment" in metadata) is expected
    if expected:
        assert result["status"] == "two_factor_required"
        assert metadata["risk_score"] == 30
        assert metadata["duplicate_payment"]["previous_transaction_id"] == previous["id"]
        assert metadata["duplicate_payment"]["elapsed_seconds"] == seconds
        assert metadata["duplicate_payment"]["previous_payment_confirmed"] is False


def test_approved_pix_duplicate_is_explained_in_compact_response_and_replayed(api, payload):
    seed_profile(api, payload, 1)
    original = post(api, new_transaction(payload))
    assert original["status"] == "approved"
    status, duplicate, _ = request("POST", "/pix/transaction", payload)
    assert status == 200
    assert duplicate["status"] == "two_factor_required"
    assert duplicate["metadata"]["risk_factors"][0]["name"] == "duplication"
    assert "Possível pagamento duplicado" in duplicate["metadata"]["duplicate_payment"]["message"]
    assert request("POST", "/pix/transaction", payload)[1] == duplicate
    assert request("GET", "/pix/transaction/" + payload["id"])[1] == duplicate


@pytest.mark.parametrize("field", ["amount", "payer", "source_account", "destination", "recipient"])
def test_different_payment_identity_does_not_trigger_duplicate(api, payload, field):
    post(api, new_transaction(payload))
    if field == "amount":
        payload["amount"] += 1
    elif field == "payer":
        payload["source_account"]["owner"]["document_number"] = "12345678909"
    elif field == "source_account":
        payload["source_account"]["account_number"] += "-other"
    elif field == "destination":
        payload["destination_account"]["account_number"] += "-other"
    else:
        payload["destination_account"]["owner"]["document_number"] = "12345678909"
    result = post(api, payload)
    assert "possible_duplicate_payment" not in result["metadata"]["reasons"]
    assert "duplicate_payment" not in result["metadata"]


def test_changed_device_and_opening_dates_do_not_hide_duplicate(api, payload):
    original = post(api, new_transaction(payload))
    payload["source"]["device_id"] += "-other"
    payload["source_account"]["opening_date"] = "2019-01-01T00:00:00Z"
    payload["destination_account"]["opening_date"] = "2019-01-01T00:00:00Z"
    result = post(api, payload)
    assert result["metadata"]["duplicate_payment"]["previous_transaction_id"] != payload["id"]
    assert result["status"] == original["status"] == "two_factor_required"


def test_rejected_attempt_is_not_a_possible_previous_payment(api, payload):
    payload["amount"] = 3_000_000
    assert post(api, new_transaction(payload))["status"] == "rejected"
    result = post(api, payload)
    assert result["status"] == "rejected"
    assert "duplicate_payment" not in result["metadata"]


def test_concurrent_new_ids_detect_duplicate_and_retries_stay_idempotent(api, payload):
    transactions = [new_transaction(payload), new_transaction(payload)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: post(api, item), transactions))
    assert sum("duplicate_payment" in item["metadata"] for item in results) == 1
    assert all(item["status"] == "two_factor_required" for item in results)
    for transaction, result in zip(transactions, results, strict=True):
        assert post(api, transaction) == result
    last = post(api, payload)
    assert last["metadata"]["recent_transactions"] == 2


def test_duplicate_factor_weight_is_configurable_without_increasing_account_untrust(payload):
    policy = Policy()
    history = History(1, 1000, 1, 1000, True, True, 1, 1000, duplicate_transaction_id="previous")
    transaction = PixTransactionCreate.model_validate(payload)
    status, metadata = DecisionEngine(policy).evaluate(transaction, history)
    assert status == "two_factor_required"
    assert metadata["risk_score"] == 30
    _, untrust, _ = assess_untrust(status, metadata, UntrustHistory(), policy.untrust)
    assert untrust["increment"] == 0
    disabled = replace(
        policy, scoring=replace(ScoringPolicy(), factor_weights=replace(FactorWeights(), duplication=0))
    )
    assert DecisionEngine(disabled).evaluate(transaction, history)[0] == "approved"


@pytest.mark.skipif(not os.environ.get("PIX_TEST_DATABASE_URL"), reason="Requires isolated database")
def test_repository_respects_custom_duplicate_window(api, payload):
    at = datetime.fromisoformat(payload["transaction_date"])
    post(api, new_transaction(payload, transaction_date=(at - timedelta(seconds=60)).isoformat()))
    transaction = PixTransactionCreate.model_validate(payload)
    source = transaction.source_account.model_dump(mode="json")
    destination = transaction.destination_account.model_dump(mode="json")
    source.pop("opening_date")
    destination.pop("opening_date")
    engine = create_engine(os.environ["PIX_TEST_DATABASE_URL"])
    try:
        with Session(engine) as session:
            repository = PixRepository(session)
            assert repository.history(
                transaction, fingerprint(destination), Policy(), fingerprint(source)
            ).duplicate_transaction_id
            assert (
                repository.history(
                    transaction,
                    fingerprint(destination),
                    replace(Policy(), duplicate_window_seconds=30),
                    fingerprint(source),
                ).duplicate_transaction_id
                is None
            )
    finally:
        engine.dispose()


def test_duplicate_never_overrides_a_hard_rejection(payload):
    history = History(5, 5000, 1, 1000, True, True, 1, 1000, duplicate_transaction_id="previous")
    status, metadata = DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload), history
    )
    assert status == "rejected"
    assert metadata["decision_source"] == "hard_limit"
    assert "velocity_above_limit" in metadata["hard_limits"]


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "120"])
def test_invalid_duplicate_window(value):
    with pytest.raises(ValueError):
        replace(Policy(), duplicate_window_seconds=value)
