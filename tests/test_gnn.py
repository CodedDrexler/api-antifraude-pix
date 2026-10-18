import copy
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from src.constants import Policy
from src.controllers.decision_engine import DecisionEngine
from src.gnn.graph import build_graph
from src.gnn.model import GraphSageModel
from src.gnn.service import DEFAULT_MODEL, GraphRiskService, combine_graph_risk
from src.gnn.synthetic import scenario
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate


def base_decision(payload):
    return DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload), History(0, 0, 0, False, False, 1, 1000)
    )


def test_real_model_weights_are_finite_and_topology_changes_prediction():
    candidate, history, _, _ = scenario(7, "test", "ring")
    graph = build_graph(candidate, history)
    model = GraphSageModel(DEFAULT_MODEL)
    normal = model.predict(graph)
    without_edges = model.predict(replace(graph, edges=np.zeros((2, 0), dtype=np.int64)))
    assert 0 <= normal <= 1
    assert abs(normal - without_edges) > 1e-5


def test_future_events_and_candidate_retries_do_not_enter_graph():
    candidate, history, _, _ = scenario(8, "test", "ring")
    original = build_graph(candidate, history)
    future = copy.deepcopy(history[0])
    future["id"] = "future"
    future["transaction_date"] = "2027-01-01T00:00:00Z"
    extra = build_graph(candidate, history + [future, candidate, history[0]])
    np.testing.assert_array_equal(original.x, extra.x)
    np.testing.assert_array_equal(original.edges, extra.edges)
    assert original.history_count == extra.history_count


def test_label_or_rule_decision_is_never_a_graph_feature():
    candidate, history, _, _ = scenario(9, "test", "ring")
    original = build_graph(candidate, history)
    for record in history:
        record.update(status="rejected", fraud_label=1, risk_score=100)
    changed = build_graph(candidate, history)
    np.testing.assert_array_equal(original.x, changed.x)
    np.testing.assert_array_equal(original.transaction_features, changed.transaction_features)


def test_graph_score_is_stable_when_history_order_changes():
    candidate, history, _, _ = scenario(10, "test", "ring")
    model = GraphSageModel(DEFAULT_MODEL)
    assert model.predict(build_graph(candidate, history)) == model.predict(
        build_graph(candidate, history[::-1])
    )


@pytest.mark.parametrize(
    ("mode", "expected"), [("off", "disabled"), ("shadow", "unavailable"), ("contribute", "unavailable")]
)
def test_missing_model_falls_back_without_fabricating_score(tmp_path, payload, mode, expected):
    service = GraphRiskService(mode, tmp_path / "missing.json")
    result = service.assess(payload, [])
    assert result["status"] == expected
    assert result["gnn_score"] is None
    assert result["proposed_points"] == 0
    status, metadata = base_decision(payload)
    combined, enriched = combine_graph_risk(status, metadata, result)
    assert combined == status and enriched["risk_score"] == metadata["risk_score"]


def test_invalid_model_is_unavailable(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"architecture":"unknown"}')
    assert GraphRiskService("shadow", path).model is None


def test_unsafe_model_parameters_are_rejected(tmp_path):
    artifact = json.loads(Path(DEFAULT_MODEL).read_text())
    artifact["weights"]["w1"][0][0] = float("nan")
    path = tmp_path / "nan.json"
    path.write_text(json.dumps(artifact))
    assert GraphRiskService("shadow", path).model is None


def test_invalid_mode_fails_fast():
    with pytest.raises(ValueError):
        GraphRiskService("typo")


def test_sparse_and_truncated_history_abstain(payload):
    candidate, history, _, _ = scenario(11, "test", "ring")
    service = GraphRiskService()
    assert service.assess(payload, [])["status"] == "insufficient_history"
    assert service.assess(candidate, history, truncated=True)["status"] == "history_truncated"


def test_shadow_mode_never_changes_rule_decision(payload):
    candidate, history, _, _ = scenario(12, "test", "ring")
    result = GraphRiskService("shadow").assess(candidate, history)
    assert result["status"] == "scored"
    status, metadata = base_decision(payload)
    combined, enriched = combine_graph_risk(status, metadata, result)
    assert combined == status
    assert enriched["risk_score"] == metadata["risk_score"]
    assert enriched["gnn"]["applied_points"] == 0
    assert metadata.get("gnn") is None  # Combination does not mutate the rule snapshot.


def high_graph_result():
    return {
        "mode": "contribute",
        "status": "scored",
        "gnn_score": 95,
        "proposed_points": 20,
        "threshold": 80,
        "experimental": True,
        "training_data": "synthetic",
        "model_version": "test-model",
    }


def test_opt_in_graph_contribution_can_request_two_factor(payload):
    payload["source_account"]["opening_date"] = payload["transaction_date"]
    status, metadata = base_decision(payload)
    assert metadata["risk_score"] == 15
    combined, enriched = combine_graph_risk(status, metadata, high_graph_result())
    assert enriched["risk_score"] == 35
    assert enriched["rule_risk_score"] == 15
    assert enriched["gnn"]["applied_points"] == 20
    assert combined == "two_factor_required"
    assert enriched["policy"]["version"] == "pix-score-v6+gnn-experimental-v1"


def test_graph_cannot_reduce_a_hard_rejection_or_exceed_score_cap(payload):
    payload["amount"] = 3_000_000
    payload["source_account"]["opening_date"] = payload["transaction_date"]
    status, metadata = DecisionEngine(Policy()).evaluate(
        PixTransactionCreate.model_validate(payload), History(0, 0, 0, False, False, 1, 3_000_000)
    )
    combined, enriched = combine_graph_risk(status, metadata, high_graph_result())
    assert combined == "rejected"
    assert enriched["decision_source"] == "hard_limit"
    assert enriched["risk_score"] == 100
    assert enriched["gnn"]["applied_points"] == 5
    assert enriched["risk_factors_sum"] == 115
    assert sum(f["score"] for f in enriched["risk_factors"]) == enriched["risk_factors_sum"]
    assert (
        sum(rule["contribution"] for rule in enriched["triggered_rules"]) - enriched["score_cap_reduction"]
        == 100
    )


def test_graph_factor_weight_is_applied_and_explained(payload):
    status, metadata = base_decision(payload)
    metadata["policy"]["version"] = "custom-policy-v3"
    metadata["policy"]["scoring"]["factor_weights"]["graph"] = 50
    combined, enriched = combine_graph_risk(status, metadata, high_graph_result())
    assert combined == "approved"
    assert enriched["risk_score"] == 10
    assert next(f for f in enriched["risk_factors"] if f["name"] == "graph")["weight"] == 50
    assert enriched["policy"]["version"] == "custom-policy-v3+gnn-experimental-v1"
    assert next(f for f in enriched["risk_factors"] if f["name"] == "graph")["score"] == 10
    assert enriched["triggered_rules"][-1]["risk_factor"] == "graph"
    assert enriched["triggered_rules"][-1]["weight"] == 20
    assert enriched["triggered_rules"][-1]["contribution"] == 10


def test_zero_graph_factor_does_not_count_as_rejection_evidence(payload):
    status, metadata = base_decision(payload)
    metadata["policy"]["scoring"]["factor_weights"]["graph"] = 0
    combined, enriched = combine_graph_risk(status, metadata, high_graph_result())
    assert combined == status
    assert enriched["risk_score"] == metadata["risk_score"]
    assert enriched["risk_group_count"] == metadata["risk_group_count"]
    assert next(f for f in enriched["risk_factors"] if f["name"] == "graph")["score"] == 0


def test_report_records_export_parity_and_training_improvement():
    report = json.loads(Path(DEFAULT_MODEL).with_suffix(".metrics.json").read_text())
    assert report["final_training_loss"] < report["initial_training_loss"]
    assert report["export_max_absolute_error"] < 1e-5
    assert report["split"]["entity_disjoint"] is True
    assert report["split"]["chronological_months"] == [1, 5, 9]


def test_entity_ids_do_not_overlap_between_training_and_test():
    train, _, _, _ = scenario(1, "train")
    test, _, _, _ = scenario(1, "test")
    assert (
        train["source_account"]["owner"]["document_number"]
        != test["source_account"]["owner"]["document_number"]
    )
    assert train["source"]["device_id"] != test["source"]["device_id"]
