"""Evaluate frozen GNNs against the v9 PostgreSQL path; never activate or train a model.

Use only a dedicated verification database. Each synthetic scenario is rolled back.
Calibration fixes thresholds before the later test split is generated/evaluated.
Labels describe generator intent, not confirmed fraud or successful 2FA.
"""

import argparse
import hashlib
import json
import math
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from scripts.temporal_graph_examples import KINDS, source_scenario
from src.constants import Policy
from src.controllers.pix_controller import PixController
from src.gnn.evaluation import metrics, select_threshold
from src.gnn.temporal_graph import GraphEvent, build_temporal_graph
from src.gnn.temporal_service import TemporalGraphService, TemporalHistory
from src.repositories.pix_repository import PixRepository
from src.schemas.pix import PixTransactionCreate

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (42, 43, 44)
METHODS = ("score_only_2fa", "corroborated_2fa")
FPR_BUDGET = 0.01
MINIMUM_ADDITIONAL_RECALL = 0.05
MAXIMUM_SUBGROUP_FPR = 0.05
SPLIT_OFFSETS = {"calibration": 710_000, "test": 910_000}


def wilson_interval(events, total):
    """Nominal two-sided 95% binomial interval; not proof of synthetic generalization."""
    if not 0 <= events <= total:
        raise ValueError("Events must fit a nonnegative sample size")
    if total == 0:
        return [0.0, 1.0]
    z = 1.959963984540054
    rate = events / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    half = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def eligible(row, method, view="live"):
    if method not in METHODS:
        raise ValueError("Unknown candidate policy")
    if row["baseline_status"] != "approved":
        return False
    return method == "score_only_2fa" or (
        row["amount"] >= row["no_history_min_amount"] and row[f"{view}_rapid_pairs"] >= 2
    )


def effective_score(row, seed, method, view="live"):
    score = row[f"{view}_scores"][str(seed)]
    return score / 100 if score is not None and eligible(row, method, view) else -1.0


def proposed_status(row, seed, method, threshold, view="live"):
    """Counterfactual only: at most 2FA, no added points or propagated own-risk evidence."""
    score = effective_score(row, seed, method, view)
    if score >= 0 and score >= threshold:
        return "two_factor_required"
    return row["baseline_status"]


def select_intervention_threshold(rows, seed, method):
    # Additional false positives are measured among legitimate payments that
    # the baseline would actually approve, not diluted by existing restrictions.
    available = [row for row in rows if row["baseline_status"] == "approved"]
    labels = [row["label"] for row in available]
    if not any(labels) or all(labels):
        return math.nextafter(1.0, math.inf)
    scores = [effective_score(row, seed, method) for row in available]
    return max(0.0, select_threshold(labels, scores, FPR_BUDGET))


def summarize(rows, seed, method, threshold, view="live"):
    labels = np.array([row["label"] for row in rows], dtype=bool)
    scores = np.array([effective_score(row, seed, method, view) for row in rows])
    result = metrics(labels, scores, threshold)
    before = [row["baseline_status"] for row in rows]
    after = [proposed_status(row, seed, method, threshold, view) for row in rows]
    negative_approved = sum(not row["label"] and row["baseline_status"] == "approved" for row in rows)
    result.update(
        threshold_score_0_100=threshold * 100,
        baseline_statuses=dict(Counter(before)),
        proposed_statuses=dict(Counter(after)),
        additional_fraud_2fa=result["true_positive"],
        additional_legitimate_2fa=result["false_positive"],
        additional_fraud_recall=result["recall"],
        baseline_approved_legitimate=negative_approved,
        additional_legitimate_rate=result["false_positive"] / negative_approved
        if negative_approved
        else None,
        additional_legitimate_rate_ci95=wilson_interval(result["false_positive"], negative_approved),
        additional_rejections=sum(
            a == "rejected" and b != "rejected" for a, b in zip(after, before, strict=True)
        ),
        available_scores=sum(row[f"{view}_scores"][str(seed)] is not None for row in rows),
        by_scenario={},
    )
    for kind in sorted({row["kind"] for row in rows}):
        subset = [row for row in rows if row["kind"] == kind]
        changed = sum(
            proposed_status(row, seed, method, threshold, view) != row["baseline_status"] for row in subset
        )
        available = sum(row["baseline_status"] == "approved" for row in subset)
        result["by_scenario"][kind] = {
            "samples": len(subset),
            "label": subset[0]["label"],
            "baseline_approved": available,
            "additional_2fa": changed,
            "additional_rate": changed / available if available else None,
        }
    return result


def numerical_gate(summary):
    subgroup_rates = [
        value["additional_rate"] or 0 for value in summary["by_scenario"].values() if not value["label"]
    ]
    return {
        "additional_recall_at_least_5_percent": summary["additional_fraud_recall"]
        >= MINIMUM_ADDITIONAL_RECALL,
        "legitimate_rate_upper_ci95_at_most_1_percent": summary["additional_legitimate_rate_ci95"][1]
        <= FPR_BUDGET,
        "worst_legitimate_scenario_rate_at_most_5_percent": max(subgroup_rates, default=1)
        <= MAXIMUM_SUBGROUP_FPR,
        "no_additional_rejections": summary["additional_rejections"] == 0,
        "score_coverage_at_least_95_percent": summary["available_scores"]
        / sum(summary["baseline_statuses"].values())
        >= 0.95,
    }


def evaluate_case(engine, services, policy, candidate, records, label, kind, *, graph_sink=None):
    """Use the actual controller/history queries, simulating chronological server receipt."""

    class Clock:
        current = None

        @classmethod
        def now(cls, tz):
            return cls.current.astimezone(tz)

    transactions = [PixTransactionCreate.model_validate(row) for row in records]
    transactions.sort(key=lambda tx: tx.transaction_date)
    tx = PixTransactionCreate.model_validate(candidate)
    past = []
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                controller = PixController(session, policy)
                with patch("src.controllers.pix_controller.datetime", Clock):
                    for previous in transactions:
                        Clock.current = previous.transaction_date
                        result = controller.analyze(previous)
                        past.append(
                            GraphEvent(
                                previous.model_dump(mode="json"),
                                Clock.current,
                                result.status,
                                result.metadata["account_untrust"]["increment"],
                            )
                        )
                    Clock.current = tx.transaction_date
                    baseline = controller.analyze(tx)
                history = PixRepository(session).temporal_history(tx, tx.transaction_date)
                if graph_sink is not None:
                    if history.abstention:
                        raise ValueError(f"Training history unavailable: {history.abstention}")
                    graph_sink.append(
                        build_temporal_graph(
                            tx.model_dump(mode="json"),
                            history.events,
                            received_at=tx.transaction_date,
                            own_events=history.own_events,
                        )
                    )
                full = TemporalHistory(past, past)
                row = {
                    "id": tx.id,
                    "kind": kind,
                    "label": label,
                    "amount": tx.amount,
                    "no_history_min_amount": policy.no_history_min_amount,
                    "baseline_status": baseline.status,
                    "baseline_score": baseline.metadata["risk_score"],
                    "history_supplied": len(past),
                    "history_selected": len(history.events),
                    "live_scores": {},
                    "full_scores": {},
                    "live_statuses": {},
                }
                for seed, service in services.items():
                    for view, snapshot in (("live", history), ("full", full)):
                        observed = service.assess(tx.model_dump(mode="json"), tx.transaction_date, snapshot)
                        row[f"{view}_scores"][str(seed)] = observed["gnn_score"]
                        row[f"{view}_rapid_pairs"] = (
                            observed.get("normalized_transaction_features", {}).get("rapid_repass_pairs", 0)
                            * 4
                        )
                        if view == "live":
                            row["live_statuses"][str(seed)] = observed["status"]
                return row
        finally:
            transaction.rollback()


def collect(engine, services, policy, split, per_kind):
    rows = []
    started = perf_counter()
    for kind in KINDS:
        for index in range(per_kind):
            candidate, records, label, _ = source_scenario(
                SPLIT_OFFSETS[split] + index, "validation" if split == "calibration" else "test", kind
            )
            rows.append(evaluate_case(engine, services, policy, candidate, records, label, kind))
        print(
            json.dumps(
                {
                    "split": split,
                    "kind": kind,
                    "completed": len(rows),
                    "elapsed_seconds": round(perf_counter() - started, 1),
                }
            ),
            flush=True,
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration-per-kind", type=int, default=50)
    parser.add_argument("--test-per-kind", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("models/gnn-v9-validation.metrics.json"))
    parser.add_argument("--rows-output", type=Path)
    args = parser.parse_args()
    if min(args.calibration_per_kind, args.test_per_kind) < 1:
        parser.error("Scenario counts must be positive")
    url = os.environ.get("PIX_TEST_DATABASE_URL")
    if not url:
        parser.error("PIX_TEST_DATABASE_URL must identify a dedicated verification database")
    policy = Policy.from_file(str(ROOT / "config/risk-policy.json"))
    services = {
        seed: TemporalGraphService(model_path=ROOT / f"models/gnn-directed-temporal-v2-seed-{seed}.json")
        for seed in SEEDS
    }
    if not all(service.enabled for service in services.values()):
        raise RuntimeError("Every predeclared frozen model must load successfully")
    engine = create_engine(url)
    try:
        calibration = collect(engine, services, policy, "calibration", args.calibration_per_kind)
        thresholds = {}
        for seed in SEEDS:
            for method in METHODS:
                thresholds[seed, method] = select_intervention_threshold(calibration, seed, method)
        # Test data are not inspected until every threshold has been frozen.
        testing = collect(engine, services, policy, "test", args.test_per_kind)
    finally:
        engine.dispose()
    runs = []
    for seed in SEEDS:
        for method in METHODS:
            threshold = thresholds[seed, method]
            test_summary = summarize(testing, seed, method, threshold)
            runs.append(
                {
                    "seed": seed,
                    "method": method,
                    "model_sha256": services[seed].model.sha256,
                    "calibration": summarize(calibration, seed, method, threshold),
                    "test": test_summary,
                    "full_history_diagnostic_at_same_threshold": summarize(
                        testing, seed, method, threshold, "full"
                    ),
                    "numerical_gate": numerical_gate(test_summary),
                }
            )
    methods_passing = [
        method
        for method in METHODS
        if all(all(run["numerical_gate"].values()) for run in runs if run["method"] == method)
    ]
    report = {
        "scope": "Synthetic generator labels only; actual PostgreSQL/controller path; no model replacement or activation",
        "policy": asdict(policy),
        "design": {
            "frozen_model_seeds": list(SEEDS),
            "scenario_offsets": SPLIT_OFFSETS,
            "samples": {"calibration": len(calibration), "test": len(testing)},
            "kinds": list(KINDS),
            "threshold_selection": "Maximize additional synthetic positives on calibration at <=1% additional false positives; freeze before test",
            "proposals": {
                "score_only_2fa": "Only approved -> 2FA; no score, own-risk or rejection changes",
                "corroborated_2fa": "Same, with amount >= no_history_min_amount and at least two rapid repass pairs",
            },
            "gate": {
                "max_fpr_upper_ci95": FPR_BUDGET,
                "min_additional_recall": MINIMUM_ADDITIONAL_RECALL,
                "max_legitimate_scenario_fpr": MAXIMUM_SUBGROUP_FPR,
                "min_score_coverage": 0.95,
                "all_three_models_must_pass": True,
            },
            "limitations": [
                "Same artificial generator family as training; new seeds/dates are not independent real-world validation",
                "Chronological receipt simulation, no full feedback loop after hypothetical graph interventions",
                "Intervals are nominal binomial estimates; paired scenarios and seeds are not independent observations",
                "Synthetic class prevalence does not estimate precision or losses in real Pix traffic",
                "Entity-risk contribution disabled; the evaluated baseline is rules plus own account history",
            ],
            "test_is_exploratory_after_this_run": True,
        },
        "runs": runs,
        "decision": {
            "methods_passing_numerical_gates": methods_passing,
            "confirmed_real_outcomes_available": False,
            "enable_contribution": False,
            "retain_mode": "shadow",
            "reason": "No candidate passes every numerical gate"
            if not methods_passing
            else "Synthetic success is insufficient for real-payment activation without confirmed outcomes and prospective monitoring",
        },
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                Path(__file__),
                ROOT / "src/controllers/pix_controller.py",
                ROOT / "src/repositories/pix_repository.py",
                ROOT / "src/gnn/temporal_graph.py",
                ROOT / "scripts/temporal_graph_examples.py",
                ROOT / "scripts/evaluate_graph_untrust.py",
                ROOT / "config/risk-policy.json",
            ]
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.rows_output:
        args.rows_output.parent.mkdir(parents=True, exist_ok=True)
        args.rows_output.write_text(
            json.dumps({"calibration": calibration, "test": testing}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({"report": str(args.output), "decision": report["decision"]}), flush=True)


if __name__ == "__main__":
    main()
