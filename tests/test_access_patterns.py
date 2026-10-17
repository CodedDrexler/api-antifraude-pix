from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from conftest import new_transaction
from test_pix import post, seed_profile

from src.constants import FactorWeights, Policy, ScoringPolicy
from src.controllers.decision_engine import DecisionEngine
from src.gnn.service import combine_graph_risk
from src.repositories.pix_repository import History
from src.schemas.pix import PixTransactionCreate


def evaluate(payload, **changes):
    history = History(0, 0, 3, 60_000, False, False, 3, 60_000)
    return DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload),
        replace(history, **changes),
    )


@pytest.mark.parametrize("channel", ["app", "APP", "App", " app "])
@pytest.mark.parametrize(
    "date,night",
    [
        ("2026-10-17T19:59:59-03:00", False),
        ("2026-10-17T20:00:00-03:00", True),
        ("2026-10-18T05:59:59-03:00", True),
        ("2026-10-18T06:00:00-03:00", False),
        ("2026-10-18T02:00:00+03:00", True),
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
    "changes",
    [
        {"approved_count": 2},
        {"approved_night_count": 1},
        {"known_device": True, "known_destination": True},
    ],
)
def test_night_alone_or_habitual_use_is_not_risk(payload, changes):
    payload["amount"] = 50_000
    payload["transaction_date"] = "2026-10-17T23:00:00-03:00"
    assert "unusual_night_app" not in evaluate(payload, **changes)[1]["reasons"]


def test_night_minimum_amount_and_configurable_start(payload):
    payload["transaction_date"] = "2026-10-17T21:00:00-03:00"
    payload["amount"] = 49_999
    assert "unusual_night_app" not in evaluate(payload)[1]["reasons"]
    payload["amount"] = 50_000
    transaction = PixTransactionCreate.model_validate(payload)
    _, metadata = DecisionEngine(replace(Policy(), night_start_hour=22)).evaluate(
        transaction,
        History(0, 0, 3, 60_000, False, False, 3, 60_000),
    )
    assert "unusual_night_app" not in metadata["reasons"]


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


def test_device_signals_share_cap_and_cannot_reject_alone(payload):
    status, metadata = evaluate(payload, device_other_owners=2, payer_other_devices=2)
    assert status == "two_factor_required"
    assert metadata["group_scores"]["device"]["score"] == 40
    assert {"shared_device", "multiple_devices"} <= set(metadata["reasons"])
    assert metadata["risk_group_count"] == 1
    assert "multiple_devices" not in evaluate(payload, payer_other_devices=2, known_device=True)[1]["reasons"]


def test_missing_baseline_after_rejected_attempts_requires_two_factor_even_at_zero_weight(payload):
    policy = replace(
        Policy(),
        scoring=replace(
            ScoringPolicy(),
            factor_weights=replace(FactorWeights(), exposure=0),
        ),
    )
    status, metadata = DecisionEngine(policy).evaluate(
        PixTransactionCreate.model_validate(payload),
        History(0, 0, 0, 0, False, False, registered_count=2),
    )
    assert status == "two_factor_required"
    assert metadata["decision_source"] == "insufficient_history"
    assert metadata["reasons"] == ["insufficient_amount_history"]
    assert (
        combine_graph_risk(
            status,
            metadata,
            {
                "mode": "contribute",
                "status": "scored",
                "proposed_points": 0,
                "gnn_score": 0,
                "threshold": 80,
            },
        )[0]
        == "two_factor_required"
    )


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


def test_rejected_and_pending_attempts_do_not_inflate_approved_profile(api, payload):
    seed_profile(api, payload, 2, amount=1000)
    at = datetime.fromisoformat(payload["transaction_date"])
    for index, amount in enumerate([10_000, 3_000_000]):
        seed = new_transaction(
            payload, amount=amount, transaction_date=(at - timedelta(minutes=30 - index)).isoformat()
        )
        assert post(api, seed)["status"] != "approved"
    candidate = new_transaction(payload, amount=5000)
    metadata = post(api, candidate)["metadata"]
    assert metadata["profile_amount"] == 2000
    assert metadata["profile_transactions"] == 2
    assert metadata["profile_limit"] == 5000
    assert metadata["profile_basis"] == "approved"


def test_pending_bootstrap_is_not_raised_by_more_pending_attempts(api, payload):
    at = datetime.fromisoformat(payload["transaction_date"])
    post(api, new_transaction(payload, transaction_date=(at - timedelta(hours=3)).isoformat()))
    post(api, new_transaction(payload, amount=10_000, transaction_date=(at - timedelta(hours=2)).isoformat()))
    candidate = post(api, new_transaction(payload, amount=5000))
    assert candidate["metadata"]["profile_limit"] == 5000
    assert candidate["metadata"]["profile_basis"] == "initial_pending_attempt"


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
