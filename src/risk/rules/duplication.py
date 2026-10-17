from collections.abc import Iterator

from src.risk.types import RuleContext, RuleMatch


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    if context.history.duplicate_transaction_id:
        yield RuleMatch(
            "possible_duplicate_payment",
            {
                "previous_transaction_id": context.history.duplicate_transaction_id,
                "elapsed_seconds": context.history.duplicate_elapsed_seconds,
            },
            {"window_seconds": context.policy.duplicate_window_seconds},
        )
