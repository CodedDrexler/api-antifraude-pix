"""Live v2 observation: bounded history, explicit abstention, no decision contribution."""

import math
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

from src.controllers.account_untrust import OWN_EVIDENCE_VERSION
from src.gnn.temporal_graph import FEATURE_VERSION, TRANSACTION_FEATURES, GraphEvent, build_temporal_graph
from src.gnn.temporal_model import TemporalModel

DEFAULT_TEMPORAL_MODEL = Path(__file__).resolve().parents[2] / "models/gnn-directed-temporal-v2-seed-42.json"
MAX_TEMPORAL_HISTORY = 300
MAX_OWN_EVIDENCE = 300
MAX_GRAPH_ENTITIES = 100
TEMPORAL_HOPS = 2


@dataclass(frozen=True)
class TemporalHistory:
    events: list[GraphEvent] = field(default_factory=list)
    own_events: list[GraphEvent] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    abstention: str | None = None


class TemporalGraphService:
    def __init__(self, mode="shadow", model_path=DEFAULT_TEMPORAL_MODEL):
        if mode not in {"off", "shadow"}:
            raise ValueError("GNN_V2_MODE must be off or shadow; contribution is not enabled")
        self.mode = mode
        self.model = None
        if mode != "off":
            try:
                self.model = TemporalModel(model_path)
            except (OSError, ValueError, KeyError, TypeError, OverflowError):
                pass

    @property
    def enabled(self):
        return self.mode != "off" and self.model is not None

    def assess(self, candidate, received_at, history: TemporalHistory):
        result = {
            "mode": self.mode,
            "experimental": True,
            "training_data": "synthetic",
            "label_target": "synthetic_source_mule_intent",
            "score_semantics": "uncalibrated_model_output_not_fraud_probability",
            "feature_version": FEATURE_VERSION,
            "gnn_score": None,
            "applied_points": 0,
            "decision_override": False,
            "history_limit": MAX_TEMPORAL_HISTORY,
            "own_evidence_limit": MAX_OWN_EVIDENCE,
            "entity_limit": MAX_GRAPH_ENTITIES,
            "hops": TEMPORAL_HOPS,
            "history_days": 30,
            "own_window_hours": 24,
            "own_evidence_version": OWN_EVIDENCE_VERSION,
            "training_evidence_policy": "pix-score-v7",
            "minimum_history": 3,
            "data_basis": "non_rejected_attempts_not_confirmed_settlement",
            "event_time_cutoff": candidate["transaction_date"],
            "received_time_cutoff": received_at.isoformat(),
            "coverage": history.coverage,
            "history_status": "not_queried" if not self.enabled else "complete",
            "processing_time_ms": 0.0,
        }
        if self.mode == "off":
            return {**result, "status": "disabled"}
        if self.model is None:
            return {**result, "status": "unavailable"}
        result.update(model_version=self.model.version, model_sha256=self.model.sha256)
        if history.abstention:
            return {**result, "status": history.abstention, "history_status": "incomplete"}
        started = perf_counter()
        try:
            graph = build_temporal_graph(
                candidate, history.events, received_at=received_at, own_events=history.own_events
            )
            result.update(
                history_transactions=graph.history_count, own_evidence_events=len(history.own_events)
            )
            if graph.history_count < result["minimum_history"]:
                result["status"] = "insufficient_history"
            else:
                value = self.model.predict(graph) * 100
                if not math.isfinite(value) or not 0 <= value <= 100:
                    raise ValueError("Non-finite or invalid model output")
                result.update(
                    status="scored",
                    gnn_score=round(value, 4),
                    graph_nodes=len(graph.x),
                    graph_edges=sum(part.shape[1] for part in graph.edges),
                    normalized_transaction_features=dict(
                        zip(TRANSACTION_FEATURES, graph.transaction_features.tolist(), strict=True)
                    ),
                )
        except (ValueError, TypeError, KeyError, OverflowError, IndexError):
            result.update(status="inference_failed", history_status="invalid_or_unsupported")
        finally:
            result["processing_time_ms"] = round((perf_counter() - started) * 1000, 3)
        return result
