from dataclasses import dataclass
from datetime import timedelta

from src.constants import Policy
from src.repositories.pix_repository import History
from src.risk_context import is_night
from src.schemas.pix import PixTransactionCreate


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
    def night(self) -> bool:
        return is_night(self.transaction.transaction_date, self.policy)
