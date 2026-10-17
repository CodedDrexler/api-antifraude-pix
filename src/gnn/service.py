"""Experimental model inference and a bounded, opt-in contribution to the rule score."""

import copy
import math
from pathlib import Path

from src.gnn.graph import build_graph
from src.gnn.model import GraphSageModel

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
    points = graph_result["proposed_points"]
    metadata["policy"]["version"] = "pix-score-v2+gnn-experimental-v1"
    if points:
        metadata["triggered_rules"].append(
            {
                "code": "gnn_relational_pattern",
                "group": "graph",
                "weight": points,
                "contribution": points,
                "observed": graph_result["gnn_score"],
                "threshold": graph_result["threshold"],
                "hard_limit": False,
            }
        )
        metadata["reasons"] = [rule["code"] for rule in metadata["triggered_rules"]]
        metadata["raw_score"] += points
        metadata["group_scores"]["graph"] = {"raw_score": points, "score": points, "cap": MAX_POINTS}
        metadata["risk_group_count"] += 1
    total = sum(group["score"] for group in metadata["group_scores"].values())
    metadata["risk_score"] = min(100, total)
    metadata["score_cap_reduction"] = max(0, total - 100)
    # This is the change to the final score, which can be smaller than the proposed points at the cap.
    metadata["gnn"]["applied_points"] = metadata["risk_score"] - metadata["rule_risk_score"]
    scoring = metadata["policy"]["scoring"]
    score = metadata["risk_score"]
    metadata["risk_level"] = (
        "high"
        if score >= scoring["rejection_threshold"]
        else "elevated"
        if score >= scoring["two_factor_threshold"]
        else "low"
    )
    if metadata["hard_limits"]:
        return "rejected", metadata
    if (
        score >= scoring["rejection_threshold"]
        and metadata["risk_group_count"] >= scoring["minimum_rejection_groups"]
    ):
        return "rejected", {**metadata, "decision_source": "risk_score"}
    if score >= scoring["two_factor_threshold"]:
        return "two_factor_required", {**metadata, "decision_source": "risk_score"}
    return "approved", {**metadata, "decision_source": "risk_score"}
