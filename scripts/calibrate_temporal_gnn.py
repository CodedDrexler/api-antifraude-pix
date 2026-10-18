"""Compare point-budget and uncertainty-aware cuts on fresh synthetic SQL splits.

Weights stay frozen. Processes isolate the simulated controller clock and each
scenario rolls back. Both strategies freeze all cuts before test generation.
"""

import argparse
import hashlib
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from sqlalchemy import create_engine

from scripts.bootcamp_graph_cases import cases
from scripts.false_positive_cases import EXPANDED_KINDS, false_positive_scenario
from scripts.validate_temporal_gnn import (
    FPR_BUDGET,
    MAXIMUM_SUBGROUP_FPR,
    METHODS,
    ROOT,
    SEEDS,
    effective_score,
    evaluate_case,
    numerical_gate,
    proposed_status,
    select_intervention_threshold,
    summarize,
    wilson_interval,
)
from src.constants import Policy
from src.gnn.temporal_service import TemporalGraphService

FRESH_OFFSETS = {"calibration": 1_500_000, "test": 1_600_000}
STRATEGIES = ("point_budget", "confidence_budget")


def select_conservative_threshold(rows, seed, method):
    available = [row for row in rows if row["baseline_status"] == "approved"]
    if not any(row["label"] for row in available) or all(row["label"] for row in available):
        return math.nextafter(1.0, math.inf)
    scores = [effective_score(row, seed, method) for row in available]
    negative = sum(not row["label"] for row in available)
    thresholds = {math.nextafter(1.0, math.inf), *(score for score in scores if score >= 0)}
    best, selected = (-1, 0, 0), math.nextafter(1.0, math.inf)
    for threshold in sorted(thresholds, reverse=True):
        flags = [score >= threshold for score in scores]
        fp = sum(flag and not row["label"] for row, flag in zip(available, flags, strict=True))
        if wilson_interval(fp, negative)[1] > FPR_BUDGET:
            continue
        groups = {}
        for row, flag in zip(available, flags, strict=True):
            if not row["label"]:
                errors, count = groups.get(row["kind"], (0, 0))
                groups[row["kind"]] = errors + int(flag), count + 1
        if any(errors / count > MAXIMUM_SUBGROUP_FPR for errors, count in groups.values()):
            continue
        tp = sum(flag and row["label"] for row, flag in zip(available, flags, strict=True))
        rank = (tp, -fp, threshold)
        if rank > best:
            best, selected = rank, threshold
    return selected


def initialize_worker(url, paths, policy):
    global _engine, _services, _policy
    _engine = create_engine(url)
    _services = {key: TemporalGraphService(model_path=path) for key, path in paths.items()}
    _policy = policy


def evaluate_worker(item):
    split, seed, kind = item
    candidate, history, label, _ = false_positive_scenario(seed, split, kind)
    fingerprint = hashlib.sha256(json.dumps([candidate, history, label], sort_keys=True).encode()).hexdigest()
    row = evaluate_case(_engine, _services, _policy, candidate, history, label, kind)
    return row, fingerprint


def collect(pool, split, count):
    items = [(split, FRESH_OFFSETS[split] + index, kind) for kind in EXPANDED_KINDS for index in range(count)]
    rows, fingerprints = [], []
    for row, fingerprint in pool.map(evaluate_worker, items):
        rows.append(row)
        fingerprints.append(fingerprint)
        if len(rows) % count == 0:
            print(json.dumps({"split": split, "kind": row["kind"], "rows": len(rows)}), flush=True)
    return rows, hashlib.sha256("\n".join(fingerprints).encode()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models/false-positive-v1")
    parser.add_argument("--output-dir", type=Path, default=Path("models/false-positive-v1/conservative"))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    url = os.environ.get("PIX_TEST_DATABASE_URL")
    if not url or not 1 <= args.workers <= 8:
        parser.error("Use a dedicated PIX_TEST_DATABASE_URL and 1 to 8 workers")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("Use an empty output directory")
    upstream = json.loads((args.model_dir / "frozen-thresholds.json").read_text())
    paths = {
        **{f"original-{seed}": ROOT / f"models/gnn-directed-temporal-v2-seed-{seed}.json" for seed in SEEDS},
        **{f"candidate-{seed}": args.model_dir / f"gnn-false-positive-v1-seed-{seed}.json" for seed in SEEDS},
    }
    services = {key: TemporalGraphService(model_path=path) for key, path in paths.items()}
    if not all(service.enabled for service in services.values()):
        raise ValueError("All frozen models must load")
    hashes = {key: service.model.sha256 for key, service in services.items()}
    if hashes != upstream["models"]:
        raise ValueError("Models must match the upstream frozen artifacts")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    policy = Policy.from_file(str(ROOT / "config/risk-policy.json"))
    with ProcessPoolExecutor(
        max_workers=args.workers, initializer=initialize_worker, initargs=(url, paths, policy)
    ) as pool:
        calibration, calibration_hash = collect(pool, "calibration", 50)
        selectors = {
            "point_budget": select_intervention_threshold,
            "confidence_budget": select_conservative_threshold,
        }
        thresholds = {
            f"{key}/{method}/{strategy}": selector(calibration, key, method)
            for key in services
            for method in METHODS
            for strategy, selector in selectors.items()
        }
        write_json(args.output_dir / "frozen-thresholds.json", {"models": hashes, "thresholds": thresholds})
        testing, test_hash = collect(pool, "test", 100)
    runs = []
    for key in services:
        for method in METHODS:
            for strategy in STRATEGIES:
                threshold = thresholds[f"{key}/{method}/{strategy}"]
                measured = summarize(testing, key, method, threshold)
                runs.append(
                    {
                        "model": key,
                        "method": method,
                        "strategy": strategy,
                        "calibration": summarize(calibration, key, method, threshold),
                        "test": measured,
                        "numerical_gate": numerical_gate(measured),
                    }
                )
    regressions, engine = [], create_engine(url)
    try:
        for kind, candidate, history, label in cases():
            row = evaluate_case(engine, services, policy, candidate, history, label, kind)
            row["proposals"] = {
                f"{key}/{method}/{strategy}": proposed_status(
                    row, key, method, thresholds[f"{key}/{method}/{strategy}"]
                )
                for key in services
                for method in METHODS
                for strategy in STRATEGIES
            }
            regressions.append(row)
    finally:
        engine.dispose()
    passing = [
        f"{method}/{strategy}"
        for method in METHODS
        for strategy in STRATEGIES
        if all(
            all(run["numerical_gate"].values())
            for run in runs
            if run["model"].startswith("candidate-")
            and run["method"] == method
            and run["strategy"] == strategy
        )
    ]
    write_json(
        args.output_dir / "evaluation.metrics.json",
        {
            "scope": "Fresh synthetic calibration/test; fixed weights; both strategies declared before test; no activation",
            "design": {
                "offsets": FRESH_OFFSETS,
                "samples": {"calibration": 900, "test": 1800},
                "workers": args.workers,
                "strategies": list(STRATEGIES),
                "selection": "Same recall objective; confidence_budget additionally enforces calibration Wilson upper bound <=1% and per-legitimate-group rate <=5%",
                "limitations": "Same synthetic generator, dependent pairs, nominal confidence intervals, no confirmed outcomes",
            },
            "models": hashes,
            "split_sha256": {"calibration": calibration_hash, "test": test_hash},
            "runs": runs,
            "bootcamp_regressions": regressions,
            "decision": {
                "methods_passing_all_candidate_seeds": passing,
                "enable_contribution": False,
                "replace_default_model": False,
            },
            "source_sha256": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in (
                    "scripts/calibrate_temporal_gnn.py",
                    "scripts/false_positive_cases.py",
                    "scripts/validate_temporal_gnn.py",
                    "scripts/bootcamp_graph_cases.py",
                    "scripts/temporal_graph_examples.py",
                    "scripts/evaluate_graph_untrust.py",
                    "src/gnn/temporal_graph.py",
                    "src/gnn/temporal_model.py",
                    "config/risk-policy.json",
                    "examples/pix.json",
                )
            },
        },
    )
    print(json.dumps({"output": str(args.output_dir), "passing": passing}), flush=True)


if __name__ == "__main__":
    main()
