"""Train with legitimate lookalikes and compare frozen models on new SQL histories.

Four disjoint scenario ranges: training, early stopping, threshold calibration,
then test. The original model files and API configuration are never overwritten.
"""

import argparse
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

import numpy as np
import torch
from sqlalchemy import create_engine

from scripts.bootcamp_graph_cases import cases
from scripts.false_positive_cases import EXPANDED_KINDS, MONTHS, OFFSETS, false_positive_scenario
from scripts.train_temporal_gnn import DirectedSage, export_model, fit, temporal_pack
from scripts.validate_temporal_gnn import (
    METHODS,
    ROOT,
    SEEDS,
    evaluate_case,
    numerical_gate,
    proposed_status,
    select_intervention_threshold,
    summarize,
)
from src.constants import Policy
from src.gnn.temporal_service import TemporalGraphService


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def collect(engine, policy, split, count, services, *, graphs=None):
    rows, hashes = [], []
    started = perf_counter()
    for kind in EXPANDED_KINDS:
        for index in range(count):
            candidate, history, label, _ = false_positive_scenario(OFFSETS[split] + index, split, kind)
            hashes.append(
                hashlib.sha256(json.dumps([candidate, history, label], sort_keys=True).encode()).hexdigest()
            )
            rows.append(
                evaluate_case(engine, services, policy, candidate, history, label, kind, graph_sink=graphs)
            )
        print(
            json.dumps(
                {
                    "split": split,
                    "kind": kind,
                    "rows": len(rows),
                    "seconds": round(perf_counter() - started, 1),
                }
            ),
            flush=True,
        )
    return rows, hashlib.sha256("\n".join(hashes).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("models/false-positive-v1"))
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--train-per-kind", type=int, default=40)
    parser.add_argument("--validation-per-kind", type=int, default=20)
    parser.add_argument("--calibration-per-kind", type=int, default=50)
    parser.add_argument("--test-per-kind", type=int, default=100)
    args = parser.parse_args()
    if min(args.epochs, *(getattr(args, f"{split}_per_kind") for split in OFFSETS)) < 1:
        parser.error("Counts and epochs must be positive")
    url = os.environ.get("PIX_TEST_DATABASE_URL")
    if not url:
        parser.error("Use PIX_TEST_DATABASE_URL for a dedicated disposable database")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("Use an empty output directory; completed experiments must remain frozen")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    policy = Policy.from_file(str(ROOT / "config/risk-policy.json"))
    engine = create_engine(url)
    services = {
        f"original-{seed}": TemporalGraphService(
            model_path=ROOT / f"models/gnn-directed-temporal-v2-seed-{seed}.json"
        )
        for seed in SEEDS
    }
    report = {
        "scope": "Synthetic false-positive experiment; no API activation or confirmed fraud outcomes",
        "policy": asdict(policy),
        "design": {
            "offsets": OFFSETS,
            "months": MONTHS,
            "kinds": list(EXPANDED_KINDS),
            "seeds": list(SEEDS),
            "epochs": args.epochs,
            "counts_per_kind": {split: getattr(args, f"{split}_per_kind") for split in OFFSETS},
            "history": "Actual PostgreSQL/controller bounded neighborhood for training and evaluation",
            "selection": "Epoch by separate validation BCE; thresholds by separate calibration; no test retuning or winning-seed selection",
            "ambiguous_pair": "mule_direct and ambiguous_legitimate_repass have identical observed inputs and opposite assumed intents; neither can be perfectly distinguished",
            "limitations": [
                "New synthetic seeds are not new real-world populations or confirmed outcomes",
                "Same generator families across splits; bootcamp original cases are development regressions",
                "Paired scenarios and seeds are dependent; nominal binomial intervals are exploratory",
                "No confirmed settlements, delayed receipts, authentication outcomes or intervention feedback loop",
            ],
        },
        "split_sha256": {},
        "training": [],
    }
    try:
        batches, labels = {}, {}
        for split in ("train", "validation"):
            graphs = []
            rows, report["split_sha256"][split] = collect(
                engine, policy, split, getattr(args, f"{split}_per_kind"), {}, graphs=graphs
            )
            batches[split] = temporal_pack(graphs)
            labels[split] = torch.tensor([row["label"] for row in rows], dtype=torch.float32)
            if split == "validation":
                validation_graphs = graphs
        for seed in SEEDS:
            torch.manual_seed(seed)
            model = DirectedSage()
            training = fit(
                model,
                batches["train"],
                batches["validation"],
                labels["train"],
                labels["validation"],
                args.epochs,
            )
            path = args.output_dir / f"gnn-false-positive-v1-seed-{seed}.json"
            exported = export_model(
                model,
                path,
                seed,
                model_version=f"gnn-false-positive-v1-seed-{seed}",
                training_policy=policy.version,
            )
            with torch.no_grad():
                predictions = model(*batches["validation"]).sigmoid().numpy()
            error = float(
                np.max(np.abs(predictions - [exported.predict(graph) for graph in validation_graphs]))
            )
            if error > 1e-5:
                raise RuntimeError(f"Export parity failed: {error}")
            services[f"candidate-{seed}"] = TemporalGraphService(model_path=path)
            report["training"].append({"seed": seed, **training, "export_max_absolute_error": error})
            print(json.dumps({"trained_seed": seed, **training}), flush=True)
        if not all(service.enabled for service in services.values()):
            raise RuntimeError("All original and candidate artifacts must load")
        report["models"] = {key: service.model.sha256 for key, service in services.items()}
        calibration, report["split_sha256"]["calibration"] = collect(
            engine, policy, "calibration", args.calibration_per_kind, services
        )
        thresholds = {
            f"{key}/{method}": select_intervention_threshold(calibration, key, method)
            for key in services
            for method in METHODS
        }
        # Persist every threshold and model hash before any test case is generated.
        write_json(
            args.output_dir / "frozen-thresholds.json", {"models": report["models"], "thresholds": thresholds}
        )
        testing, report["split_sha256"]["test"] = collect(
            engine, policy, "test", args.test_per_kind, services
        )
        report["runs"] = []
        for key in services:
            for method in METHODS:
                threshold = thresholds[f"{key}/{method}"]
                measured = summarize(testing, key, method, threshold)
                report["runs"].append(
                    {
                        "model": key,
                        "method": method,
                        "calibration": summarize(calibration, key, method, threshold),
                        "test": measured,
                        "numerical_gate": numerical_gate(measured),
                    }
                )
        report["bootcamp_regressions"] = []
        for kind, candidate, history, label in cases():
            row = evaluate_case(engine, services, policy, candidate, history, label, kind)
            row["proposals"] = {
                f"{key}/{method}": proposed_status(row, key, method, thresholds[f"{key}/{method}"])
                for key in services
                for method in METHODS
            }
            report["bootcamp_regressions"].append(row)
        passing = [
            method
            for method in METHODS
            if all(
                all(run["numerical_gate"].values())
                for run in report["runs"]
                if run["model"].startswith("candidate-") and run["method"] == method
            )
        ]
        report["decision"] = {
            "methods_passing_all_candidate_seeds": passing,
            "enable_contribution": False,
            "replace_default_model": False,
            "retain_mode": "shadow",
        }
        report["source_sha256"] = {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/improve_temporal_gnn.py",
                "scripts/false_positive_cases.py",
                "scripts/train_temporal_gnn.py",
                "scripts/validate_temporal_gnn.py",
                "scripts/bootcamp_graph_cases.py",
                "scripts/temporal_graph_examples.py",
                "scripts/evaluate_graph_untrust.py",
                "src/gnn/temporal_graph.py",
                "src/gnn/temporal_model.py",
                "src/controllers/pix_controller.py",
                "src/repositories/pix_repository.py",
                "config/risk-policy.json",
                "examples/pix.json",
            )
        }
        write_json(args.output_dir / "evaluation.metrics.json", report)
        print(json.dumps({"output": str(args.output_dir), "decision": report["decision"]}), flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
