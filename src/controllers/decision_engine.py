from dataclasses import asdict
from datetime import timedelta

from src.constants import Policy
from src.repositories.pix_repository import History
from src.schemas.pix import PixTransactionCreate


class DecisionEngine:
    """Deterministic heuristic score with capped evidence groups and explicit hard limits."""

    def __init__(self, policy: Policy):
        self.policy = policy

    def evaluate(self, transaction: PixTransactionCreate, history: History):
        p = self.policy
        scoring = p.scoring
        age = transaction.transaction_date - transaction.source_account.opening_date
        destination_age = transaction.transaction_date - transaction.destination_account.opening_date
        rules = []

        def add(code, group, observed, threshold, hard_limit=False):
            rules.append(
                {
                    "code": code,
                    "group": group,
                    "weight": getattr(scoring.weights, code),
                    "contribution": 0,
                    "observed": observed,
                    "threshold": threshold,
                    "hard_limit": hard_limit,
                }
            )

        if transaction.amount >= p.rejection_amount:
            add("amount_above_rejection_limit", "exposure", transaction.amount, p.rejection_amount, True)
        if history.recent_count >= p.velocity_limit:
            add("velocity_above_limit", "activity", history.recent_count, p.velocity_limit, True)
        if history.recent_amount + transaction.amount >= p.accumulated_amount:
            add(
                "accumulated_amount_above_limit",
                "activity",
                history.recent_amount + transaction.amount,
                p.accumulated_amount,
                True,
            )
        if transaction.amount >= p.two_factor_amount:
            add("amount_requires_two_factor", "exposure", transaction.amount, p.two_factor_amount)
        if age < timedelta(days=p.new_account_days):
            add("new_source_account", "account", age.total_seconds(), p.new_account_days * 86400)
        if (
            not history.known_destination
            and destination_age < timedelta(days=p.new_account_days)
            and transaction.amount >= p.profile_min_amount
        ):
            add(
                "new_destination_account",
                "counterparty",
                destination_age.total_seconds(),
                p.new_account_days * 86400,
            )
        if (
            history.approved_count >= p.destination_min_history
            and not history.known_destination
            and transaction.amount >= p.profile_min_amount
        ):
            add("unfamiliar_destination", "counterparty", False, True)
        # Integer comparison avoids floating point money and averaging errors.
        if (
            history.approved_count >= p.profile_min_history
            and transaction.amount >= p.profile_min_amount
            and transaction.amount * history.approved_count >= history.approved_amount * p.profile_multiplier
        ):
            add(
                "amount_above_customer_profile",
                "profile",
                {
                    "amount": transaction.amount,
                    "history_amount": history.approved_amount,
                    "history_count": history.approved_count,
                },
                {
                    "multiplier": p.profile_multiplier,
                    "minimum_amount": p.profile_min_amount,
                    "minimum_history": p.profile_min_history,
                },
            )
        if (
            history.approved_count >= p.device_min_history
            and not history.known_device
            and transaction.amount >= p.device_min_amount
        ):
            add("unfamiliar_device", "device", False, True)

        groups = {}
        for group, cap in asdict(scoring.group_caps).items():
            matches = [rule for rule in rules if rule["group"] == group]
            if not matches:
                continue
            remaining = cap
            # Largest signals consume the cap first; code breaks ties deterministically.
            for rule in sorted(matches, key=lambda rule: (-rule["weight"], rule["code"])):
                rule["contribution"] = min(rule["weight"], remaining)
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
            "risk_score": risk_score,
            "risk_level": risk_level,
            "score_semantics": "heuristic_not_probability",
            "raw_score": sum(rule["weight"] for rule in rules),
            "group_scores": groups,
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
            "profile_transactions": history.approved_count,
            "profile_amount": history.approved_amount,
            "known_destination": history.known_destination,
            "known_device": history.known_device,
        }
