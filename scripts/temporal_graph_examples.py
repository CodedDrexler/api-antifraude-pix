"""Source-intent labels only; hard temporal negatives share the same base graph."""

from datetime import datetime, timedelta

from scripts.evaluate_graph_untrust import STRESS_KINDS, stress_scenario
from src.gnn.graph import account_identity

KINDS = (*STRESS_KINDS, "temporal_fast", "temporal_slow")


def source_scenario(seed, split, kind):
    base_kind = "mule_direct" if kind.startswith("temporal_") else kind
    candidate, records, label, _ = stress_scenario(seed, split, base_kind)
    at = datetime.fromisoformat(candidate["transaction_date"])
    source = account_identity(candidate["source_account"])
    if kind.startswith("temporal_"):
        receipts, payments = [], []
        for row in records:
            age = (at - datetime.fromisoformat(row["transaction_date"])).total_seconds() / 60
            sender, recipient = (
                account_identity(row["source_account"]),
                account_identity(row["destination_account"]),
            )
            if sender == source and age > 180:
                row["transaction_date"] = (at - timedelta(hours=72 + age / 60)).isoformat()
            elif age < 180 and recipient == source:
                receipts.append(row)
            elif age < 180 and sender == source:
                payments.append(row)
        for index, (receipt, payment) in enumerate(zip(receipts, payments, strict=True)):
            received = at - timedelta(hours=20 - 4 * index)
            receipt["transaction_date"] = received.isoformat()
            payment["transaction_date"] = (
                received + timedelta(minutes=5 if kind == "temporal_fast" else 120)
            ).isoformat()
        label = int(kind == "temporal_fast")
        for row in [candidate, *records]:
            row["id"] += "-" + kind
    if split == "train":
        # Existing stress generator uses September for non-validation splits.
        shift = at.replace(month=1) - at
        for row in [candidate, *records]:
            row["transaction_date"] = (datetime.fromisoformat(row["transaction_date"]) + shift).isoformat()
            for side in ("source_account", "destination_account"):
                account = row[side]
                # Accounts are shared dictionaries in the generator: transform each once below.
                account.setdefault("_original_opening", account["opening_date"])
        for row in [candidate, *records]:
            for side in ("source_account", "destination_account"):
                account = row[side]
                account["opening_date"] = (
                    datetime.fromisoformat(account["_original_opening"]) + shift
                ).isoformat()
        for row in [candidate, *records]:
            for side in ("source_account", "destination_account"):
                row[side].pop("_original_opening", None)
    return candidate, records, label, kind
