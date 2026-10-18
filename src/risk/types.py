from dataclasses import dataclass
from datetime import timedelta

from src.constants import Policy
from src.risk_context import is_night
from src.schemas.pix import PixTransactionCreate


@dataclass(frozen=True)
class History:
    recent_count: int
    recent_amount: int
    approved_count: int
    known_destination: bool
    known_device: bool
    profile_count: int = 0
    profile_amount: int = 0
    registered_count: int | None = None
    profile_basis: str = "provided_history"
    device_other_owners: int = 0
    payer_other_devices: int = 0
    approved_night_count: int = 0
    duplicate_transaction_id: str | None = None
    duplicate_elapsed_seconds: float | None = None
    payer_reference_values: tuple[int, ...] = ()
    relationship_reference_values: tuple[int, ...] = ()
    relationship_received_days: int = 0


@dataclass(frozen=True)
class RuleMatch:
    code: str
    observed: object
    threshold: object
    hard_limit: bool = False


@dataclass(frozen=True)
class RuleContext:
    transaction: PixTransactionCreate
    history: History
    policy: Policy

    @property
    def age(self) -> timedelta:
        return self.transaction.transaction_date - self.transaction.source_account.opening_date

    @property
    def destination_age(self) -> timedelta:
        return self.transaction.transaction_date - self.transaction.destination_account.opening_date

    @property
    def registered_count(self) -> int:
        value = self.history.registered_count
        return value if value is not None else self.history.profile_count

    @property
    def needs_history_confirmation(self) -> bool:
        return (
            self.history.profile_count == 0 and self.transaction.amount >= self.policy.no_history_min_amount
        )

    @property
    def night(self) -> bool:
        return is_night(self.transaction.transaction_date, self.policy)
