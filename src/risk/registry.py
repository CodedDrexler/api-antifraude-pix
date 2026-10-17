"""Explicit factor order preserves the audit order of triggered rules."""

from src.risk.rules import (
    access_context,
    account,
    activity,
    counterparty,
    device,
    duplication,
    exposure,
    profile,
)
from src.risk.types import RuleContext, RuleMatch

EVALUATORS = (
    activity.evaluate,
    duplication.evaluate,
    exposure.evaluate,
    account.evaluate,
    counterparty.evaluate,
    profile.evaluate,
    device.evaluate,
    access_context.evaluate,
)


def evaluate_rules(context: RuleContext) -> list[RuleMatch]:
    return [match for evaluate in EVALUATORS for match in evaluate(context)]
