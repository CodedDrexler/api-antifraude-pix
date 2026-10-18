from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.dtos.rule_aliases import rule_alias
from src.models.pix import PixAnalysis


class PixAnalysisDTO(BaseModel):
    """Internal decision and immutable audit evidence, never serialized directly by HTTP."""

    key: str
    status: Literal["approved", "rejected", "two_factor_required"]
    metadata: dict[str, Any]

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

    def to_response(self, *, include_details: bool = False) -> "PixResponseDTO":
        evidence = self.metadata
        # Prefer the saved v2 assessment; old immutable analyses can still contain v1.
        graph = evidence.get("gnn_v2") or evidence.get("gnn") or {}
        metadata = PixResponseMetadata(
            risk_score=evidence.get("risk_score", 0),
            untrust_score=graph.get("gnn_score"),
            bank_notification_required=evidence.get("bank_notification", {}).get("required", False),
        )
        if include_details:
            metadata.rules = self.applied_rule_names()
        return PixResponseDTO(key=self.key, status=self.status, metadata=metadata)

    def applied_rule_names(self) -> list[str]:
        evidence = self.metadata
        causes = [cause["rule_id"] for cause in evidence.get("decision_causes", [])]
        if "triggered_rules" in evidence:
            codes = [
                rule["code"]
                for rule in evidence["triggered_rules"]
                if rule.get("contribution", 1) > 0 or rule.get("hard_limit") or rule["code"] in causes
            ]
        else:
            # Older snapshots did not record each rule's effective contribution.
            codes = [
                code for factor in self.normalized_metadata()["risk_factors"] for code in factor["rules"]
            ]
            if not codes:
                codes = evidence.get("reasons", [])
        codes = dict.fromkeys([*codes, *causes])
        return [rule_alias(code) for code in codes if code != "no_rule_triggered"]


class PixResponseMetadata(BaseModel):
    risk_score: int = Field(
        ge=0, le=100, description="Score das regras, de 0 a 100; não é probabilidade de fraude."
    )
    untrust_score: float | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        ge=0,
        le=100,
        description=(
            "Score de desconfiança do grafo, de 0 a 100; não é probabilidade de fraude nem o acumulado da conta. "
            "Presente somente quando há avaliação disponível. Em contribute, pode elevar aprovação para 2FA; "
            "não altera risk_score. Em shadow, somente observa."
        ),
    )
    bank_notification_required: bool = Field(
        description="Indica necessidade de aviso ao banco; não envia aviso."
    )
    rules: list[str] = Field(
        default_factory=list, description="Nomes das regras aplicadas; somente com include_details=true."
    )


class PixResponseDTO(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "key": "b3f1c2e0-7d4a-4c1e-9a52-1f0e6c9d2a77",
                    "status": "two_factor_required",
                    "metadata": {
                        "risk_score": 30,
                        "bank_notification_required": False,
                    },
                }
            ]
        }
    )

    key: str
    status: Literal["approved", "rejected", "two_factor_required"]
    metadata: PixResponseMetadata
