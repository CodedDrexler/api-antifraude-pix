"""Disjoint, labeled synthetic scenarios; labels represent generator intent, never API decisions."""

import random
from datetime import datetime, timedelta, timezone


def scenario(seed: int, split="train", kind: str | None = None):
    rng = random.Random(f"{split}:{seed}")
    kinds = ["normal", "merchant", "family", "ring", "fan_in", "new_merchant"]
    kind = kind or rng.choice(kinds)
    fraud = kind in {"ring", "fan_in"}
    month = {"train": 1, "validation": 5, "test": 9, "demo": 10}[split]
    at = datetime(2026, month, 15, 15, tzinfo=timezone.utc)
    prefix = f"synthetic-{split}-{seed}"

    def account(index, days):
        # Distinct accounts across splits and scenarios. No identifier is a numeric model feature.
        split_number = {"train": 1, "validation": 2, "test": 3, "demo": 4}[split]
        doc = f"{split_number * 10**10 + seed * 100 + index:011d}"
        return {
            "participant": "12345678",
            "branch": "0001",
            "account_number": f"{prefix}-{index}",
            "opening_date": (at - timedelta(days=days)).isoformat(),
            "owner": {"document_number": doc},
        }

    source = account(1, rng.randint(30, 500))
    # Hard negative: a legitimate new merchant can resemble a fraudulent concentrator.
    recipient_days = rng.randint(1, 20) if fraud or kind == "new_merchant" else rng.randint(1, 500)
    recipient = account(2, recipient_days)
    records = []
    count = rng.randint(10, 24)
    for i in range(count):
        if kind == "normal":
            sender = source if i % 3 else account(10 + i, rng.randint(30, 500))
            receiver = recipient if i % 2 else account(50 + i, rng.randint(5, 500))
            device = f"{prefix}-personal-{sender['account_number']}"
        elif kind == "merchant":
            sender = source if i % 4 == 0 else account(10 + i, rng.randint(1, 500))
            receiver = recipient
            device = f"{prefix}-personal-{sender['account_number']}"
        elif kind == "family":
            sender = account(1 + i % 3, rng.randint(30, 500))
            receiver = recipient if i % 2 else account(50 + i, rng.randint(1, 500))
            device = f"{prefix}-shared-family"
        elif kind == "ring":
            sender = source if i % 6 == 0 else account(10 + i % 10, rng.randint(1, 60))
            receiver = recipient if i % 3 else account(50 + i % 4, rng.randint(1, 20))
            device = f"{prefix}-shared-ring"
        else:
            sender = source if i % 6 == 0 else account(10 + i, rng.randint(1, 90))
            receiver = recipient
            device = f"{prefix}-device-{i % 3}"
        records.append(
            {
                "id": f"{prefix}-history-{i}",
                "amount": rng.randint(1000, 90_000),
                "transaction_date": (at - timedelta(minutes=(i + 1) * rng.randint(2, 20))).isoformat(),
                "source_account": sender,
                "destination_account": receiver,
                "source": {"device_id": device, "channel": "app", "ip": "198.51.100.23"},
            }
        )
    if kind == "family":
        current_device = f"{prefix}-shared-family"
    elif kind == "ring":
        current_device = f"{prefix}-shared-ring"
    elif kind in {"fan_in", "new_merchant"}:
        current_device = f"{prefix}-device-0"
    else:
        current_device = f"{prefix}-personal-{source['account_number']}"
    candidate = {
        "id": f"{prefix}-candidate",
        "amount": rng.randint(1000, 90_000),
        "transaction_date": at.isoformat(),
        "source_account": source,
        "destination_account": recipient,
        "source": {"device_id": current_device, "channel": "app", "ip": "198.51.100.23"},
    }
    return candidate, records, int(fraud), kind
