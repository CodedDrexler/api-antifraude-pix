from collections.abc import Iterator

from src.risk.types import RuleContext, RuleMatch
from src.risk_context import BRASILIA


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    transaction = context.transaction
    history = context.history
    policy = context.policy
    if (
        transaction.source.channel.casefold() == "app"
        and context.night
        and history.approved_count >= policy.night_min_history
        and history.approved_night_count == 0
        and transaction.amount >= policy.night_min_amount
        and (not history.known_device or not history.known_destination)
    ):
        yield RuleMatch(
            "unusual_night_app",
            {
                "channel": transaction.source.channel,
                "local_hour": transaction.transaction_date.astimezone(BRASILIA).hour,
                "approved_night_transactions": history.approved_night_count,
            },
            {
                "start_hour": policy.night_start_hour,
                "end_hour": policy.night_end_hour,
                "timezone": "UTC-03:00",
                "minimum_amount": policy.night_min_amount,
            },
        )
