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
                        "score_semantics": "heuristic_not_probability",
                        "reasons": ["amount_requires_two_factor"],
                        "decision_source": "risk_score",
                        "policy": {"version": "pix-score-v2"},
                    },
                }
            ]
        }
    )

    key: str
    status: Literal["approved", "rejected", "two_factor_required"]
    metadata: dict[str, Any] = Field(
        description=(
            "Saved decision evidence. Policy pix-score-v2 includes risk_score (0..100 heuristic points), "
            "risk_level, triggered_rules with weights and effective contributions, group_scores, "
            "hard_limits and the complete policy snapshot. Earlier pix-v1 analyses remain unchanged."
        )
    )

    @classmethod
    def from_model(cls, analysis: PixAnalysis):
        return cls(
            key=analysis.analysis_key,
            status=analysis.status,
            metadata=analysis.decision_metadata,
        )
