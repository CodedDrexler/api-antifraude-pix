from collections.abc import Iterator
from datetime import timedelta

from src.risk.types import RuleContext, RuleMatch


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    policy = context.policy
    if context.age < timedelta(days=policy.new_account_days):
        yield RuleMatch("new_source_account", context.age.total_seconds(), policy.new_account_days * 86400)
