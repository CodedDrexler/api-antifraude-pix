import os
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class RuleWeights:
    amount_above_rejection_limit: int = 80
    velocity_above_limit: int = 80
    accumulated_amount_above_limit: int = 80
    amount_requires_two_factor: int = 30
    new_source_account: int = 15
    new_destination_account: int = 15
    unfamiliar_destination: int = 15
    amount_above_customer_profile: int = 25
    unfamiliar_device: int = 20


@dataclass(frozen=True)
class GroupCaps:
    exposure: int = 80
    activity: int = 80
    account: int = 15
    counterparty: int = 25
    profile: int = 25
    device: int = 20


@dataclass(frozen=True)
class ScoringPolicy:
    two_factor_threshold: int = 30
    rejection_threshold: int = 80
    minimum_rejection_groups: int = 2
    weights: RuleWeights = field(default_factory=RuleWeights)
    group_caps: GroupCaps = field(default_factory=GroupCaps)

    def __post_init__(self):
        for value in (self.two_factor_threshold, self.rejection_threshold, self.minimum_rejection_groups):
            if type(value) is not int:
                raise ValueError("Scoring thresholds must be integers")
        if not 0 < self.two_factor_threshold < self.rejection_threshold <= 100:
            raise ValueError("Score thresholds must satisfy 0 < two_factor < rejection <= 100")
        if not 1 <= self.minimum_rejection_groups <= len(asdict(self.group_caps)):
            raise ValueError("minimum_rejection_groups must fit the available groups")
        for value in asdict(self.weights).values():
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError("Rule weights must be integers from 0 to 100")
        for value in asdict(self.group_caps).values():
            if type(value) is not int or not 0 < value <= 100:
                raise ValueError("Group caps must be integers from 1 to 100")


@dataclass(frozen=True)
class Policy:
    version: str = "pix-score-v2"
    rejection_amount: int = 2_000_000
    two_factor_amount: int = 100_000
    velocity_minutes: int = 10
    velocity_limit: int = 5
    accumulated_amount: int = 3_000_000
    new_account_days: int = 7
    profile_days: int = 30
    profile_min_history: int = 5
    profile_multiplier: int = 5
    profile_min_amount: int = 50_000
    device_min_history: int = 3
    device_min_amount: int = 50_000
    destination_min_history: int = 3
    scoring: ScoringPolicy = field(default_factory=ScoringPolicy)

    def __post_init__(self):
        for name, value in asdict(self).items():
            if name not in {"version", "scoring"} and (type(value) is not int or value <= 0):
                raise ValueError(f"Policy {name} must be a positive integer")
        if self.two_factor_amount >= self.rejection_amount:
            raise ValueError("two_factor_amount must be below rejection_amount")


@dataclass(frozen=True)
class Settings:
    database_url: str
    internal_token: str
    service_name: str = "pix-antifraud"

    @classmethod
    def from_env(cls):
        database_url = os.environ.get("DATABASE_URL", "")
        internal_token = os.environ.get("INTERNAL_TOKEN", "")
        if not database_url.startswith("postgresql+psycopg2://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg2://")
        if not internal_token.strip() or not internal_token.isascii():
            raise ValueError("INTERNAL_TOKEN must be nonempty ASCII text")
        return cls(database_url, internal_token)
