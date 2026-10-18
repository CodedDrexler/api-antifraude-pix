"""A familiar amount for this payer/recipient can attenuate only the value-profile signal."""

from src.risk.types import RuleContext
from src.risk_context import BRASILIA


def reference_fields(payer_samples, relationship_samples):
    """Samples are (integer cents, trusted received_at), ordered newest first."""
    return {
        "payer_reference_values": tuple(row[0] for row in payer_samples),
        "relationship_reference_values": tuple(row[0] for row in relationship_samples),
        "relationship_received_days": len(
            {row[1].astimezone(BRASILIA).date() for row in relationship_samples}
        ),
    }


def median_twice(values):
    """Twice the median in cents; retains half-cent medians without floating point."""
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] * 2 if len(ordered) % 2 else ordered[middle - 1] + ordered[middle]


def assess(context: RuleContext):
    policy = context.policy.contextual_trust
    history = context.history
    payer = history.payer_reference_values
    relationship = history.relationship_reference_values
    result = {
        "enabled": policy.enabled,
        "eligible": False,
        "applied": False,
        "reason": "disabled" if not policy.enabled else "insufficient_payer_history",
        "payer_samples": len(payer),
        "relationship_samples": len(relationship),
        "relationship_received_days": history.relationship_received_days,
        "payer_median_twice_cents": None,
        "relationship_median_twice_cents": None,
        "reference_semantics": "local_approvals_not_confirmed_payments",
        "policy_version": context.policy.version,
    }
    # Missing or malformed optional context must not grant an attenuation.
    if any(type(value) is not int or value <= 0 for value in (*payer, *relationship)):
        return {**result, "reason": "invalid_reference"}
    if payer:
        result["payer_median_twice_cents"] = median_twice(payer)
    if relationship:
        result["relationship_median_twice_cents"] = median_twice(relationship)
    if not policy.enabled or len(payer) < policy.minimum_payer_samples:
        return result
    if len(relationship) < policy.minimum_relationship_samples:
        return {**result, "reason": "insufficient_relationship_history"}
    if history.relationship_received_days < policy.minimum_received_days:
        return {**result, "reason": "insufficient_received_days"}
    median = result["relationship_median_twice_cents"]
    amount = context.transaction.amount * 200
    compatible = median * policy.minimum_ratio_percent <= amount <= median * policy.maximum_ratio_percent
    return {
        **result,
        "eligible": compatible,
        "reason": "compatible_relationship" if compatible else "incompatible_amount",
    }
