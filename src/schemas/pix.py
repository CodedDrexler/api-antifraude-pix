from datetime import timezone
from typing import Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    IPvAnyAddress,
    StringConstraints,
    field_validator,
    model_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def require_date_strings(cls, value, info):
        if info.field_name in {"opening_date", "transaction_date"} and not isinstance(value, str):
            raise ValueError("dates must be ISO 8601 strings with a timezone")
        return value

    @field_validator("*", mode="after")
    @classmethod
    def normalize_dates(cls, value):
        if hasattr(value, "astimezone"):
            return value.astimezone(timezone.utc)
        return value


class AccountOwner(InputModel):
    document_number: str = Field(min_length=11, max_length=18)

    @field_validator("document_number")
    @classmethod
    def normalize_document(cls, value):
        if any(c not in "0123456789./-" for c in value):
            raise ValueError("document_number must contain CPF/CNPJ digits and punctuation")
        digits = "".join(c for c in value if c.isdigit())
        if len(digits) not in (11, 14):
            raise ValueError("document_number must have 11 or 14 digits")
        return digits


class Account(InputModel):
    participant: str | None = Field(default=None, pattern=r"^[0-9]{8}$")
    branch: Text
    account_number: Text
    opening_date: AwareDatetime
    owner: AccountOwner


class DestinationAccount(Account):
    participant: str = Field(pattern=r"^[0-9]{8}$")


class Geolocation(InputModel):
    latitude: float = Field(strict=True, ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(strict=True, ge=-180, le=180, allow_inf_nan=False)


class PixSource(InputModel):
    device_id: Text
    channel: Text
    ip: IPvAnyAddress
    geolocation: Geolocation | None = None


class PixTransactionCreate(InputModel):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    amount: int = Field(strict=True, gt=0, le=9_223_372_036_854_775_807)
    transaction_date: AwareDatetime
    source_account: Account
    destination_account: DestinationAccount
    source: PixSource

    @model_validator(mode="after")
    def validate_opening_dates(self):
        for account in (self.source_account, self.destination_account):
            if account.opening_date > self.transaction_date:
                raise ValueError("account opening_date cannot follow transaction_date")
        return self
