from collections.abc import Iterator

from src.risk.types import RuleContext, RuleMatch


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    history = context.history
    if context.registered_count == 0:
        yield RuleMatch("first_transaction", 0, 1)
    elif history.profile_count == 0:
        yield RuleMatch("insufficient_amount_history", 0, 1)
