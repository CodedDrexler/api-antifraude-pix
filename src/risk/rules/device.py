from collections.abc import Iterator

from src.risk.types import RuleContext, RuleMatch


def evaluate(context: RuleContext) -> Iterator[RuleMatch]:
    transaction = context.transaction
    history = context.history
    policy = context.policy
    if (
        history.approved_count >= policy.device_min_history
        and not history.known_device
        and transaction.amount >= policy.device_min_amount
    ):
        yield RuleMatch("unfamiliar_device", False, True)
    # Count distinct owners, not accounts: one owner may legitimately have many accounts.
    if history.device_other_owners + 1 >= policy.device_owner_limit:
        yield RuleMatch("shared_device", history.device_other_owners + 1, policy.device_owner_limit)
    # Only a new device within this short window adds a device-churn signal.
    if history.payer_other_devices + 1 >= policy.payer_device_limit and not history.known_device:
        yield RuleMatch("multiple_devices", history.payer_other_devices + 1, policy.payer_device_limit)
