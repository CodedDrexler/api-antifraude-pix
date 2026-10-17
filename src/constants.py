import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RuleWeights:
    velocity_above_limit: int = 80
    accumulated_amount_above_limit: int = 80
    first_transaction: int = 30
    new_source_account: int = 15
    new_destination_account: int = 15
    unfamiliar_destination: int = 15
    amount_above_customer_profile: int = 80
    unfamiliar_device: int = 20
    shared_device: int = 30
    multiple_devices: int = 20
    unusual_night_app: int = 15
    insufficient_amount_history: int = 30


@dataclass(frozen=True)
class GroupCaps:
    exposure: int = 80
    activity: int = 80
    account: int = 15
    counterparty: int = 25
    profile: int = 80
    device: int = 40
    access_context: int = 15


@dataclass(frozen=True)
class FactorWeights:
    """Percentage applied to rule points before the factor cap (100 = unchanged)."""

    exposure: int = 100
    activity: int = 100
    account: int = 100
    counterparty: int = 100
    profile: int = 100
    device: int = 100
    graph: int = 100
    access_context: int = 100


@dataclass(frozen=True)
class RuleFactors:
    velocity_above_limit: str = "activity"
    accumulated_amount_above_limit: str = "activity"
    first_transaction: str = "exposure"
    new_source_account: str = "account"
    new_destination_account: str = "counterparty"
    unfamiliar_destination: str = "counterparty"
    amount_above_customer_profile: str = "profile"
    unfamiliar_device: str = "device"
    shared_device: str = "device"
    multiple_devices: str = "device"
    unusual_night_app: str = "access_context"
    insufficient_amount_history: str = "exposure"


@dataclass(frozen=True)
class ScoringPolicy:
    two_factor_threshold: int = 30
    rejection_threshold: int = 80
    minimum_rejection_groups: int = 2
    weights: RuleWeights = field(default_factory=RuleWeights)
    group_caps: GroupCaps = field(default_factory=GroupCaps)
    factor_weights: FactorWeights = field(default_factory=FactorWeights)
    rule_factors: RuleFactors = field(default_factory=RuleFactors)

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
        for value in asdict(self.factor_weights).values():
            if type(value) is not int or not 0 <= value <= 200:
                raise ValueError("Factor weights must be integer percentages from 0 to 200")
        for value in asdict(self.rule_factors).values():
            if not isinstance(value, str) or value not in asdict(self.group_caps):
                raise ValueError("Every rule must reference an existing risk factor")


@dataclass(frozen=True)
class UntrustPolicy:
    enabled: bool = True
    rejection_enabled: bool = False
    window_hours: int = 24
    two_factor_threshold: int = 40
    notification_threshold: int = 60
    rejection_threshold: int = 80
    maximum_increment: int = 25
    score_divisor: int = 4
    minimum_rejection_events: int = 4

    def __post_init__(self):
        if type(self.enabled) is not bool or type(self.rejection_enabled) is not bool:
            raise ValueError("untrust enabled flags must be booleans")
        for name, value in asdict(self).items():
            if name not in {"enabled", "rejection_enabled"} and (type(value) is not int or value <= 0):
                raise ValueError(f"untrust.{name} must be a positive integer")
        if not 0 < self.two_factor_threshold <= self.notification_threshold < self.rejection_threshold <= 100:
            raise ValueError(
                "Untrust thresholds must satisfy 0 < two_factor <= notification < rejection <= 100"
            )
        if self.maximum_increment > 25 or self.minimum_rejection_events < 2:
            raise ValueError("Untrust requires bounded increments (<=25) and repeated evidence (>=2 events)")


@dataclass(frozen=True)
class Policy:
    version: str = "pix-score-v5"
    velocity_minutes: int = 10
    velocity_limit: int = 5
    accumulated_amount: int = 3_000_000
    new_account_days: int = 7
    profile_days: int = 30
    profile_history_size: int = 10
    profile_multiplier: int = 5
    profile_min_amount: int = 50_000
    device_min_history: int = 3
    device_min_amount: int = 50_000
    destination_min_history: int = 3
    device_window_hours: int = 24
    device_owner_limit: int = 3
    payer_device_limit: int = 3
    night_start_hour: int = 20
    night_end_hour: int = 6
    night_min_amount: int = 50_000
    night_min_history: int = 3
    untrust: UntrustPolicy = field(default_factory=UntrustPolicy)
    scoring: ScoringPolicy = field(default_factory=ScoringPolicy)

    @classmethod
    def from_file(cls, path: str):
        """Load a trusted operator configuration; unknown fields fail at startup."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Policy configuration must be a JSON object")
        scoring = data.pop("scoring", {})
        if not isinstance(scoring, dict):
            raise ValueError("scoring must be a JSON object")
        untrust = data.pop("untrust", {})
        if not isinstance(untrust, dict):
            raise ValueError("untrust must be a JSON object")
        for name, model in (
            ("weights", RuleWeights),
            ("group_caps", GroupCaps),
            ("factor_weights", FactorWeights),
            ("rule_factors", RuleFactors),
        ):
            if name in scoring:
                values = scoring[name]
                if not isinstance(values, dict):
                    raise ValueError(f"{name} must be a JSON object")
                scoring[name] = model(**values)
        return cls(**data, scoring=ScoringPolicy(**scoring), untrust=UntrustPolicy(**untrust))

    def __post_init__(self):
        for name, value in asdict(self).items():
            if name not in {"version", "scoring", "untrust", "night_start_hour", "night_end_hour"} and (
                type(value) is not int or value <= 0
            ):
                raise ValueError(f"Policy {name} must be a positive integer")
        if (
            type(self.night_start_hour) is not int
            or type(self.night_end_hour) is not int
            or not 0 <= self.night_end_hour < self.night_start_hour <= 23
        ):
            raise ValueError("Night hours must satisfy 0 <= end < start <= 23")
        if self.device_owner_limit < 2 or self.payer_device_limit < 2:
            raise ValueError("Device diversity thresholds must be at least 2")


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
