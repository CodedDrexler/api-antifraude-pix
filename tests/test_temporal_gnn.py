"""Causal checks for the offline directed model and its comparison artifacts."""

import copy
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

from scripts.evaluate_graph_untrust import replay
from scripts.temporal_graph_examples import source_scenario
from src.constants import Policy
from src.gnn.evaluation import select_threshold
from src.gnn.graph import build_graph, parse_date
from src.gnn.model import GraphSageModel
from src.gnn.service import DEFAULT_MODEL, GraphRiskService
from src.gnn.temporal_graph import (
    RELATIONS,
    TRANSACTION_FEATURES,
    GraphEvent,
    build_temporal_graph,
    relation_mean,
)
from src.gnn.temporal_model import TemporalModel

ROOT = Path(__file__).resolve().parents[1]


def event(payload, identifier, sender, receiver, minutes, *, increment=0, status="approved"):
    row = copy.deepcopy(payload)
    row["id"] = identifier
    row["amount"] = 10_000
    row["transaction_date"] = (
        parse_date(payload["transaction_date"]) - timedelta(minutes=minutes)
    ).isoformat()
    for side, owner in (("source_account", sender), ("destination_account", receiver)):
        row[side]["owner"]["document_number"] = f"{owner:011d}"
        row[side]["account_number"] = f"account-{owner}"
    return GraphEvent(row, parse_date(row["transaction_date"]), status, increment)


def candidate_for(payload):
    row = copy.deepcopy(payload)
    row["source_account"]["participant"] = "12345678"
    row["destination_account"]["participant"] = "12345678"
    row["source_account"]["branch"] = row["destination_account"]["branch"] = "0001"
    row["source_account"]["owner"]["document_number"] = "00000000001"
    row["source_account"]["account_number"] = "account-1"
    row["destination_account"]["owner"]["document_number"] = "00000000002"
    row["destination_account"]["account_number"] = "account-2"
    return row


def generated_graph(seed=500_001, kind="temporal_fast"):
    candidate, records, _, _ = source_scenario(seed, "test", kind)
    _, past, _, _, _ = replay(candidate, records, Policy())
    events = [
        GraphEvent(r.tx.model_dump(mode="json"), r.tx.transaction_date, r.status, r.increment) for r in past
    ]
    return candidate, events, build_temporal_graph(candidate, events)


def test_payment_and_device_relations_are_separate_and_directional(payload):
    candidate = candidate_for(payload)
    graph = build_temporal_graph(candidate, [event(candidate, "past", 3, 1, 60)])
    source, destination, device, holder = graph.targets
    assert (source, destination) in set(map(tuple, graph.edges[0].T))
    assert (destination, source) not in set(map(tuple, graph.edges[0].T))
    assert (destination, source) in set(map(tuple, graph.edges[1].T))
    assert (source, device) in set(map(tuple, graph.edges[2].T))
    assert (device, source) in set(map(tuple, graph.edges[3].T))
    assert (holder, source) in set(map(tuple, graph.edges[4].T))
    assert (source, holder) in set(map(tuple, graph.edges[5].T))


def test_receiving_from_suspect_is_not_the_same_as_paying_a_suspect(payload):
    candidate = candidate_for(payload)
    evidence = [
        event(candidate, "own-one", 10, 90, 180, increment=20),
        event(candidate, "own-two", 10, 90, 120, increment=20),
    ]
    received = build_temporal_graph(candidate, evidence + [event(candidate, "received", 10, 1, 60)])
    paid = build_temporal_graph(candidate, evidence + [event(candidate, "paid", 1, 10, 60)])
    np.testing.assert_allclose(received.transaction_features[4:6], [0.4, 0])
    np.testing.assert_allclose(paid.transaction_features[4:6], [0, 0.4])


def test_holder_identity_deduplicates_accounts_on_a_shared_device(payload):
    candidate = candidate_for(payload)
    first = event(candidate, "first", 1, 2, 60)
    second = event(candidate, "second", 1, 2, 30)
    second.payload["source_account"]["account_number"] = "other-account-same-holder"
    graph = build_temporal_graph(candidate, [first, second])
    assert graph.transaction_features[-1] == pytest.approx(0.1)
    third = event(candidate, "third", 3, 2, 10)
    assert build_temporal_graph(candidate, [first, second, third]).transaction_features[-1] == pytest.approx(
        0.2
    )


@pytest.mark.parametrize("minutes,expected", [(29.999, 0.25), (30, 0.25), (30.001, 0), (0, 0)])
def test_repasses_require_strict_time_order_and_inclusive_thirty_minute_window(payload, minutes, expected):
    candidate = candidate_for(payload)
    rows = [event(candidate, "receipt", 3, 1, 60), event(candidate, "outgoing", 1, 10, 60 - minutes)]
    graph = build_temporal_graph(candidate, rows)
    assert graph.transaction_features[8] == pytest.approx(expected)


def test_receipt_cannot_be_used_twice_and_risky_unrelated_payment_is_not_a_risky_repass(payload):
    candidate = candidate_for(payload)
    evidence = [
        event(candidate, "risk1", 10, 90, 180, increment=20),
        event(candidate, "risk2", 10, 90, 120, increment=20),
    ]
    rows = [
        event(candidate, "in", 3, 1, 60),
        event(candidate, "out", 1, 4, 55),
        event(candidate, "another-out", 1, 4, 50),
        event(candidate, "risky-unmatched", 1, 10, 10),
    ]
    graph = build_temporal_graph(candidate, evidence + rows)
    assert graph.transaction_features[8] == pytest.approx(0.25)
    assert graph.transaction_features[10] == 0


def test_old_edges_attenuate_even_when_the_neighbor_is_the_only_contact():
    x = np.ones((2, 3), dtype=np.float32)
    edges = np.array([[0], [1]])
    recent = relation_mean(x, edges, np.array([1], dtype=np.float32))
    old = relation_mean(x, edges, np.array([0.5], dtype=np.float32))
    np.testing.assert_allclose(old[1], recent[1] / 2)


def test_future_receipt_old_own_evidence_retries_and_labels_do_not_leak(payload):
    candidate = candidate_for(payload)
    previous = event(candidate, "valid", 3, 1, 60)
    graph = build_temporal_graph(candidate, [previous])
    future = replace(
        event(candidate, "future-reception", 10, 1, 30, increment=25),
        received_at=parse_date(candidate["transaction_date"]) + timedelta(seconds=1),
    )
    copied = copy.deepcopy(previous)
    copied.payload.update(
        fraud_label=1, risk_score=100, entity_risk={"relationships": {"exposure_score": 100}}
    )
    changed = build_temporal_graph(candidate, [copied, copied, future])
    np.testing.assert_array_equal(graph.x, changed.x)
    np.testing.assert_array_equal(graph.transaction_features, changed.transaction_features)
    old = event(candidate, "at-window-cutoff", 10, 1, 1440, increment=25)
    assert build_temporal_graph(candidate, [old]).x[:, 11].max() == 0


def test_rejection_keeps_independent_evidence_but_does_not_create_payment_edge(payload):
    candidate = candidate_for(payload)
    rejected = event(candidate, "rejection", 3, 1, 30, increment=25, status="rejected")
    graph = build_temporal_graph(candidate, [rejected])
    assert graph.history_count == 0
    assert graph.x[:, 11].max() == pytest.approx(0.25)
    assert graph.edges[0].shape[1] == 1  # Only the candidate's known relationship.


def test_truncated_conflicting_and_unbounded_history_are_refused(payload):
    candidate = candidate_for(payload)
    original = event(candidate, "past", 3, 1, 60)
    with pytest.raises(ValueError, match="Incomplete"):
        build_temporal_graph(candidate, [], history_truncated=True)
    with pytest.raises(ValueError, match="bounded"):
        build_temporal_graph(candidate, [replace(original, own_increment=26)])
    with pytest.raises(ValueError, match="Conflicting"):
        build_temporal_graph(candidate, [original, replace(original, status="rejected")])
    with pytest.raises(ValueError, match="300-event"):
        build_temporal_graph(candidate, [event(candidate, f"id-{i}", 3, 1, 60) for i in range(301)])


def test_fast_and_slow_pair_have_same_legacy_prediction_but_distinct_temporal_features():
    fast, fast_events, fast_graph = generated_graph(kind="temporal_fast")
    slow, slow_events, slow_graph = generated_graph(kind="temporal_slow")
    model = GraphSageModel(DEFAULT_MODEL)
    fast_old = model.predict(build_graph(fast, [e.payload for e in fast_events]))
    slow_old = model.predict(build_graph(slow, [e.payload for e in slow_events]))
    assert fast_old == pytest.approx(slow_old, abs=1e-6)
    assert fast_graph.transaction_features[8] >= 0.5
    assert slow_graph.transaction_features[8] == 0


@pytest.mark.parametrize("split,month", [("train", 1), ("validation", 5), ("test", 9)])
def test_synthetic_split_dates_and_openings_are_valid(split, month):
    candidate, records, _, _ = source_scenario(123, split, "temporal_fast")
    assert parse_date(candidate["transaction_date"]).month == month
    for row in [candidate, *records]:
        for side in ("source_account", "destination_account"):
            assert parse_date(row[side]["opening_date"]) <= parse_date(row["transaction_date"])
            assert "_original_opening" not in row[side]


@pytest.mark.parametrize("seed", [42, 43, 44])
def test_exported_v2_is_safe_finite_permutation_invariant_and_not_loadable_as_v1(seed):
    path = ROOT / "models" / f"gnn-directed-temporal-v2-seed-{seed}.json"
    model = TemporalModel(path)
    candidate, events, graph = generated_graph()
    prediction = model.predict(graph)
    assert 0 <= prediction <= 1
    assert prediction == pytest.approx(model.predict(build_temporal_graph(candidate, events[::-1])), abs=1e-6)
    other_intent = copy.deepcopy(candidate)
    other_intent["fraud_label"] = 1
    assert model.predict(build_temporal_graph(other_intent, events)) == prediction
    assert GraphRiskService("shadow", path).model is None


def test_comparison_selects_on_validation_and_records_parity_for_every_seed():
    report = json.loads((ROOT / "models/gnn-directed-temporal-v2.metrics.json").read_text())
    assert report["design"]["seeds"] == [42, 43, 44]
    assert len(report["runs"]) == 9
    assert set(RELATIONS) == {"paid_to", "received_from", "uses_device", "used_by", "owns", "owned_by"}
    assert len(TRANSACTION_FEATURES) == 12
    for run in report["runs"]:
        for budget, comparison in run["comparison"].items():
            assert comparison["validation"]["false_positive_rate"] <= float(budget)
            assert comparison["validation"]["threshold"] == comparison["test"]["threshold"]
        if run["method"] == "v2_directed":
            assert run["export_max_absolute_error"] < 1e-5


@pytest.mark.parametrize("change", ["nan_weight", "wrong_shape", "node_schema", "label_target"])
def test_experimental_loader_refuses_unsafe_weights_and_incompatible_semantics(tmp_path, change):
    data = json.loads((ROOT / "models/gnn-directed-temporal-v2-seed-42.json").read_text())
    if change == "nan_weight":
        data["weights"]["w1"][0][0] = float("nan")
    elif change == "wrong_shape":
        data["weights"]["w2"] = [[0]]
    elif change == "node_schema":
        data["node_features"] = data["node_features"][::-1]
    else:
        data["label_target"] = "different_target"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        TemporalModel(path)


@pytest.mark.parametrize("score", [0, 0.5, 1])
def test_constant_float32_scores_can_abstain_without_breaking_zero_fpr_budget(score):
    scores = np.array([score, score], dtype=np.float32)
    threshold = select_threshold([0, 1], scores, 0)
    assert not (scores.astype(np.float64) >= threshold).any()


def test_threshold_does_not_split_tied_legitimate_and_fraud_scores():
    scores = np.array([0.8, 0.8, 0.9, 0.1])
    threshold = select_threshold([0, 1, 1, 0], scores, 0)
    assert threshold == 0.9


def test_entity_identities_do_not_overlap_across_training_validation_and_test():
    documents = []
    for split in ("train", "validation", "test"):
        candidate, records, _, _ = source_scenario(123, split, "temporal_fast")
        documents.append(
            {
                row[side]["owner"]["document_number"]
                for row in [candidate, *records]
                for side in ("source_account", "destination_account")
            }
        )
    assert not documents[0] & documents[1]
    assert not documents[0] & documents[2]
    assert not documents[1] & documents[2]
