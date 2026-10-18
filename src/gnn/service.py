"""Experimental model inference and a bounded, opt-in contribution to the rule score."""

import copy
import math
from pathlib import Path

from src.gnn.graph import build_graph
from src.gnn.model import GraphSageModel
from src.risk.scoring import rule_evidence, score_decision, summarize_factor, summarize_score
from src.risk.types import RuleMatch

MAX_HISTORY = 300
HISTORY_DAYS = 30
MIN_HISTORY = 3
MODEL_THRESHOLD = 80
MAX_POINTS = 20
DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "models" / "gnn-synthetic-v1.json"


class GraphRiskService:
    def __init__(self, mode="shadow", model_path=DEFAULT_MODEL):
        if mode not in {"off", "shadow", "contribute"}:
            raise ValueError("GNN_MODE must be off, shadow or contribute")
        self.mode = mode
        self.model = None
        if mode != "off":
            try:
                self.model = GraphSageModel(model_path)
            except (OSError, ValueError, KeyError, TypeError):
                # Optional model problems never turn a valid Pix into a server error.
                pass

    @property
    def enabled(self):
        return self.mode != "off" and self.model is not None

    def assess(self, candidate, history, truncated=False):
        result = {
            "mode": self.mode,
            "experimental": True,
            "training_data": "synthetic",
            "score_semantics": "uncalibrated_model_output_not_fraud_probability",
            "gnn_score": None,
            "proposed_points": 0,
            "applied_points": 0,
            "threshold": MODEL_THRESHOLD,
            "maximum_points": MAX_POINTS,
            "minimum_history": MIN_HISTORY,
            "history_days": HISTORY_DAYS,
            "history_limit": MAX_HISTORY,
        }
        if self.mode == "off":
            return {**result, "status": "disabled"}
        if self.model is None:
            return {**result, "status": "unavailable"}
        result.update(model_version=self.model.version, model_sha256=self.model.sha256)
        if truncated:
            return {**result, "status": "history_truncated"}
        if len(history) < MIN_HISTORY:
            return {**result, "status": "insufficient_history"}
        try:
            graph = build_graph(candidate, history)
            if graph.history_count < MIN_HISTORY:
                return {**result, "status": "insufficient_history"}
            value = self.model.predict(graph) * 100
            if not math.isfinite(value):
                raise ValueError("Non-finite model output")
            result.update(
                status="scored",
                gnn_score=round(value, 4),
                proposed_points=MAX_POINTS if value >= MODEL_THRESHOLD else 0,
                graph_nodes=len(graph.x),
                graph_edges=graph.edges.shape[1],
                history_transactions=graph.history_count,
            )
            return result
        except (ValueError, TypeError, KeyError, OverflowError):
            return {**result, "status": "inference_failed"}


def combine_graph_risk(status, metadata, graph_result):
    metadata = copy.deepcopy(metadata)
    metadata["gnn"] = copy.deepcopy(graph_result)
    metadata["rule_risk_score"] = metadata["risk_score"]
    metadata["policy"]["gnn"] = {
        key: value
        for key, value in graph_result.items()
        if key
        in {
            "mode",
            "threshold",
            "maximum_points",
            "model_sha256",
            "model_version",
            "experimental",
            "training_data",
            "minimum_history",
            "history_days",
            "history_limit",
        }
    }
    if graph_result["mode"] != "contribute" or graph_result["status"] != "scored":
        return status, metadata
    scoring = metadata["policy"]["scoring"]
    proposed_points = graph_result["proposed_points"]
    metadata["policy"]["version"] += "+gnn-experimental-v1"
    if proposed_points:
        factor_weight = scoring["factor_weights"]["graph"]
        match = RuleMatch("gnn_relational_pattern", graph_result["gnn_score"], graph_result["threshold"])
        rule = rule_evidence(match, "graph", proposed_points, factor_weight)
        factor = summarize_factor("graph", [rule], MAX_POINTS, factor_weight)
        metadata["triggered_rules"].append(rule)
        metadata["reasons"] = [rule["code"] for rule in metadata["triggered_rules"]]
        metadata["raw_score"] += proposed_points
        metadata["group_scores"]["graph"] = {key: factor[key] for key in ("raw_score", "score", "cap")}
        metadata["risk_factors"].append(factor)
    metadata.update(summarize_score(metadata["group_scores"], scoring))
    # Applied points can be smaller than the factor contribution at the global cap.
    metadata["gnn"]["applied_points"] = metadata["risk_score"] - metadata["rule_risk_score"]
    status, source = score_decision(metadata, scoring)
    if status == "approved" and metadata["decision_source"] in {"first_transaction", "insufficient_history"}:
        return "two_factor_required", metadata
    metadata["decision_source"] = source
    return status, metadata
