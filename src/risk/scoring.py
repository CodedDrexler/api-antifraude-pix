"""Shared score calculation for rule evidence and the optional GNN factor."""

from src.risk.attribution import RULE_SUBJECTS
from src.risk.types import RuleMatch
from src.risk_context import FACTOR_LABELS


def rule_evidence(match: RuleMatch, factor: str, weight: int, factor_weight: int) -> dict:
    return {
        "code": match.code,
        "subject": RULE_SUBJECTS.get(match.code, "transaction"),
        "source": (
            "operator_registry"
            if match.code == "verified_entity_relationship_exposure"
            else "local_model"
            if match.code == "gnn_relational_pattern"
            else "request_and_local_history"
        ),
        "group": factor,
        "risk_factor": factor,
        "weight": weight,
        "weighted_points": weight * factor_weight // 100,
        "contribution": 0,
        "observed": match.observed,
        "threshold": match.threshold,
        "hard_limit": match.hard_limit,
    }


def summarize_factor(name: str, rules: list[dict], cap: int, weight: int) -> dict:
    remaining = cap
    # Largest signals consume the cap first; code breaks ties deterministically.
    for rule in sorted(rules, key=lambda rule: (-rule["weighted_points"], rule["code"])):
        rule["contribution"] = min(rule["weighted_points"], remaining)
        remaining -= rule["contribution"]
    return {
        "name": name,
        "label": FACTOR_LABELS[name],
        "raw_score": sum(rule["weight"] for rule in rules),
        "weighted_score": sum(rule["weighted_points"] for rule in rules),
        "score": cap - remaining,
        "cap": cap,
        "weight": weight,
        "rules": [rule["code"] for rule in rules],
        "hard_limits": [rule["code"] for rule in rules if rule["hard_limit"]],
    }


def summarize_score(groups: dict, scoring: dict) -> dict:
    total = sum(group["score"] for group in groups.values())
    score = min(100, total)
    if score >= scoring["rejection_threshold"]:
        level = "high"
    elif score >= scoring["two_factor_threshold"]:
        level = "elevated"
    else:
        level = "low"
    return {
        "risk_score": score,
        "risk_level": level,
        "risk_factors_sum": total,
        "score_cap_reduction": max(0, total - 100),
        "risk_group_count": sum(group["score"] > 0 for group in groups.values()),
    }


def score_decision(metadata: dict, scoring: dict) -> tuple[str, str]:
    if metadata["hard_limits"]:
        return "rejected", "hard_limit"
    if (
        metadata["risk_score"] >= scoring["rejection_threshold"]
        and metadata["risk_group_count"] >= scoring["minimum_rejection_groups"]
    ):
        return "rejected", "risk_score"
    if metadata["risk_score"] >= scoring["two_factor_threshold"]:
        return "two_factor_required", "risk_score"
    return "approved", "risk_score"
