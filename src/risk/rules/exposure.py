from collections.abc import Iterator

from src.risk.types import RuleContext, RuleMatch


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    if context.needs_history_confirmation:
        code = "first_transaction" if context.registered_count == 0 else "insufficient_amount_history"
        yield RuleMatch(
            code,
            {"amount": context.transaction.amount, "profile_transactions": context.history.profile_count},
            {"minimum_amount": context.policy.no_history_min_amount, "minimum_profile_transactions": 1},
        )
