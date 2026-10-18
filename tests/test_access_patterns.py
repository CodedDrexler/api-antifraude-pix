"""Access context, device relationships and their history windows."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from conftest import new_transaction, post, seed_profile

from src.constants import Policy
from src.controllers.decision_engine import DecisionEngine
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate


def evaluate(payload, **changes):
    history = History(0, 0, 3, False, False, 3, 60_000)
    return DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload),
        replace(history, **changes),
    )


@pytest.mark.parametrize(
    "channel,date,night",
    [
        pytest.param("app", "2026-10-17T19:59:59-03:00", False, id="before-night"),
        pytest.param("app", "2026-10-17T20:00:00-03:00", True, id="night-start-inclusive"),
        pytest.param("app", "2026-10-18T05:59:59-03:00", True, id="last-night-second"),
        pytest.param("app", "2026-10-18T06:00:00-03:00", False, id="night-end-exclusive"),
        pytest.param("app", "2026-10-18T02:00:00+03:00", True, id="timezone-converted-to-brasilia"),
        pytest.param("APP", "2026-10-17T23:00:00-03:00", True, id="uppercase-channel"),
        pytest.param("App", "2026-10-17T23:00:00-03:00", True, id="mixed-case-channel"),
        pytest.param(" app ", "2026-10-17T23:00:00-03:00", True, id="trimmed-channel"),
    ],
)
def test_night_rule_uses_app_and_brasilia_boundaries(payload, channel, date, night):
    payload["source"]["channel"] = channel
    payload["transaction_date"] = date
    payload["amount"] = 50_000
    _, metadata = evaluate(payload)
    assert ("unusual_night_app" in metadata["reasons"]) == night
    assert metadata["access_context"]["regulatory_limits_checked"] is False


@pytest.mark.parametrize("channel", ["internet_banking", "web", "atm", "api"])
def test_non_app_channel_has_no_contextual_night_penalty_but_keeps_hard_limits(payload, channel):
    payload["source"]["channel"] = channel
    payload["transaction_date"] = "2026-10-17T23:00:00-03:00"
    payload["amount"] = 50_000
    _, metadata = evaluate(payload)
    assert "unusual_night_app" not in metadata["reasons"]
    status, metadata = evaluate(payload, recent_count=5)
    assert status == "rejected"
    assert "velocity_above_limit" in metadata["hard_limits"]


@pytest.mark.parametrize(
    "date,night",
    [
        pytest.param("2026-10-17T21:59:59-03:00", False, id="before-configured-night-start"),
        pytest.param("2026-10-17T22:00:00-03:00", True, id="at-configured-night-start"),
    ],
)
def test_configured_night_start_controls_the_signal(payload, date, night):
    payload["transaction_date"] = date
    payload["amount"] = 50_000
    assert "unusual_night_app" in evaluate(payload)[1]["reasons"]
    transaction = PixTransactionCreate.model_validate(payload)
    _, metadata = DecisionEngine(replace(Policy(), night_start_hour=22)).evaluate(
        transaction,
        History(0, 0, 3, False, False, 3, 60_000),
    )
    assert ("unusual_night_app" in metadata["reasons"]) is night
    assert metadata["access_context"]["is_night"] is night


@pytest.mark.parametrize(
    "changes",
    [
        {"night_start_hour": 24},
        {"night_end_hour": -1},
        {"night_start_hour": True},
        {"night_start_hour": 6},
        {"device_owner_limit": 1},
        {"payer_device_limit": 1},
    ],
)
def test_invalid_access_policy(changes):
    with pytest.raises(ValueError):
        replace(Policy(), **changes)


def test_shared_device_counts_distinct_owners_and_excludes_old_future_events(api, payload):
    at = datetime.fromisoformat(payload["transaction_date"])
    # Many accounts belonging to the same owner must not look like a ring.
    for index in range(3):
        seed = new_transaction(payload)
        seed["source_account"]["account_number"] = str(index)
        post(api, seed)
    assert "shared_device" not in post(api, new_transaction(payload))["metadata"]["reasons"]
    for offset, owner in [(0, "11122233344"), (86401, "22233344455"), (-1, "33344455566")]:
        seed = new_transaction(payload, transaction_date=(at - timedelta(seconds=offset)).isoformat())
        seed["source_account"]["owner"]["document_number"] = owner
        post(api, seed)
    decision = post(api, new_transaction(payload))
    assert decision["metadata"]["device_owner_count"] == 2
    assert "shared_device" not in decision["metadata"]["reasons"]
    third = new_transaction(payload)
    third["source_account"]["owner"]["document_number"] = "44455566677"
    assert "shared_device" in post(api, third)["metadata"]["reasons"]


def test_multiple_devices_aggregate_payer_across_accounts_and_deduplicate(api, payload):
    for index, device in enumerate(["one", "one", "two"]):
        seed = new_transaction(payload)
        seed["source"]["device_id"] = payload["id"] + device
        seed["source_account"]["account_number"] = str(index)
        post(api, seed)
    result = post(api, payload)
    assert result["metadata"]["payer_device_count"] == 3
    assert "multiple_devices" in result["metadata"]["reasons"]
    assert post(api, payload) == result


def test_shared_device_concurrency_sees_prior_commits(api, payload):
    candidates = []
    for index in range(3):
        seed = new_transaction(payload)
        seed["source_account"]["owner"]["document_number"] = f"{int(payload['id'][-10:], 16) + index:011d}"[
            -11:
        ]
        candidates.append(seed)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda candidate: post(api, candidate), candidates))
    assert sorted(result["metadata"]["device_owner_count"] for result in results) == [1, 2, 3]
    assert sum("shared_device" in r["metadata"]["reasons"] for r in results) == 1


def test_repository_recognizes_habitual_night_use(api, payload):
    payload["transaction_date"] = "2026-10-18T01:00:00-03:00"
    seed_profile(api, payload, 3, amount=20_000)
    payload["amount"] = 50_000
    payload["source"]["device_id"] = "night-" + payload["id"]
    result = post(api, payload)
    assert result["metadata"]["access_context"]["approved_night_transactions"] > 0
    assert "unusual_night_app" not in result["metadata"]["reasons"]


def test_repository_novel_app_night_combines_context_with_device(api, payload):
    seed_profile(api, payload, 3, amount=20_000)
    payload = deepcopy(payload)
    payload["transaction_date"] = "2026-10-17T23:00:00-03:00"
    payload["amount"] = 50_000
    payload["source"]["device_id"] = "night-" + payload["id"]
    result = post(api, payload)
    assert result["status"] == "two_factor_required"
    assert result["metadata"]["risk_score"] == 35
    assert "unusual_night_app" in result["metadata"]["reasons"]
