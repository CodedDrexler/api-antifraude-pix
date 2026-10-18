"""Cold-start amount boundaries, independent controls and immutable policy replay."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from conftest import new_transaction, post
from sqlalchemy.orm import Session

from src.constants import Policy
from src.controllers.decision_engine import DecisionEngine
from src.controllers.pix_controller import PixController
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate


@pytest.mark.parametrize("registered", [0, 2])
@pytest.mark.parametrize("amount", [1, 1000, 49_999, 50_000, 50_001, 150_000])
def test_no_history_amount_floor(payload, registered, amount):
    payload["amount"] = amount
    status, metadata = DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload),
        History(0, 0, 0, False, False, registered_count=registered),
    )
    needs_confirmation = amount >= 50_000
    code = "first_transaction" if registered == 0 else "insufficient_amount_history"
    assert status == ("two_factor_required" if needs_confirmation else "approved")
    assert metadata["risk_score"] == (30 if needs_confirmation else 0)
    assert metadata["reasons"] == ([code] if needs_confirmation else ["no_rule_triggered"])
    assert metadata["profile_limit"] is None
    if needs_confirmation:
        rule = metadata["triggered_rules"][0]
        assert rule["threshold"]["minimum_amount"] == 50_000
        assert rule["observed"]["amount"] == amount


@pytest.mark.parametrize("amount,expected", [(24_999, "approved"), (25_000, "two_factor_required")])
def test_no_history_amount_floor_is_configurable(payload, amount, expected):
    payload["amount"] = amount
    policy = replace(Policy(), no_history_min_amount=25_000)
    status, metadata = DecisionEngine(policy).evaluate(
        PixTransactionCreate.model_validate(payload), History(0, 0, 0, False, False)
    )
    assert status == expected
    assert metadata["policy"]["no_history_min_amount"] == 25_000


@pytest.mark.parametrize("value", [0, -1, True, 500.5, "50000", None])
def test_no_history_amount_floor_requires_positive_integer_cents(value):
    with pytest.raises(ValueError):
        replace(Policy(), no_history_min_amount=value)


@pytest.mark.parametrize(
    "history,expected,reason",
    [
        (History(0, 0, 0, False, False, device_other_owners=2), "two_factor_required", "shared_device"),
        (History(5, 5000, 0, False, False), "rejected", "velocity_above_limit"),
        (History(1, 2_999_000, 0, False, False), "rejected", "accumulated_amount_above_limit"),
    ],
)
def test_low_value_without_history_still_respects_other_controls(payload, history, expected, reason):
    status, metadata = DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload), history
    )
    assert status == expected
    assert reason in metadata["reasons"]
    assert "first_transaction" not in metadata["reasons"]
    assert "insufficient_amount_history" not in metadata["reasons"]


@pytest.mark.parametrize(
    "amount,expected", [(1000, "approved"), (49_999, "approved"), (50_000, "two_factor_required")]
)
def test_first_pix_http_boundary_and_replay(api, payload, amount, expected):
    payload["amount"] = amount
    result = post(api, payload)
    assert result["status"] == expected
    assert result["metadata"]["profile_basis"] == "unavailable"
    assert result["metadata"]["policy"]["version"] == "pix-score-v9"
    assert post(api, payload) == result
    assert api("GET", "/pix/transaction/" + payload["id"])[1] == result


def test_pending_attempt_cannot_raise_the_reference_for_a_small_pix(api, payload):
    at = datetime.fromisoformat(payload["transaction_date"])
    pending = new_transaction(payload, amount=150_000, transaction_date=(at - timedelta(hours=1)).isoformat())
    assert post(api, pending)["status"] == "two_factor_required"
    small = post(api, payload)
    assert small["status"] == "approved"
    assert small["metadata"]["profile_transactions"] == 0
    assert small["metadata"]["profile_amount"] == 0
    assert small["metadata"]["profile_basis"] == "unavailable"
    next_pix = post(api, new_transaction(payload, amount=5000))
    assert next_pix["metadata"]["profile_amount"] == 1000
    assert next_pix["metadata"]["profile_transactions"] == 1
    assert next_pix["metadata"]["reasons"] == ["amount_above_customer_profile"]
    assert next_pix["status"] == "two_factor_required"


def test_policy_change_does_not_recompute_a_saved_first_pix(database_engine, payload):
    transaction = PixTransactionCreate.model_validate(payload)
    with Session(database_engine) as session:
        previous_policy = replace(Policy(), version="pix-score-v8", no_history_min_amount=1)
        saved = PixController(session, previous_policy).analyze(transaction)
        assert saved.status == "two_factor_required"
        current = PixController(session, Policy())
        assert current.analyze(transaction) == saved
        assert current.get_analysis(transaction.id) == saved
        assert saved.metadata["policy"]["version"] == "pix-score-v8"
