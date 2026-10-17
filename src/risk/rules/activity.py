from collections.abc import Iterator

from src.risk.types import RuleContext, RuleMatch


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    transaction = context.transaction
    history = context.history
    p = context.policy
    if history.recent_count >= p.velocity_limit:
        yield RuleMatch("velocity_above_limit", history.recent_count, p.velocity_limit, True)
    if history.recent_amount + transaction.amount >= p.accumulated_amount:
        yield RuleMatch(
            "accumulated_amount_above_limit",
            history.recent_amount + transaction.amount,
            p.accumulated_amount,
            True,
        )
