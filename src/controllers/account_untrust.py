"""Bounded, expiring account restrictions based on prior independent rule evidence.

This indicator is deliberately separate from transaction risk_score: it is neither
a probability nor a fraud label, and cannot feed its own restrictions back into evidence.
"""

from dataclasses import asdict, dataclass

from src.constants import UntrustPolicy

ELIGIBLE_FACTORS = {"activity", "profile", "device", "counterparty"}


@dataclass(frozen=True)
class UntrustHistory:
    points: int = 0
    events: int = 0


def assess_untrust(status, baseline, history, policy: UntrustPolicy, minimum_transaction_score=30):
    rules = [r for r in baseline["triggered_rules"] if r["risk_factor"] in ELIGIBLE_FACTORS]
    eligible = sum(rule["contribution"] for rule in rules)
    increment = 0
    active_block = (
        history.points >= policy.rejection_threshold and history.events >= policy.minimum_rejection_events
    )
    if policy.enabled and not active_block:
        if baseline["hard_limits"]:
            increment = policy.maximum_increment
        elif baseline["risk_score"] >= minimum_transaction_score:
            increment = min(
                policy.maximum_increment, (eligible + policy.score_divisor - 1) // policy.score_divisor
            )
    before = min(100, history.points) if policy.enabled else 0
    # Cap only the displayed account score; persist the independent increment.
    # This preserves outstanding evidence when earlier events leave the window.
    after = min(100, history.points + increment) if policy.enabled else 0
    events = history.events + int(increment > 0) if policy.enabled else 0
    action = "none"
    if (
        policy.enabled
        and policy.rejection_enabled
        and after >= policy.rejection_threshold
        and events >= policy.minimum_rejection_events
    ):
        action = "rejected"
    elif policy.enabled and after >= policy.two_factor_threshold:
        action = "two_factor_required"
    result = {
        "label": "Desconfiança acumulada da conta",
        "enabled": policy.enabled,
        "score_before": before,
        "score": after,
        "increment": increment,
        "increment_suppressed_by_active_restriction": policy.enabled and active_block,
        "risk_events": events,
        "action": action,
        "window_hours": policy.window_hours,
        "time_basis": "server_received_time",
        "eligible_rules": [rule["code"] for rule in rules if rule["contribution"] > 0],
        "score_semantics": "heuristic_not_probability_or_confirmed_fraud",
        "policy": asdict(policy),
    }
    # Only escalate, never relax a rejection or a requirement imposed by another control.
    if action == "rejected" and status != "rejected":
        status, result["decision_override"] = "rejected", True
    elif action == "two_factor_required" and status == "approved":
        status, result["decision_override"] = "two_factor_required", True
    else:
        result["decision_override"] = False
    notify = policy.enabled and after >= policy.notification_threshold
    notification = {
        "required": notify,
        "status": "indicated_only" if notify else "not_required",
        "reason": "account_untrust_threshold" if notify else None,
        "threshold": policy.notification_threshold,
        "threshold_crossed": notify and before < policy.notification_threshold,
    }
    return status, result, notification
