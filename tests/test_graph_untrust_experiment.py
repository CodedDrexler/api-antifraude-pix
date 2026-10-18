"""Causal and anti-contamination checks for the offline graph experiment."""

import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from scripts.evaluate_graph_untrust import (
    STRESS_KINDS,
    GraphPolicy,
    Observation,
    add_points,
    graph_signal,
    key,
    rapid_repasses,
    replay,
    stress_scenario,
)
from src.constants import Policy
from src.schemas.pix import PixTransactionCreate

AT = datetime(2026, 9, 20, 15, tzinfo=timezone.utc)


def account(index):
    return {
        "participant": "12345678",
        "branch": "0001",
        "account_number": str(index),
        "opening_date": "2025-01-01T00:00:00+00:00",
        "owner": {"document_number": f"{index:011d}"},
    }


def payment(identifier, sender, receiver, minutes, amount=10_000):
    return {
        "id": identifier,
        "amount": amount,
        "transaction_date": (AT - timedelta(minutes=minutes)).isoformat(),
        "source_account": account(sender),
        "destination_account": account(receiver),
        "source": {"device_id": f"device-{sender}", "channel": "app", "ip": "198.51.100.23"},
    }


def observation(identifier, sender, receiver, minutes, *, increment=0, status="approved", amount=10_000):
    return Observation(
        PixTransactionCreate.model_validate(payment(identifier, sender, receiver, minutes, amount)),
        status,
        increment,
    )


def evidence(node):
    return [observation(f"e-{node}-{i}", node, 90, 120 + i * 20, increment=25) for i in range(4)]


def signal(past, graph_policy=GraphPolicy()):
    tx = PixTransactionCreate.model_validate(payment("candidate", 1, 2, 0))
    return graph_signal(tx, past, Policy(), graph_policy)


def test_two_hops_finds_independent_evidence_without_counting_paths_or_root():
    past = evidence(10) + [
        observation("a", 1, 20, 30),
        observation("b", 20, 10, 20),
        observation("c", 10, 20, 10),
        observation("self", 1, 1, 5, increment=25),
    ]
    assert signal(past, replace(GraphPolicy(), hops=1))["suspect_nodes"] == 0
    result = signal(past)
    assert result["suspect_nodes"] == 1
    assert result["count_neighbors"] == 5
    assert result["weighted_neighbors"] <= 10


def test_future_and_expired_evidence_do_not_increase_current_risk():
    linked = [observation("a", 1, 10, 30)]
    future = [observation(f"future-{i}", 10, 90, -i - 1, increment=25) for i in range(4)]
    expired = [observation(f"old-{i}", 10, 90, 1500 + i, increment=25) for i in range(4)]
    assert signal(linked + future + expired)["count_neighbors"] == 0
    assert signal(evidence(10) + [observation("old-link", 1, 10, 1500)])["count_neighbors"] == 0


def test_rejected_attempt_does_not_create_payment_link_but_pending_is_explicit_proxy():
    past = evidence(10)
    assert signal(past + [observation("a", 1, 10, 30, status="rejected")])["suspect_nodes"] == 0
    assert signal(past + [observation("a", 1, 10, 30, status="two_factor_required")])["suspect_nodes"] == 1


def test_same_suspicion_is_diluted_by_legitimate_contacts_and_ages():
    risky = evidence(10) + [observation("a", 1, 10, 30)]
    diverse = risky + [observation(f"clean-{i}", 1, 20 + i, 30) for i in range(8)]
    assert signal(diverse)["weighted_neighbors"] < signal(risky)["weighted_neighbors"]
    old_link = evidence(10) + [observation("a", 1, 10, 700)]
    assert signal(old_link)["weighted_neighbors"] < signal(risky)["weighted_neighbors"]


def test_neighbor_budget_keeps_latest_contacts_and_bounds_search():
    past = evidence(10) + [observation("a", 1, 10, 60)]
    past += [observation(f"n-{i}", 1, 20 + i, i + 1) for i in range(11)]
    result = signal(past)
    assert result["neighbor_cap_reached"]
    assert result["suspect_nodes"] == 0  # Older suspicious contact was outside the explicit budget.
    assert result["visited_nodes"] <= 1 + 10 + 100


def test_repass_requires_distinct_receipts_time_order_value_and_different_destination():
    root = key(account(1))
    past = [observation("in-1", 30, 1, 60), observation("out-1", 1, 10, 55), observation("out-2", 1, 10, 50)]
    assert rapid_repasses(root, past, GraphPolicy()) == 1  # One receipt cannot support two repasses.
    past += [observation("in-2", 31, 1, 40), observation("out-3", 1, 10, 35, amount=8500)]
    assert rapid_repasses(root, past, GraphPolicy()) == 2
    assert (
        rapid_repasses(root, [observation("in", 30, 1, 60), observation("refund", 1, 30, 55)], GraphPolicy())
        == 0
    )
    assert (
        rapid_repasses(root, [observation("in", 30, 1, 60), observation("late", 1, 10, 10)], GraphPolicy())
        == 0
    )


def test_replay_deduplicates_retries_and_excludes_future_and_candidate():
    candidate, records, _, _ = stress_scenario(20_000, "test", "mule_direct")
    tx, past, _, status, metadata = replay(candidate, records, Policy())
    future = copy.deepcopy(records[0])
    future.update(id="future", transaction_date=(tx.transaction_date + timedelta(days=1)).isoformat())
    _, extra, _, extra_status, extra_metadata = replay(
        candidate, records + records + [future, candidate], Policy()
    )
    assert status == extra_status
    assert metadata == extra_metadata
    assert len(past) == len(extra)
    assert [(r.tx.id, r.increment) for r in past] == [(r.tx.id, r.increment) for r in extra]


def test_graph_does_not_relax_existing_restriction_and_uses_group_rejection_gate():
    candidate, records, _, _ = stress_scenario(20_001, "test", "normal")
    _, _, _, status, metadata = replay(candidate, records, Policy())
    assert metadata["risk_score"] == 25 and status == "approved"
    assert add_points(status, metadata, 5) == ("two_factor_required", 30)
    assert add_points("rejected", metadata, 0)[0] == "rejected"
    assert add_points("two_factor_required", metadata, 0)[0] == "two_factor_required"
    assert metadata["risk_score"] == 25


def test_stress_intent_is_separate_from_rule_outputs_and_splits_are_disjoint():
    mule = stress_scenario(20_001, "test", "mule_direct")
    merchant = stress_scenario(20_001, "test", "merchant_fast_settlement")
    assert mule[2] == 1 and merchant[2] == 0
    assert stress_scenario(20_001, "test", "mule_direct") == mule
    validation = stress_scenario(10_001, "validation", "mule_direct")
    assert key(validation[0]["source_account"]) != key(mule[0]["source_account"])


@pytest.mark.parametrize("kind", STRESS_KINDS)
@pytest.mark.parametrize("seed,expected_score", [(20_000, 0), (20_001, 25)])
def test_stress_candidates_isolate_graph_effect_without_own_behavior_anomaly(kind, seed, expected_score):
    candidate, records, _, _ = stress_scenario(seed, "test", kind)
    _, _, _, status, metadata = replay(candidate, records, Policy())
    assert status == "approved"
    assert metadata["risk_score"] == expected_score
