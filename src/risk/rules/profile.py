from collections.abc import Iterator

from src.risk.types import RuleContext, RuleMatch


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    transaction = context.transaction
    history = context.history
    p = context.policy
    # Integer comparison avoids floating point money and averaging errors.
    if (
        history.profile_count > 0
        and transaction.amount * history.profile_count >= history.profile_amount * p.profile_multiplier
    ):
        yield RuleMatch(
            "amount_above_customer_profile",
            {
                "amount": transaction.amount,
                "history_amount": history.profile_amount,
                "history_count": history.profile_count,
            },
            {
                "multiplier": p.profile_multiplier,
                "history_size": p.profile_history_size,
            },
        )
