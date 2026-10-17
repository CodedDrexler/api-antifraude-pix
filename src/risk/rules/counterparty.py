from collections.abc import Iterator
from datetime import timedelta

from src.risk.types import RuleContext, RuleMatch


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    transaction = context.transaction
    history = context.history
    p = context.policy
    if (
        not history.known_destination
        and context.destination_age < timedelta(days=p.new_account_days)
        and transaction.amount >= p.profile_min_amount
    ):
        yield RuleMatch(
            "new_destination_account",
            context.destination_age.total_seconds(),
            p.new_account_days * 86400,
        )
    if (
        history.approved_count >= p.destination_min_history
        and not history.known_destination
        and transaction.amount >= p.profile_min_amount
    ):
        yield RuleMatch("unfamiliar_destination", False, True)
