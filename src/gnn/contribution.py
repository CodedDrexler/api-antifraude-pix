"""Bound a synthetic-validated prototype intervention to its frozen artifacts."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.constants import Policy

DEFAULT_CONTRIBUTION_POLICY = Path(__file__).resolve().parents[2] / "config/gnn-contribution.json"


def policy_fingerprint(policy: Policy) -> str:
    encoded = json.dumps(asdict(policy), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class ContributionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: Literal["gnn-2fa-v1"]
    method: Literal["score_only_2fa/confidence_budget"]
    maximum_action: Literal["two_factor_required"]
    model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    baseline_policy_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    threshold: float = Field(gt=0, le=1, allow_inf_nan=False)
    validation_report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def from_file(cls, path):
        raw = Path(path).read_bytes()
        if len(raw) > 10_000:
            raise ValueError("Contribution policy too large")
        return cls.model_validate_json(raw)


def combine_temporal_risk(status, metadata, policy, mode, contribution):
    """Only escalate an approval to 2FA; never change points, evidence or other controls."""
    graph = metadata["gnn_v2"]
    graph["contribution_status"] = "observation_only"
    if contribution is not None:
        graph["contribution_policy"] = contribution.model_dump()
    if mode != "contribute":
        return status
    if contribution is None:
        graph["contribution_status"] = "policy_unavailable"
    elif graph.get("model_sha256") != contribution.model_sha256:
        graph["contribution_status"] = "model_mismatch"
    elif policy_fingerprint(policy) != contribution.baseline_policy_sha256:
        graph["contribution_status"] = "baseline_policy_mismatch"
    elif graph.get("status") != "scored" or graph.get("gnn_score") is None:
        graph["contribution_status"] = "score_unavailable"
    elif status != "approved":
        graph["contribution_status"] = "existing_restriction_preserved"
    elif graph["gnn_score"] / 100 < contribution.threshold:
        graph["contribution_status"] = "below_threshold"
    else:
        graph.update(contribution_status="two_factor_required", decision_override=True)
        metadata["decision_source"] = "gnn_v2"
        return "two_factor_required"
    return status
