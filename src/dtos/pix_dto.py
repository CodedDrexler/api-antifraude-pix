from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.models.pix import PixAnalysis


class PixAnalysisDTO(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "key": "b3f1c2e0-7d4a-4c1e-9a52-1f0e6c9d2a77",
                    "status": "two_factor_required",
                    "metadata": {
                        "risk_score": 30,
                        "risk_level": "elevated",
                        "decision_source": "first_transaction",
                        "policy_version": "pix-score-v7",
                        "processing_time_ms": 8.412,
                        "risk_factors_sum": 30,
                        "account_untrust": {
                            "label": "Desconfiança acumulada da conta",
                            "score": 0,
                            "increment": 0,
                            "risk_events": 0,
                            "action": "none",
                            "window_hours": 24,
                        },
                        "bank_notification": {
                            "required": False,
                            "status": "not_required",
                            "reason": None,
                            "threshold": 60,
                            "threshold_crossed": False,
                        },
                        "risk_factors": [
                            {
                                "name": "exposure",
                                "label": "Histórico inicial",
                                "weight": 100,
                                "score": 30,
                                "rules": ["first_transaction"],
                            }
                        ],
                    },
                }
            ]
        }
    )

    key: str
    status: Literal["approved", "rejected", "two_factor_required"]
    metadata: dict[str, Any] = Field(
        description=(
            "Resumo da decisão: score heurístico de 0 a 100, fatores com nome legível, pontos e regras. "
            "Score não é probabilidade de fraude. risk_factors_sum precede o teto de 100. "
            "processing_time_ms mede a análise antes da gravação; null em registros antigos. "
            "Use include_details=true para consultar as evidências e a política salvas."
        )
    )

    @classmethod
    def from_model(cls, analysis: PixAnalysis):
        result = cls(
            key=analysis.analysis_key,
            status=analysis.status,
            metadata=analysis.decision_metadata,
        )
        return result.model_copy(update={"metadata": result.normalized_metadata()})

    def normalized_metadata(self):
        evidence = self.metadata.copy()
        factors = evidence.get("risk_factors")
        if factors is None:
            factors = {
                group: {
                    "weight": 100,
                    "score": values["score"],
                    "rules": [r["code"] for r in evidence.get("triggered_rules", []) if r["group"] == group],
                }
                for group, values in evidence.get("group_scores", {}).items()
            }
        if isinstance(factors, dict):
            factors = [{**factor, "name": name} for name, factor in factors.items()]
        evidence["risk_factors"] = factors
        evidence["risk_factors_sum"] = sum(factor["score"] for factor in factors)
        evidence.setdefault("processing_time_ms", None)
        return evidence

    def compact(self):
        evidence = self.normalized_metadata()
        factors = evidence["risk_factors"]
        summary = {
            key: evidence[key] for key in ("risk_score", "risk_level", "decision_source") if key in evidence
        }
        summary.update(
            policy_version=evidence.get("policy", {}).get("version"),
            processing_time_ms=evidence.get("processing_time_ms"),
            risk_factors_sum=evidence["risk_factors_sum"],
            risk_factors=[
                {key: factor[key] for key in ("name", "label", "weight", "score", "rules") if key in factor}
                for factor in factors
            ],
        )
        if "duplicate_payment" in evidence:
            summary["duplicate_payment"] = evidence["duplicate_payment"]
        if "decision_causes" in evidence:
            summary["decision_causes"] = evidence["decision_causes"]
        if "contextual_trust" in evidence:
            trust = evidence["contextual_trust"]
            summary["contextual_trust"] = {
                key: trust[key]
                for key in ("applied", "reason", "profile_points_before", "profile_points_after")
            }
        if evidence.get("hard_limits"):
            summary["hard_limits"] = evidence["hard_limits"]
        if "account_untrust" in evidence:
            summary["account_untrust"] = {
                key: evidence["account_untrust"][key]
                for key in ("label", "score", "increment", "risk_events", "action", "window_hours")
            }
            summary["bank_notification"] = evidence["bank_notification"]
        if not factors and evidence.get("reasons") not in (None, ["no_rule_triggered"]):
            summary["reasons"] = evidence["reasons"]
        if evidence.get("gnn", {}).get("mode") not in (None, "off"):
            summary["gnn"] = {
                key: evidence["gnn"][key]
                for key in ("mode", "status", "gnn_score", "applied_points")
                if key in evidence["gnn"]
            }
        if evidence.get("gnn_v2", {}).get("mode") not in (None, "off"):
            summary["gnn_v2"] = {
                key: evidence["gnn_v2"][key]
                for key in (
                    "mode",
                    "status",
                    "gnn_score",
                    "applied_points",
                    "model_version",
                    "feature_version",
                )
                if key in evidence["gnn_v2"]
            }
        if "entity_risk" in evidence:
            entity = evidence["entity_risk"]
            summary["entity_risk"] = {
                "mode": entity["mode"],
                "status": entity["status"],
                "registry_status": entity["registry_status"],
                "relationship_coverage": entity["relationships"]["coverage"],
                "own_entity_untrust": entity["own_entity"]["score"],
                "own_history_status": entity["own_entity"]["history_status"],
                "related_exposure_score": entity["relationships"]["exposure_score"],
                "confirmed_incidents": entity["relationships"]["confirmed_incidents"],
                "proposed_action": entity["proposed_action"],
                "proposed_points": entity["proposed_points"],
                "applied_points": entity["applied_points"],
            }
        return self.model_copy(update={"metadata": summary})
