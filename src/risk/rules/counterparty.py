from collections.abc import Iterator
from datetime import timedelta

from src.risk.types import RuleContext, RuleMatch


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    transaction = context.transaction
    history = context.history
    policy = context.policy
    if (
        not history.known_destination
        and context.destination_age < timedelta(days=policy.new_account_days)
        and transaction.amount >= policy.profile_min_amount
    ):
        yield RuleMatch(
            "new_destination_account",
            context.destination_age.total_seconds(),
            policy.new_account_days * 86400,
        )
    if (
        history.approved_count >= policy.destination_min_history
        and not history.known_destination
        and transaction.amount >= policy.profile_min_amount
    ):
        yield RuleMatch("unfamiliar_destination", False, True)
