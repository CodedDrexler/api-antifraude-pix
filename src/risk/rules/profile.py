from collections.abc import Iterator

from src.risk.types import RuleContext, RuleMatch


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    transaction = context.transaction
    history = context.history
    policy = context.policy
    # Integer comparison avoids floating point money and averaging errors.
    if (
        history.profile_count > 0
        and transaction.amount * history.profile_count >= history.profile_amount * policy.profile_multiplier
    ):
        yield RuleMatch(
            "amount_above_customer_profile",
            {
                "amount": transaction.amount,
                "history_amount": history.profile_amount,
                "history_count": history.profile_count,
            },
            {
                "multiplier": policy.profile_multiplier,
                "history_size": policy.profile_history_size,
            },
        )
