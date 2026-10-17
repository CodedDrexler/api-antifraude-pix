from dataclasses import asdict

from src.constants import Policy
from src.repositories.pix_repository import History
from src.risk.registry import evaluate_rules
from src.risk.types import RuleContext
from src.risk_context import FACTOR_LABELS
from src.schemas.pix import PixTransactionCreate


class DecisionEngine:
    """Deterministic heuristic score with capped evidence groups and explicit hard limits."""

    def __init__(self, policy: Policy):
        self.policy = policy

    def evaluate(self, transaction: PixTransactionCreate, history: History):
        p = self.policy
        scoring = p.scoring
        context = RuleContext(transaction, history, p)
        age = context.age
        destination_age = context.destination_age
        registered_count = context.registered_count
        night = context.night
        rules = []
        for match in evaluate_rules(context):
            factor = getattr(scoring.rule_factors, match.code)
            weight = getattr(scoring.weights, match.code)
            rules.append(
                {
                    "code": match.code,
                    "group": factor,
                    "risk_factor": factor,
                    "weight": weight,
                    "weighted_points": weight * getattr(scoring.factor_weights, factor) // 100,
                    "contribution": 0,
                    "observed": match.observed,
                    "threshold": match.threshold,
                    "hard_limit": match.hard_limit,
                }
            )

        groups = {}
        for group, cap in asdict(scoring.group_caps).items():
            matches = [rule for rule in rules if rule["group"] == group]
            if not matches:
                continue
            remaining = cap
            # Largest signals consume the cap first; code breaks ties deterministically.
            for rule in sorted(matches, key=lambda rule: (-rule["weighted_points"], rule["code"])):
                rule["contribution"] = min(rule["weighted_points"], remaining)
                remaining -= rule["contribution"]
            groups[group] = {
                "raw_score": sum(rule["weight"] for rule in matches),
                "score": cap - remaining,
                "cap": cap,
            }

        grouped_score = sum(group["score"] for group in groups.values())
        risk_score = min(100, grouped_score)
        group_count = sum(group["score"] > 0 for group in groups.values())
        hard_limits = [rule["code"] for rule in rules if rule["hard_limit"]]
        if hard_limits:
            status, decision_source = "rejected", "hard_limit"
        elif risk_score >= scoring.rejection_threshold and group_count >= scoring.minimum_rejection_groups:
            status, decision_source = "rejected", "risk_score"
        elif history.profile_count == 0:
            status = "two_factor_required"
            decision_source = "first_transaction" if registered_count == 0 else "insufficient_history"
        elif risk_score >= scoring.two_factor_threshold:
            status, decision_source = "two_factor_required", "risk_score"
        else:
            status, decision_source = "approved", "risk_score"
        risk_level = (
            "high"
            if risk_score >= scoring.rejection_threshold
            else "elevated"
            if risk_score >= scoring.two_factor_threshold
            else "low"
        )
        return status, {
            **(
                {
                    "duplicate_payment": {
                        "message": "Possível pagamento duplicado: existe uma tentativa recente com o mesmo valor para este destinatário.",
                        "previous_transaction_id": history.duplicate_transaction_id,
                        "elapsed_seconds": history.duplicate_elapsed_seconds,
                        "window_seconds": p.duplicate_window_seconds,
                        "previous_payment_confirmed": False,
                    }
                }
                if history.duplicate_transaction_id
                else {}
            ),
            "risk_score": risk_score,
            "risk_factors_sum": grouped_score,
            "risk_level": risk_level,
            "score_semantics": "heuristic_not_probability",
            "raw_score": sum(rule["weight"] for rule in rules),
            "group_scores": groups,
            "risk_factors": [
                {
                    "name": factor,
                    "label": FACTOR_LABELS[factor],
                    **values,
                    "weight": getattr(scoring.factor_weights, factor),
                    "weighted_score": sum(r["weighted_points"] for r in rules if r["risk_factor"] == factor),
                    "rules": [r["code"] for r in rules if r["risk_factor"] == factor],
                    "hard_limits": [
                        r["code"] for r in rules if r["risk_factor"] == factor and r["hard_limit"]
                    ],
                }
                for factor, values in groups.items()
            ],
            "score_cap_reduction": grouped_score - risk_score,
            "risk_group_count": group_count,
            "triggered_rules": rules,
            "decision_source": decision_source,
            "hard_limits": hard_limits,
            "reasons": [rule["code"] for rule in rules] or ["no_rule_triggered"],
            "policy": asdict(p),
            "recent_transactions": history.recent_count,
            "recent_amount": history.recent_amount,
            "source_account_age_days": age.days,
            "destination_account_age_days": destination_age.days,
            "profile_transactions": history.profile_count,
            "registered_transactions": registered_count,
            "profile_basis": history.profile_basis,
            "profile_amount": history.profile_amount,
            "profile_average": history.profile_amount / history.profile_count
            if history.profile_count
            else None,
            "profile_limit": (
                history.profile_amount * p.profile_multiplier / history.profile_count
                if history.profile_count
                else None
            ),
            "approved_transactions": history.approved_count,
            "known_destination": history.known_destination,
            "known_device": history.known_device,
            "device_owner_count": history.device_other_owners + 1,
            "payer_device_count": history.payer_other_devices + 1,
            "device_window_hours": p.device_window_hours,
            "access_context": {
                "channel": transaction.source.channel,
                "is_night": night,
                "timezone": "UTC-03:00",
                "approved_night_transactions": history.approved_night_count,
                "regulatory_limits_checked": False,
            },
        }
