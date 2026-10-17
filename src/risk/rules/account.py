from collections.abc import Iterator
from datetime import timedelta

from src.risk.types import RuleContext, RuleMatch


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    p = context.policy
    if context.age < timedelta(days=p.new_account_days):
        yield RuleMatch("new_source_account", context.age.total_seconds(), p.new_account_days * 86400)
