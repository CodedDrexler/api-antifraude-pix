"""New synthetic splits, legitimate lookalikes and bootcamp contract variations.

Ambiguous intent deliberately has an identical observable history to mule_direct.
No identity, scenario name or synthetic label is supplied to the neural network.
"""

import copy
import hashlib
import random
from datetime import datetime

from scripts.bootcamp_graph_cases import cases
from scripts.temporal_graph_examples import KINDS, source_scenario

CONTRACT_KINDS = {
    "contract_habitual": "habitual_payment",
    "contract_new_recipient": "new_recipient_without_other_risk",
    "contract_fast_settlement": "legitimate_fast_settlement",
    "contract_changed_device": "habitual_payment",
    "contract_shared_device": "habitual_payment",
    "contract_risky_senders": "synthetic_mule_with_risky_senders",
}
EXPANDED_KINDS = (*KINDS, *CONTRACT_KINDS, "ambiguous_legitimate_repass")
OFFSETS = {"train": 1_100_000, "validation": 1_200_000, "calibration": 1_300_000, "test": 1_400_000}
MONTHS = {"train": 1, "validation": 4, "calibration": 7, "test": 10}


def false_positive_scenario(seed, split, kind):
    if split not in OFFSETS or kind not in EXPANDED_KINDS:
        raise ValueError("Unknown false-positive scenario or split")
    if kind not in CONTRACT_KINDS:
        base = "mule_direct" if kind == "ambiguous_legitimate_repass" else kind
        candidate, records, label, _ = source_scenario(seed, "test", base)
        if kind == "ambiguous_legitimate_repass":
            label = 0
    else:
        _, candidate, records, label = next(item for item in cases() if item[0] == CONTRACT_KINDS[kind])
        candidate, records = copy.deepcopy((candidate, records))
        rng = random.Random(seed)
        scale = rng.uniform(0.6, 1.8)
        for payload in [candidate, *records]:
            # Preserve a low-value first approval; pending attempts cannot train a profile.
            if payload["amount"] > 49_999:
                payload["amount"] = int(payload["amount"] * scale)
        if kind == "contract_changed_device":
            candidate["source"]["device_id"] += "-replacement"
        if kind == "contract_shared_device":
            at = datetime.fromisoformat(candidate["transaction_date"])
            for index in range(3):
                payload = copy.deepcopy(candidate)
                payload.update(id=f"shared-{index}", amount=1000)
                payload["transaction_date"] = at.replace(hour=12 - index).isoformat()
                payload["source_account"]["account_number"] = f"shared-{index}"
                payload["source_account"]["owner"]["document_number"] = f"{22233344450 + index:011d}"
                records.append(payload)
    # Remap all identities consistently: no payer/device crosses any split or scenario.
    candidate, records = copy.deepcopy((candidate, records))
    prefix = f"fp-{split}-{seed}"
    at = datetime.fromisoformat(candidate["transaction_date"])
    shift = at.replace(month=MONTHS[split]) - at
    for payload in [candidate, *records]:
        payload["id"] = prefix + ":" + payload["id"]
        payload["transaction_date"] = (
            datetime.fromisoformat(payload["transaction_date"]) + shift
        ).isoformat()
        payload["source"]["device_id"] = prefix + ":" + payload["source"]["device_id"]
    # Shared account dicts must be transformed only once.
    seen = set()
    for payload in [candidate, *records]:
        for side in ("source_account", "destination_account"):
            account = payload[side]
            if id(account) in seen:
                continue
            seen.add(id(account))
            account["account_number"] = prefix + ":" + account["account_number"]
            document = account["owner"]["document_number"]
            digest = hashlib.sha256(f"{prefix}:{document}".encode()).hexdigest()
            account["owner"] = {"document_number": f"{int(digest[:14], 16) % 10**11:011d}"}
            account["opening_date"] = (datetime.fromisoformat(account["opening_date"]) + shift).isoformat()
    return candidate, records, label, kind
