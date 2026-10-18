from dataclasses import asdict

from src.constants import Policy
from src.risk.attribution import decision_causes
from src.risk.contextual_trust import assess as assess_contextual_trust
from src.risk.registry import evaluate_rules
from src.risk.scoring import rule_evidence, score_decision, summarize_factor, summarize_score
from src.risk.types import History, RuleContext
from src.schemas.pix import PixTransactionCreate


class DecisionEngine:
    """Evaluate pure rules, apply factor caps and preserve the decision evidence."""

    def __init__(self, policy: Policy):
        self.policy = policy

    def evaluate(self, transaction: PixTransactionCreate, history: History):
        context = RuleContext(transaction, history, self.policy)
        scoring = self.policy.scoring
        contextual_trust = assess_contextual_trust(context)
        contextual_trust.update(profile_points_before=0, profile_points_after=0)
        rules = []
        for match in evaluate_rules(context):
            factor = getattr(scoring.rule_factors, match.code)
            evidence = rule_evidence(
                match,
                factor,
                getattr(scoring.weights, match.code),
                getattr(scoring.factor_weights, factor),
            )
            if match.code == "amount_above_customer_profile":
                before = evidence["weighted_points"]
                if contextual_trust["eligible"]:
                    evidence["points_before_context"] = before
                    evidence["weighted_points"] = 0
                    evidence["context_adjustment"] = "familiar_relationship_amount"
                    contextual_trust["applied"] = True
                contextual_trust.update(
                    profile_points_before=before, profile_points_after=evidence["weighted_points"]
                )
            rules.append(evidence)

        factors = []
        for name, cap in asdict(scoring.group_caps).items():
            matches = [rule for rule in rules if rule["risk_factor"] == name]
            if matches:
                factors.append(summarize_factor(name, matches, cap, getattr(scoring.factor_weights, name)))
        groups = {
            factor["name"]: {key: factor[key] for key in ("raw_score", "score", "cap")} for factor in factors
        }
        policy_snapshot = asdict(self.policy)
        metadata = {
            **summarize_score(groups, policy_snapshot["scoring"]),
            "score_semantics": "heuristic_not_probability",
            "raw_score": sum(rule["weight"] for rule in rules),
            "group_scores": groups,
            "risk_factors": factors,
            "triggered_rules": rules,
            "hard_limits": [rule["code"] for rule in rules if rule["hard_limit"]],
            "reasons": [rule["code"] for rule in rules] or ["no_rule_triggered"],
            "policy": policy_snapshot,
            "recent_transactions": history.recent_count,
            "recent_amount": history.recent_amount,
            "source_account_age_days": context.age.days,
            "destination_account_age_days": context.destination_age.days,
            "profile_transactions": history.profile_count,
            "registered_transactions": context.registered_count,
            "profile_basis": history.profile_basis,
            "contextual_trust": contextual_trust,
            "profile_amount": history.profile_amount,
            "profile_average": history.profile_amount / history.profile_count
            if history.profile_count
            else None,
            "profile_limit": (
                history.profile_amount * self.policy.profile_multiplier / history.profile_count
                if history.profile_count
                else None
            ),
            "approved_transactions": history.approved_count,
            "known_destination": history.known_destination,
            "known_device": history.known_device,
            "device_owner_count": history.device_other_owners + 1,
            "payer_device_count": history.payer_other_devices + 1,
            "device_window_hours": self.policy.device_window_hours,
            "access_context": {
                "channel": transaction.source.channel,
                "is_night": context.night,
                "timezone": "UTC-03:00",
                "approved_night_transactions": history.approved_night_count,
                "regulatory_limits_checked": False,
            },
        }
        status, source = score_decision(metadata, policy_snapshot["scoring"])
        if status != "rejected" and history.profile_count == 0:
            status = "two_factor_required"
            source = "first_transaction" if context.registered_count == 0 else "insufficient_history"
        metadata["decision_source"] = source
        metadata["decision_causes"] = decision_causes(metadata, status)
        if history.duplicate_transaction_id:
            metadata["duplicate_payment"] = {
                "message": "Possível pagamento duplicado: existe uma tentativa recente com o mesmo valor para este destinatário.",
                "previous_transaction_id": history.duplicate_transaction_id,
                "elapsed_seconds": history.duplicate_elapsed_seconds,
                "window_seconds": self.policy.duplicate_window_seconds,
                "previous_payment_confirmed": False,
            }
        return status, metadata
