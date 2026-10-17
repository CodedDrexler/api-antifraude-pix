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

from src.schemas.pix_examples import PIX_REQUEST_EXAMPLE

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
    document_number: str = Field(
        min_length=11,
        max_length=18,
        examples=["123.456.789-09", "12.345.678/0001-90"],
        description="CPF ou CNPJ; aceita pontuação e normaliza para dígitos.",
    )

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
    participant: str | None = Field(default=None, pattern=r"^[0-9]{8}$", examples=["60701190"])
    branch: Text = Field(examples=["0001"])
    account_number: Text = Field(examples=["88213"])
    opening_date: AwareDatetime = Field(examples=["2025-03-02T10:00:00-03:00"])
    owner: AccountOwner


class DestinationAccount(Account):
    participant: str = Field(pattern=r"^[0-9]{8}$", examples=["60701190"])


class Geolocation(InputModel):
    latitude: float = Field(strict=True, ge=-90, le=90, allow_inf_nan=False, examples=[-23.56])
    longitude: float = Field(strict=True, ge=-180, le=180, allow_inf_nan=False, examples=[-46.65])


class PixSource(InputModel):
    device_id: Text = Field(examples=["dvc-9f2c71a8"])
    channel: Text = Field(
        examples=["app", "internet_banking"],
        description=(
            "Canal informado pelo integrador: app para aplicativo móvel; internet_banking para navegador/PC. "
            "Outros canais são aceitos. O sinal contextual noturno avalia somente app (sem distinguir maiúsculas). "
            "Isso não dispensa os limites noturnos bancários nos demais canais."
        ),
    )
    ip: IPvAnyAddress = Field(examples=["198.51.100.23"])
    geolocation: Geolocation | None = None


class PixTransactionCreate(InputModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [PIX_REQUEST_EXAMPLE]},
    )

    id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
        examples=["pix-000123"],
        description="Identificador único. Use um novo ID ao alterar o conteúdo ou testar outra análise.",
    )
    amount: int = Field(
        strict=True,
        gt=0,
        le=9_223_372_036_854_775_807,
        examples=[150_000],
        description="Valor em centavos: 150000 corresponde a R$ 1.500,00.",
    )
    transaction_date: AwareDatetime = Field(examples=["2026-10-17T22:15:00-03:00"])
    source_account: Account
    destination_account: DestinationAccount
    source: PixSource

    @model_validator(mode="after")
    def validate_opening_dates(self):
        for account in (self.source_account, self.destination_account):
            if account.opening_date > self.transaction_date:
                raise ValueError("account opening_date cannot follow transaction_date")
        return self
