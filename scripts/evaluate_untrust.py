"""Reproducible, offline comparison on the existing labeled synthetic graph generator.

This does not estimate performance on real banking traffic. Simulated reception is
chronological event time; live accumulation uses the trusted server reception clock.
"""

import argparse
import json
from collections import Counter
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path

from src.constants import Policy
from src.controllers.account_untrust import UntrustHistory, assess_untrust
from src.controllers.decision_engine import DecisionEngine
from src.controllers.pix_controller import fingerprint
from src.gnn.synthetic import scenario
from src.repositories.pix_repository import History
from src.risk_context import is_night
from src.schemas.pix import PixTransactionCreate


def identity(account):
    value = account.model_dump(mode="json")
    value.pop("opening_date")
    return fingerprint(value)


def replay(candidate, records, policy):
    engine = DecisionEngine(policy)
    past = []
    transactions = [PixTransactionCreate.model_validate(row) for row in [*records, candidate]]
    transactions.sort(key=lambda tx: (tx.transaction_date, tx.id))
    result = None
    for tx in transactions:
        at = tx.transaction_date
        owner = tx.source_account.owner.document_number
        payer = [row for row in past if row[0].source_account.owner.document_number == owner]
        recent = [
            row for row in payer if row[0].transaction_date >= at - timedelta(minutes=policy.velocity_minutes)
        ]
        approved = [row for row in payer if row[1] == "approved"]
        familiar = [
            row for row in approved if row[0].transaction_date >= at - timedelta(days=policy.profile_days)
        ]
        profile = approved[-policy.profile_history_size :]
        if not profile:
            profile = [row for row in payer if row[1] == "two_factor_required"][:1]
        day = [
            row for row in past if row[0].transaction_date >= at - timedelta(hours=policy.device_window_hours)
        ]
        history = History(
            recent_count=len(recent),
            recent_amount=sum(row[0].amount for row in recent),
            approved_count=len(familiar),
            approved_amount=sum(row[0].amount for row in familiar),
            known_destination=any(
                identity(row[0].destination_account) == identity(tx.destination_account) for row in familiar
            ),
            known_device=any(row[0].source.device_id == tx.source.device_id for row in familiar),
            profile_count=len(profile),
            profile_amount=sum(row[0].amount for row in profile),
            registered_count=len(payer),
            device_other_owners=len(
                {
                    row[0].source_account.owner.document_number
                    for row in day
                    if row[0].source.device_id == tx.source.device_id
                    and row[0].source_account.owner.document_number != owner
                }
            ),
            payer_other_devices=len(
                {
                    row[0].source.device_id
                    for row in day
                    if row[0].source_account.owner.document_number == owner
                    and row[0].source.device_id != tx.source.device_id
                }
            ),
            approved_night_count=sum(is_night(row[0].transaction_date, policy) for row in familiar),
        )
        status, metadata = engine.evaluate(tx, history)
        account_history = [
            row
            for row in payer
            if identity(row[0].source_account) == identity(tx.source_account)
            and row[0].transaction_date > at - timedelta(hours=policy.untrust.window_hours)
        ]
        status, untrust, notice = assess_untrust(
            status,
            metadata,
            UntrustHistory(
                sum(row[2] for row in account_history),
                sum(row[2] > 0 for row in account_history),
            ),
            policy.untrust,
            policy.scoring.two_factor_threshold,
        )
        past.append((tx, status, untrust["increment"]))
        if tx.id == candidate["id"]:
            result = status, untrust, notice
    return result


def evaluate(split, size, policy):
    counts = Counter()
    by_kind = {}
    no_untrust = replace(policy, untrust=replace(policy.untrust, enabled=False))
    for seed in range(size):
        candidate, records, fraud, kind = scenario(seed, split)
        baseline = replay(candidate, records, no_untrust)
        current = replay(candidate, records, policy)
        label = "synthetic_fraud" if fraud else "synthetic_legitimate"
        counts[label] += 1
        counts[f"baseline_{label}_{baseline[0]}"] += 1
        counts[f"untrust_{label}_{current[0]}"] += 1
        counts["changed_decisions"] += baseline[0] != current[0]
        counts["notification_indications"] += current[2]["required"]
        counts["additional_legitimate_rejections"] += (
            not fraud and baseline[0] != "rejected" and current[0] == "rejected"
        )
        counts["additional_legitimate_challenges"] += (
            not fraud and baseline[0] == "approved" and current[0] == "two_factor_required"
        )
        counts["additional_fraud_rejections"] += (
            bool(fraud) and baseline[0] != "rejected" and current[0] == "rejected"
        )
        kind_counts = by_kind.setdefault(kind, Counter())
        kind_counts[current[0]] += 1
    return {
        "samples": size,
        "counts": dict(sorted(counts.items())),
        "by_scenario": {kind: dict(values) for kind, values in sorted(by_kind.items())},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    policy = Policy()
    report = {
        "scope": "SYNTHETIC ONLY; not calibrated to real Pix traffic or confirmed fraud outcomes",
        "generator": "src.gnn.synthetic.scenario; seeds 0..N-1; unchanged labeled scenario generator",
        "threshold_selection": "operator hypotheses; automatic blocking disabled after initial validation added 3 legitimate rejections and 0 fraud rejections",
        "evaluation_limit": "both splits were inspected during prototype development; not an untouched final holdout",
        "gnn_mode": "off for both comparison lanes; only rule engine and account history are compared",
        "policy_version": policy.version,
        "untrust_policy": asdict(policy.untrust),
        "validation": evaluate("validation", 150, policy),
        "test": evaluate("test", 200, policy),
        "experimental_blocking_validation": evaluate(
            "validation",
            150,
            replace(
                policy,
                untrust=replace(policy.untrust, rejection_enabled=True),
            ),
        ),
        "experimental_blocking_test": evaluate(
            "test",
            200,
            replace(
                policy,
                untrust=replace(policy.untrust, rejection_enabled=True),
            ),
        ),
    }
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
