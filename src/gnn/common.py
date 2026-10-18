"""Account identity, timestamps and monetary normalization for the directed graph."""

import math
from datetime import datetime


def account_identity(account):
    return (
        account.get("participant") or "",
        account["branch"],
        account["account_number"],
        account["owner"]["document_number"],
    )


def parse_date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def money_feature(value):
    return min(math.log1p(max(value, 0)) / 16, 1.5)
