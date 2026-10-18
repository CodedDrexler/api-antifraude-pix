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
from src.errors.pix_errors import TransactionConflict
from src.gnn.synthetic import scenario
from src.risk.attribution import decision_causes
from src.risk.contextual_trust import reference_fields
from src.risk.types import History
from src.risk_context import is_night
from src.schemas.pix import PixTransactionCreate


def identity(account):
    value = account.model_dump(mode="json")
    value.pop("opening_date")
    return fingerprint(value)


def replay(candidate, records, policy, *, include_details=False):
    engine = DecisionEngine(policy)
    past = []
    transactions = [PixTransactionCreate.model_validate(row) for row in [*records, candidate]]
    # Stable arrival order for equal event times, matching the repository's row-ID
    # tie-break. Lexical request IDs must not decide which request sees the other.
    transactions.sort(key=lambda tx: tx.transaction_date)
    result = None
    saved = {}
    for tx in transactions:
        payload_hash = fingerprint(tx.model_dump(mode="json"))
        if tx.id in saved:
            previous_hash, previous_result = saved[tx.id]
            if previous_hash != payload_hash:
                raise TransactionConflict()
            if tx.id == candidate["id"]:
                result = previous_result
            continue
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
        profile_basis = "approved" if profile else "unavailable"
        if not profile:
            profile = [row for row in payer if row[1] == "two_factor_required"][:1]
            if profile:
                profile_basis = "initial_pending_attempt"
        day = [
            row for row in past if row[0].transaction_date >= at - timedelta(hours=policy.device_window_hours)
        ]
        duplicate = next(
            (
                row[0]
                for row in reversed(payer)
                if identity(row[0].source_account) == identity(tx.source_account)
                and identity(row[0].destination_account) == identity(tx.destination_account)
                and row[0].amount == tx.amount
                and row[1] in {"approved", "two_factor_required"}
                and row[0].transaction_date >= at - timedelta(seconds=policy.duplicate_window_seconds)
            ),
            None,
        )
        history = History(
            **reference_fields(
                [(row[0].amount, row[0].transaction_date) for row in reversed(familiar)][
                    : policy.contextual_trust.history_size
                ],
                [
                    (row[0].amount, row[0].transaction_date)
                    for row in reversed(familiar)
                    if identity(row[0].destination_account) == identity(tx.destination_account)
                ][: policy.contextual_trust.history_size],
            )
            if policy.contextual_trust.enabled
            else {},
            recent_count=len(recent),
            recent_amount=sum(row[0].amount for row in recent),
            approved_count=len(familiar),
            known_destination=any(
                identity(row[0].destination_account) == identity(tx.destination_account) for row in familiar
            ),
            known_device=any(row[0].source.device_id == tx.source.device_id for row in familiar),
            profile_count=len(profile),
            profile_amount=sum(row[0].amount for row in profile),
            registered_count=len(payer),
            profile_basis=profile_basis,
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
            duplicate_transaction_id=duplicate.id if duplicate else None,
            duplicate_elapsed_seconds=(at - duplicate.transaction_date).total_seconds()
            if duplicate
            else None,
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
        metadata["account_untrust"] = untrust
        metadata["bank_notification"] = notice
        if untrust["decision_override"]:
            metadata["decision_source"] = "account_untrust"
        metadata["decision_causes"] = decision_causes(metadata, status)
        snapshot = (status, untrust, notice, metadata) if include_details else (status, untrust, notice)
        saved[tx.id] = payload_hash, snapshot
        if tx.id == candidate["id"]:
            result = snapshot
    return result


def evaluate(split, size, policy):
    counts = Counter()
    by_kind = {}
    transitions = {label: Counter() for label in ("synthetic_fraud", "synthetic_legitimate")}
    changed_examples = []
    no_untrust = replace(policy, untrust=replace(policy.untrust, enabled=False))
    for seed in range(size):
        candidate, records, fraud, kind = scenario(seed, split)
        baseline = replay(candidate, records, no_untrust, include_details=True)
        current = replay(candidate, records, policy, include_details=True)
        label = "synthetic_fraud" if fraud else "synthetic_legitimate"
        counts[label] += 1
        transitions[label][f"{baseline[0]} -> {current[0]}"] += 1
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
        counts["additional_fraud_challenges"] += (
            bool(fraud) and baseline[0] == "approved" and current[0] == "two_factor_required"
        )
        if baseline[0] != current[0] and len(changed_examples) < 12:
            changed_examples.append(
                {
                    "seed": seed,
                    "scenario": kind,
                    "label": label,
                    "baseline_status": baseline[0],
                    "untrust_status": current[0],
                    "baseline_risk_score": baseline[3]["risk_score"],
                    "untrust_risk_score": current[3]["risk_score"],
                    "transaction_evidence_changed": any(
                        baseline[3][key] != current[3][key]
                        for key in ("triggered_rules", "profile_average", "approved_transactions")
                    ),
                    "baseline_profile_average": baseline[3]["profile_average"],
                    "untrust_profile_average": current[3]["profile_average"],
                    "decision_source": current[3]["decision_source"],
                    "account_score_before": current[1]["score_before"],
                    "current_increment": current[1]["increment"],
                    "account_score": current[1]["score"],
                    "eligible_rules": current[1]["eligible_rules"],
                }
            )
        kind_counts = by_kind.setdefault(kind, Counter())
        kind_counts[current[0]] += 1
    return {
        "samples": size,
        "counts": dict(sorted(counts.items())),
        "by_scenario": {kind: dict(values) for kind, values in sorted(by_kind.items())},
        "decision_transitions": {
            label: dict(sorted(values.items())) for label, values in transitions.items()
        },
        "changed_examples": changed_examples,
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
