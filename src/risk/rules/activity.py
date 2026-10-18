from collections.abc import Iterator

from src.risk.types import RuleContext, RuleMatch


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    transaction = context.transaction
    history = context.history
    policy = context.policy
    if history.recent_count >= policy.velocity_limit:
        yield RuleMatch("velocity_above_limit", history.recent_count, policy.velocity_limit, True)
    if history.recent_amount + transaction.amount >= policy.accumulated_amount:
        yield RuleMatch(
            "accumulated_amount_above_limit",
            history.recent_amount + transaction.amount,
            policy.accumulated_amount,
            True,
        )
