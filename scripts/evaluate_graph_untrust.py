"""Offline paired experiment: recent Pix neighbors and independent account untrust.

No API calls, database writes, policy changes, training or confirmed fraud labels.
Histories are replayed once with the existing rules; candidate-only graph changes
share that frozen baseline. Synthetic event time simulates server reception time.
"""

import argparse
import copy
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from src.constants import Policy
from src.controllers.account_untrust import UntrustHistory, assess_untrust
from src.controllers.decision_engine import DecisionEngine
from src.gnn.common import account_identity
from src.gnn.synthetic import scenario
from src.risk.scoring import score_decision
from src.risk.types import History
from src.risk_context import is_night
from src.schemas.pix import PixTransactionCreate

STATUS_ORDER = {"approved": 0, "two_factor_required": 1, "rejected": 2}
METHODS = ("baseline", "count_neighbors", "weighted_neighbors", "weighted_with_repass")
STRESS_KINDS = (
    "mule_direct",
    "mule_two_hops",
    "mule_no_risky_neighbor",
    "mule_first_repass",
    "innocent_payer",
    "merchant",
    "merchant_fast_settlement",
    "normal",
    "stale_contact",
)


def key(account):
    if hasattr(account, "model_dump"):
        account = account.model_dump(mode="json")
    return account_identity(account)


@dataclass(frozen=True)
class GraphPolicy:
    hops: int = 2
    neighbors: int = 10
    window_hours: int = 24
    half_life_hours: int = 12
    hop_decay: float = 0.5
    suspicious_threshold: int = 40
    maximum_points: int = 20
    points_per_suspect: int = 5
    repass_minutes: int = 30
    repass_ratio: float = 0.8
    repass_events: int = 2


@dataclass
class Observation:
    tx: PixTransactionCreate
    status: str
    increment: int


def history_for(tx, past, policy):
    """Mirror repository eligibility, including duplicate attempts and profile fallback."""
    at = tx.transaction_date
    past = [row for row in past if row.tx.transaction_date <= at and row.tx.id != tx.id]
    owner = tx.source_account.owner.document_number
    payer = [r for r in past if r.tx.source_account.owner.document_number == owner]
    recent = [r for r in payer if r.tx.transaction_date >= at - timedelta(minutes=policy.velocity_minutes)]
    approved = [r for r in payer if r.status == "approved"]
    familiar = [r for r in approved if r.tx.transaction_date >= at - timedelta(days=policy.profile_days)]
    profile = approved[-policy.profile_history_size :]
    basis = "approved" if profile else "unavailable"
    day = [r for r in past if r.tx.transaction_date >= at - timedelta(hours=policy.device_window_hours)]
    duplicate = [
        r
        for r in payer
        if r.status != "rejected"
        and key(r.tx.source_account) == key(tx.source_account)
        and key(r.tx.destination_account) == key(tx.destination_account)
        and r.tx.amount == tx.amount
        and r.tx.transaction_date >= at - timedelta(seconds=policy.duplicate_window_seconds)
    ]
    return History(
        recent_count=len(recent),
        recent_amount=sum(r.tx.amount for r in recent),
        approved_count=len(familiar),
        known_destination=any(key(r.tx.destination_account) == key(tx.destination_account) for r in familiar),
        known_device=any(r.tx.source.device_id == tx.source.device_id for r in familiar),
        profile_count=len(profile),
        profile_amount=sum(r.tx.amount for r in profile),
        profile_basis=basis,
        registered_count=len(payer),
        device_other_owners=len(
            {
                r.tx.source_account.owner.document_number
                for r in day
                if r.tx.source.device_id == tx.source.device_id
                and r.tx.source_account.owner.document_number != owner
            }
        ),
        payer_other_devices=len(
            {
                r.tx.source.device_id
                for r in day
                if r.tx.source_account.owner.document_number == owner
                and r.tx.source.device_id != tx.source.device_id
            }
        ),
        approved_night_count=sum(is_night(r.tx.transaction_date, policy) for r in familiar),
        duplicate_transaction_id=duplicate[-1].tx.id if duplicate else None,
        duplicate_elapsed_seconds=(at - duplicate[-1].tx.transaction_date).total_seconds()
        if duplicate
        else None,
    )


def untrust_for(account, at, past, policy):
    rows = [
        r
        for r in past
        if key(r.tx.source_account) == account
        and at - timedelta(hours=policy.untrust.window_hours) < r.tx.transaction_date <= at
    ]
    return UntrustHistory(sum(r.increment for r in rows), sum(r.increment > 0 for r in rows))


def replay(candidate, records, policy):
    engine, past = DecisionEngine(policy), []
    at = datetime.fromisoformat(candidate["transaction_date"])
    # Strictly earlier events; equal timestamps in this offline fixture are excluded.
    unique = {
        r["id"]: r
        for r in records
        if r["id"] != candidate["id"] and datetime.fromisoformat(r["transaction_date"]) < at
    }
    for row in sorted(
        unique.values(), key=lambda r: (datetime.fromisoformat(r["transaction_date"]), r["id"])
    ):
        tx = PixTransactionCreate.model_validate(row)
        status, metadata = engine.evaluate(tx, history_for(tx, past, policy))
        status, untrust, _ = assess_untrust(
            status,
            metadata,
            untrust_for(key(tx.source_account), tx.transaction_date, past, policy),
            policy.untrust,
            policy.scoring.two_factor_threshold,
        )
        past.append(Observation(tx, status, untrust["increment"]))
    tx = PixTransactionCreate.model_validate(candidate)
    rule_status, metadata = engine.evaluate(tx, history_for(tx, past, policy))
    status, _, _ = assess_untrust(
        rule_status,
        metadata,
        untrust_for(key(tx.source_account), at, past, policy),
        policy.untrust,
        policy.scoring.two_factor_threshold,
    )
    return tx, past, rule_status, status, metadata


def graph_signal(tx, past, policy, graph_policy, *, include_rejected=False):
    """Bounded BFS; each account counts once, with independent untrust at decision time."""
    at, root = tx.transaction_date, key(tx.source_account)
    adjacency = defaultdict(dict)
    eligible = [
        r
        for r in past
        if at - timedelta(hours=graph_policy.window_hours) < r.tx.transaction_date < at
        and (include_rejected or r.status != "rejected")
    ]
    for row in eligible:
        left, right = key(row.tx.source_account), key(row.tx.destination_account)
        if left == right:
            continue
        # Keep most recent relationship; record direction separately for explanations.
        adjacency[left][right] = max(
            adjacency[left].get(right, row.tx.transaction_date), row.tx.transaction_date
        )
        adjacency[right][left] = max(
            adjacency[right].get(left, row.tx.transaction_date), row.tx.transaction_date
        )
    frontier, visited, layers = {root: 1.0}, {root}, []
    capped = False
    for depth in range(1, graph_policy.hops + 1):
        next_frontier = {}
        for node, path_weight in frontier.items():
            contacts = sorted(adjacency[node].items(), key=lambda item: (-item[1].timestamp(), item[0]))
            capped |= len(contacts) > graph_policy.neighbors
            for neighbor, event_at in contacts[: graph_policy.neighbors]:
                if neighbor in visited:
                    continue
                age_hours = (at - event_at).total_seconds() / 3600
                weight = path_weight * 2 ** (-age_hours / graph_policy.half_life_hours)
                next_frontier[neighbor] = max(next_frontier.get(neighbor, 0), weight)
        visited.update(next_frontier)
        risk = {node: min(100, untrust_for(node, at, past, policy).points) for node in next_frontier}
        total_weight = sum(next_frontier.values())
        exposure = sum(
            weight * risk[node] / 100
            for node, weight in next_frontier.items()
            if risk[node] >= graph_policy.suspicious_threshold
        ) / max(total_weight, 1e-12)
        layers.append(
            {
                "hop": depth,
                "nodes": len(risk),
                "suspects": sum(value >= graph_policy.suspicious_threshold for value in risk.values()),
                "exposure": exposure * graph_policy.hop_decay ** (depth - 1),
            }
        )
        frontier = next_frontier
    count = sum(layer["suspects"] for layer in layers)
    weighted = graph_policy.maximum_points * max((layer["exposure"] for layer in layers), default=0)
    # Preserve absolute recency after normalizing relative contact weights.
    if adjacency[root]:
        newest = max(adjacency[root].values())
        weighted *= 2 ** (-(at - newest).total_seconds() / 3600 / graph_policy.half_life_hours)
    repasses = rapid_repasses(root, eligible, graph_policy)
    return {
        "count_neighbors": min(graph_policy.maximum_points, count * graph_policy.points_per_suspect),
        "weighted_neighbors": min(graph_policy.maximum_points, math.ceil(weighted - 1e-9)),
        "weighted_with_repass": min(graph_policy.maximum_points, math.ceil(weighted - 1e-9))
        if repasses >= graph_policy.repass_events
        else 0,
        "layers": layers,
        "suspect_nodes": count,
        "rapid_repasses": repasses,
        "visited_nodes": len(visited),
        "neighbor_cap_reached": capped,
    }


def rapid_repasses(root, eligible, policy):
    """Two distinct receive/send pairs, not repeated use of the same incoming funds.

    Pending attempts are only a proxy for settled payments in this dataset.
    This matching is a behavioral indicator, not tracing of the actual funds.
    """
    incoming, matches = [], 0
    for row in sorted(eligible, key=lambda r: (r.tx.transaction_date, r.tx.id)):
        tx = row.tx
        if key(tx.destination_account) == root and key(tx.source_account) != root:
            incoming.append(tx)
        elif key(tx.source_account) == root and key(tx.destination_account) != root:
            candidates = [
                r
                for r in incoming
                if timedelta(0)
                < tx.transaction_date - r.transaction_date
                <= timedelta(minutes=policy.repass_minutes)
                and policy.repass_ratio * r.amount <= tx.amount <= r.amount / policy.repass_ratio
                and key(r.source_account) != key(tx.destination_account)
            ]
            if candidates:
                chosen = max(candidates, key=lambda r: r.transaction_date)
                incoming.remove(chosen)
                matches += 1
    return matches


def add_points(status, metadata, points):
    updated = copy.deepcopy(metadata)
    updated["risk_score"] = min(100, metadata["risk_score"] + points)
    updated["risk_group_count"] += int(points > 0)
    proposed, _ = score_decision(updated, updated["policy"]["scoring"])
    return max((status, proposed), key=STATUS_ORDER.get), updated["risk_score"]


def evaluate_one(candidate, records, policy, graph_policy, *, include_rejected=False):
    tx, past, _, status, metadata = replay(candidate, records, policy)
    started = perf_counter()
    signal = graph_signal(tx, past, policy, graph_policy, include_rejected=include_rejected)
    signal["graph_ms"] = (perf_counter() - started) * 1000
    outcomes = {"baseline": {"status": status, "score": metadata["risk_score"], "points": 0}}
    for method in METHODS[1:]:
        changed, score = add_points(status, metadata, signal[method])
        outcomes[method] = {"status": changed, "score": score, "points": score - metadata["risk_score"]}
    return outcomes, signal


def stress_scenario(seed, split, kind):
    """Independent intent labels for the SOURCE account; includes hard benign cases.

    The rule engine supplies untrust evidence, never scenario labels or seeds.
    """
    rng = random.Random(f"graph-untrust-v1:{split}:{seed}:{kind}")
    at = datetime(2026, 5 if split == "validation" else 9, 20, 15, tzinfo=timezone.utc)
    prefix = f"gu-{split}-{kind}-{seed}"
    accounts, records = {}, []

    def account(index):
        if index not in accounts:
            # Stable pseudo-documents are identity only; no model sees numeric IDs.
            doc = int(hashlib.sha256(f"{prefix}:{index}".encode()).hexdigest()[:14], 16) % 10**11
            accounts[index] = {
                "participant": "12345678",
                "branch": "0001",
                "account_number": f"{prefix}-{index}",
                "opening_date": (at - timedelta(days=3 if index == 3 else rng.randint(90, 500))).isoformat(),
                "owner": {"document_number": f"{doc:011d}"},
            }
        return accounts[index]

    def payment(sender, receiver, minutes, amount=None, device=None):
        return {
            "id": f"{prefix}-{len(records)}",
            "amount": amount or rng.randint(9000, 11000),
            "transaction_date": (at - timedelta(minutes=minutes)).isoformat(),
            "source_account": account(sender),
            "destination_account": account(receiver),
            "source": {
                "device_id": device or f"{prefix}-device-{sender}",
                "channel": "app",
                "ip": "198.51.100.23",
            },
        }

    def add(sender, receiver, minutes, amount=None):
        records.append(payment(sender, receiver, minutes, amount))

    # Independent suspicious neighbors build their own untrust through amount spikes.
    # Benign unusual account: intentionally produces the same untrust, showing its uncertainty.
    risky_count = rng.randint(2, 4)
    for index in range(10, 10 + risky_count):
        add(index, 90, 600, 10_000)
        add(index, 90, 540, 11_000)
        for j in range(4):
            add(index, 90, 300 - j * 35, rng.randint(65_000, 85_000))
    # Establish a quiet payer profile; candidate has no own unusual behavior.
    for minute in (500, 440, 380, 320):
        amount = rng.randint(55_000, 65_000)
        # The first approval must be below the v9 cold-start floor. Later
        # amounts can establish their own profile without trusting pending 2FA.
        add(1, 2, minute, min(amount, 49_999) if minute == 500 else amount)
    risk_target = 10
    if kind in {
        "mule_direct",
        "mule_two_hops",
        "mule_no_risky_neighbor",
        "merchant_fast_settlement",
        "mule_first_repass",
    }:
        target = 20 if kind in {"mule_two_hops", "mule_no_risky_neighbor"} else risk_target
        if kind == "mule_two_hops":
            add(20, risk_target, 155)
        cycles = 1 if kind == "mule_first_repass" else rng.randint(2, 4)
        for j in range(cycles):
            minute = 140 - j * 35
            value = rng.randint(9000, 11000)
            add(30 + j, 1, minute, value)
            add(1, target, minute - rng.randint(2, 9), int(value * rng.uniform(0.82, 0.98)))
    elif kind == "innocent_payer":
        add(1, risk_target, 60)  # Paying a scammer does not make the sender a mule.
    elif kind == "merchant":
        for j in range(18):
            add(risk_target if j == 0 else 30 + j, 1, 150 - j * 5)
    elif kind == "stale_contact":
        add(1, risk_target, 1500, 60_000)
    else:
        for j in range(3):
            add(1, 30 + j, 140 - j * 35)
    # Half the candidates exercise the existing 25-point boundary: new, unfamiliar
    # recipient (counterparty cap). Others exercise a familiar zero-point payment.
    candidate = payment(1, 3 if seed % 2 else 2, 0, rng.randint(55_000, 65_000) if seed % 2 else None)
    candidate["id"] = prefix + "-candidate"
    return candidate, records, int(kind.startswith("mule_")), kind


def binary_metrics(rows, method, target):
    def flagged(row):
        status = row["outcomes"][method]["status"]
        return status == "rejected" if target == "rejected" else status != "approved"

    tp = sum(r["label"] and flagged(r) for r in rows)
    fp = sum(not r["label"] and flagged(r) for r in rows)
    fn = sum(r["label"] and not flagged(r) for r in rows)
    tn = sum(not r["label"] and not flagged(r) for r in rows)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
    }


def summary(rows):
    result = {"samples": len(rows), "fraud_or_mule": sum(r["label"] for r in rows), "methods": {}}
    for method in METHODS:
        changed = [r for r in rows if r["outcomes"][method]["status"] != r["outcomes"]["baseline"]["status"]]
        result["methods"][method] = {
            "rejection": binary_metrics(rows, method, "rejected"),
            "intervention_2fa_or_rejection": binary_metrics(rows, method, "intervention"),
            "changed_decisions": len(changed),
            "additional_fraud_interventions": sum(
                r["label"] and r["outcomes"]["baseline"]["status"] == "approved" for r in changed
            ),
            "additional_legitimate_interventions": sum(
                not r["label"] and r["outcomes"]["baseline"]["status"] == "approved" for r in changed
            ),
            "additional_fraud_rejections": sum(
                r["label"] and r["outcomes"][method]["status"] == "rejected" for r in changed
            ),
            "additional_legitimate_rejections": sum(
                not r["label"] and r["outcomes"][method]["status"] == "rejected" for r in changed
            ),
            "positive_graph_contributions": sum(r["outcomes"][method]["points"] > 0 for r in rows),
            "mean_added_score": sum(r["outcomes"][method]["points"] for r in rows) / len(rows),
            "decisions": dict(Counter(r["outcomes"][method]["status"] for r in rows)),
        }
    result["by_scenario"] = {
        kind: {
            method: {
                "decisions": dict(
                    Counter(r["outcomes"][method]["status"] for r in rows if r["kind"] == kind)
                ),
                "positive_graph_contributions": sum(
                    r["outcomes"][method]["points"] > 0 for r in rows if r["kind"] == kind
                ),
            }
            for method in METHODS
        }
        for kind in sorted({r["kind"] for r in rows})
    }
    times = sorted(r["signal"]["graph_ms"] for r in rows)
    result["diagnostics"] = {
        "with_suspicious_neighbors": sum(r["signal"]["suspect_nodes"] > 0 for r in rows),
        "neighbor_cap_reached": sum(r["signal"]["neighbor_cap_reached"] for r in rows),
        "graph_ms_p50": times[len(times) // 2],
        "graph_ms_p95": times[int(len(times) * 0.95)],
        "max_visited_nodes": max(r["signal"]["visited_nodes"] for r in rows),
        "gnn_status": dict(Counter(r["signal"]["gnn_status"] for r in rows)),
    }
    return result


def fixed_fpr(rows, method, threshold):
    tp = sum(r["label"] and r["outcomes"][method]["score"] >= threshold for r in rows)
    fp = sum(not r["label"] and r["outcomes"][method]["score"] >= threshold for r in rows)
    positives, negatives = sum(r["label"] for r in rows), sum(not r["label"] for r in rows)
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "recall": tp / positives,
        "false_positive_rate": fp / negatives,
        "precision": tp / (tp + fp) if tp + fp else None,
    }


def compare_at_fpr(validation, test):
    # Ranking only: these thresholds do not reproduce hard limits, group counts or account actions.
    comparisons = {}
    for budget in (0.0, 0.01, 0.05):
        methods = {}
        for method in METHODS:
            candidates = [fixed_fpr(validation, method, threshold) for threshold in range(102)]
            feasible = [item for item in candidates if item["false_positive_rate"] <= budget]
            chosen = min(
                feasible, key=lambda item: (-item["recall"], item["false_positive_rate"], item["threshold"])
            )
            methods[method] = {"validation": chosen, "test": fixed_fpr(test, method, chosen["threshold"])}
        comparisons[str(budget)] = methods
    return comparisons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("models/graph-untrust-experiment.metrics.json"))
    parser.add_argument("--rows-output", type=Path, default=Path("tmp/graph-untrust-experiment.rows.json"))
    args = parser.parse_args()
    policy = Policy.from_file("config/risk-policy.json")
    graph_policy = GraphPolicy()
    report = {
        "scope": "SYNTHETIC ONLY; no real confirmed fraud, no deployment or production writes",
        "policy": asdict(policy),
        "graph_policy_frozen_before_evaluation": asdict(graph_policy),
        "methods": list(METHODS),
        "design": {
            "legacy": "Existing unchanged generator, 600 validation/1200 test, fresh seeds 10000+/20000+; labels are scenario fraud intent",
            "stress": "9 explicit source-account scenarios, 50 validation/100 test each; labels are mule intent",
            "stress_boundaries": "Each scenario has half familiar 0-point candidates and half unfamiliar new-recipient 25-point candidates; own behavior is otherwise quiet",
            "split": "May validation and September test; separate synthetic identities; same generator in both",
            "untrust": "Recomputed from independent existing own-account rules, available before candidate; no labels or propagated score",
            "history": "Frozen baseline replay; only final candidate is changed in each method; no full-policy feedback simulation",
            "links": "Non-rejected historical attempts, including pending 2FA, as proxy; not confirmed settled Pix",
            "time": "Ordered event timestamps simulate trusted receipt clock; no out-of-order or delayed-label data",
            "score_thresholds": "Selected on validation per method for score ranking only, with 0/1/5 percent FPR budgets; frozen for test",
            "limitations": "Balanced/enriched synthetic mix; no real-world precision, calibration, money-loss or production latency claim",
            "development_disclosure": "Initial runs inspected during fixture debugging: intended 25-point candidates were below the minimum amount, and stale-contact amounts accidentally changed the payer profile. Corrected and regression-tested; not an untouched confirmatory holdout.",
        },
        "datasets": {},
        "source_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                Path(__file__),
                Path("config/risk-policy.json"),
                Path("src/gnn/synthetic.py"),
                Path("src/controllers/decision_engine.py"),
                Path("src/controllers/account_untrust.py"),
            )
        },
    }
    all_rows = {}
    for dataset in ("legacy", "stress"):
        by_split = {}
        for split in ("validation", "test"):
            rows = []
            offset = 10_000 if split == "validation" else 20_000
            if dataset == "legacy":
                examples = (
                    scenario(offset + i, split) for i in range(600 if split == "validation" else 1200)
                )
            else:
                examples = (
                    stress_scenario(offset + i, split, kind)
                    for kind in STRESS_KINDS
                    for i in range(50 if split == "validation" else 100)
                )
            for candidate, records, label, kind in examples:
                outcomes, signal = evaluate_one(candidate, records, policy, graph_policy)
                rows.append(
                    {
                        "id": candidate["id"],
                        "label": label,
                        "kind": kind,
                        "outcomes": outcomes,
                        "signal": signal,
                    }
                )
            by_split[split] = rows
            print(json.dumps({"dataset": dataset, "split": split, "samples": len(rows)}), flush=True)
        report["datasets"][dataset] = {split: summary(rows) for split, rows in by_split.items()}
        report["datasets"][dataset]["fixed_validation_fpr_score_ranking"] = compare_at_fpr(
            by_split["validation"],
            by_split["test"],
        )
        all_rows[dataset] = by_split
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.rows_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.rows_output.write_text(json.dumps(all_rows, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "rows": str(args.rows_output)}))


if __name__ == "__main__":
    main()
