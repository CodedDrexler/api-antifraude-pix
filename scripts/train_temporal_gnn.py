"""Paired offline training/evaluation, never imported by or installed in the API.

Same source-intent synthetic data for retrained v1, tabular and directed v2.
Thresholds use validation only. Test labels never select weights or thresholds.
"""

import argparse
import copy
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch
from torch import nn

from scripts.evaluate_graph_untrust import add_points, replay
from scripts.temporal_graph_examples import KINDS, source_scenario
from scripts.train_gnn import GraphSage, metrics, pack
from src.constants import Policy
from src.gnn.evaluation import select_threshold
from src.gnn.graph import build_graph
from src.gnn.model import GraphSageModel
from src.gnn.service import DEFAULT_MODEL
from src.gnn.temporal_graph import (
    FEATURE_VERSION,
    NODE_FEATURES,
    RELATIONS,
    TRANSACTION_FEATURES,
    GraphEvent,
    build_temporal_graph,
)
from src.gnn.temporal_model import HIDDEN, TemporalModel


def events_for(past):
    return [
        GraphEvent(row.tx.model_dump(mode="json"), row.tx.transaction_date, row.status, row.increment)
        for row in past
    ]


def build_dataset(split, count, policy):
    rows, old_graphs, new_graphs = [], [], []
    offset = {"train": 300_000, "validation": 400_000, "test": 500_000}[split]
    for kind in KINDS:
        for index in range(count):
            candidate, records, label, _ = source_scenario(offset + index, split, kind)
            _, past, _, status, metadata = replay(candidate, records, policy)
            events = events_for(past)
            old_graphs.append(build_graph(candidate, [e.payload for e in events]))
            new_graphs.append(build_temporal_graph(candidate, events))
            rows.append(
                {"id": candidate["id"], "kind": kind, "label": label, "status": status, "metadata": metadata}
            )
    return rows, old_graphs, new_graphs


def temporal_pack(graphs):
    xs, targets, transactions = [], [], []
    edges, weights = [[] for _ in RELATIONS], [[] for _ in RELATIONS]
    offset = 0
    for graph in graphs:
        xs.append(graph.x)
        targets.append(graph.targets + offset)
        transactions.append(graph.transaction_features)
        for relation in range(len(RELATIONS)):
            edges[relation].append(graph.edges[relation] + offset)
            weights[relation].append(graph.edge_weights[relation])
        offset += len(graph.x)
    return (
        torch.from_numpy(np.concatenate(xs)),
        tuple(torch.from_numpy(np.concatenate(part, axis=1)) for part in edges),
        tuple(torch.from_numpy(np.concatenate(part)) for part in weights),
        torch.from_numpy(np.stack(targets)),
        torch.from_numpy(np.stack(transactions)),
    )


class DirectedSage(nn.Module):
    def __init__(self):
        super().__init__()
        self.layer1 = nn.Linear(len(NODE_FEATURES) * (1 + len(RELATIONS)), HIDDEN)
        self.layer2 = nn.Linear(HIDDEN * (1 + len(RELATIONS)), HIDDEN)
        self.classifier = nn.Linear(HIDDEN * 4 + len(TRANSACTION_FEATURES), HIDDEN)
        self.output = nn.Linear(HIDDEN, 1)

    def forward(self, x, edges, weights, targets, transaction_features):
        for layer in (self.layer1, self.layer2):
            messages = []
            for relation_edges, relation_weights in zip(edges, weights, strict=True):
                sums = torch.zeros_like(x).index_add_(
                    0, relation_edges[1], x[relation_edges[0]] * relation_weights[:, None]
                )
                counts = torch.zeros((len(x), 1)).index_add_(
                    0, relation_edges[1], torch.ones((relation_edges.shape[1], 1))
                )
                messages.append(sums / counts.clamp_min(1))
            x = layer(torch.cat([x, *messages], dim=1)).relu()
        z = torch.cat([x[targets].reshape(len(targets), -1), transaction_features], dim=1)
        return self.output(self.classifier(z).relu()).squeeze(1)


class Tabular(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(4 * len(NODE_FEATURES) + len(TRANSACTION_FEATURES), HIDDEN),
            nn.ReLU(),
            nn.Linear(HIDDEN, HIDDEN),
            nn.ReLU(),
            nn.Linear(HIDDEN, 1),
        )

    def forward(self, values):
        return self.layers(values).squeeze(1)


def fit(model, training, validation, labels, val_labels, epochs):
    optimizer = torch.optim.Adam(model.parameters(), lr=0.005, weight_decay=0.0001)
    criterion = nn.BCEWithLogitsLoss()
    initial = float(criterion(model(*training), labels).detach())
    best_loss, best_epoch, state = float("inf"), 0, None
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        loss = criterion(model(*training), labels)
        loss.backward()
        optimizer.step()
        model.eval()
        with torch.no_grad():
            value = float(criterion(model(*validation), val_labels))
        if value < best_loss:
            best_loss, best_epoch, state = value, epoch + 1, copy.deepcopy(model.state_dict())
    model.load_state_dict(state)
    model.eval()
    return {
        "best_epoch": best_epoch,
        "validation_loss": best_loss,
        "initial_training_loss": initial,
        "final_training_loss": float(criterion(model(*training), labels).detach()),
    }


def decisions(rows, predictions, threshold):
    predictions = np.asarray(predictions, dtype=np.float64)
    statuses = [
        add_points(row["status"], row["metadata"], 20 if value >= threshold else 0)[0]
        for row, value in zip(rows, predictions, strict=True)
    ]
    positive = sum(row["label"] for row in rows)
    negative = len(rows) - positive
    return {
        "interventions": dict(Counter(statuses)),
        "fraud_interventions": sum(
            bool(row["label"]) and status != "approved" for row, status in zip(rows, statuses, strict=True)
        ),
        "legitimate_interventions": sum(
            not row["label"] and status != "approved" for row, status in zip(rows, statuses, strict=True)
        ),
        "additional_fraud_interventions": sum(
            bool(row["label"]) and row["status"] == "approved" and status != "approved"
            for row, status in zip(rows, statuses, strict=True)
        ),
        "additional_legitimate_interventions": sum(
            not row["label"] and row["status"] == "approved" and status != "approved"
            for row, status in zip(rows, statuses, strict=True)
        ),
        "additional_legitimate_rejections": sum(
            not row["label"] and row["status"] != "rejected" and status == "rejected"
            for row, status in zip(rows, statuses, strict=True)
        ),
        "positives": positive,
        "negatives": negative,
    }


def summarize(validation_rows, test_rows, validation_scores, test_scores):
    validation_scores = np.asarray(validation_scores, dtype=np.float64)
    test_scores = np.asarray(test_scores, dtype=np.float64)
    val_y = np.array([r["label"] for r in validation_rows])
    test_y = np.array([r["label"] for r in test_rows])
    result = {}
    for budget in (0.0, 0.01, 0.05):
        threshold = select_threshold(val_y, validation_scores, budget)
        result[str(budget)] = {
            "validation": metrics(val_y, validation_scores, threshold),
            "test": metrics(test_y, test_scores, threshold),
            "policy_with_20_point_cap": decisions(test_rows, test_scores, threshold),
            "by_scenario": {
                kind: {
                    "samples": sum(r["kind"] == kind for r in test_rows),
                    "flagged": sum(
                        int(r["kind"] == kind and value >= threshold)
                        for r, value in zip(test_rows, test_scores, strict=True)
                    ),
                    "mean_score": float(
                        np.mean(
                            [
                                value
                                for r, value in zip(test_rows, test_scores, strict=True)
                                if r["kind"] == kind
                            ]
                        )
                    ),
                }
                for kind in KINDS
            },
        }
    return result


def export_model(model, path, seed):
    weights = {}
    for index, layer in enumerate((model.layer1, model.layer2, model.classifier, model.output), 1):
        weights[f"w{index}"] = layer.weight.detach().numpy().T.tolist()
        weights[f"b{index}"] = layer.bias.detach().numpy().tolist()
    data = {
        "architecture": "directed-temporal-sage-2",
        "feature_version": FEATURE_VERSION,
        "training_data": "synthetic",
        "model_version": f"gnn-directed-temporal-v2-seed-{seed}",
        "label_target": "synthetic_source_mule_intent",
        "relations": list(RELATIONS),
        "node_features": list(NODE_FEATURES),
        "transaction_features": list(TRANSACTION_FEATURES),
        "seed": seed,
        "weights": weights,
    }
    path.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    return TemporalModel(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--per-kind-train", type=int, default=40)
    parser.add_argument("--per-kind-validation", type=int, default=20)
    parser.add_argument("--per-kind-test", type=int, default=40)
    parser.add_argument("--output", type=Path, default=Path("models/gnn-directed-temporal-v2.metrics.json"))
    parser.add_argument("--rows-output", type=Path, default=Path("tmp/gnn-directed-temporal-v2.rows.json"))
    args = parser.parse_args()
    if min(args.epochs, args.per_kind_train, args.per_kind_validation, args.per_kind_test) < 1:
        parser.error("Counts and epochs must be positive")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    policy = Policy.from_file("config/risk-policy.json")
    datasets = {}
    batches = {"v1_retrained": {}, "v2_tabular": {}, "v2_directed": {}}
    labels = {}
    frozen = GraphSageModel(DEFAULT_MODEL)
    for split in ("train", "validation", "test"):
        count = getattr(args, "per_kind_" + split)
        rows, old_graphs, new_graphs = build_dataset(split, count, policy)
        datasets[split] = rows, old_graphs, new_graphs
        labels[split] = torch.tensor([row["label"] for row in rows], dtype=torch.float32)
        batches["v1_retrained"][split] = pack(old_graphs)
        batches["v2_directed"][split] = temporal_pack(new_graphs)
        batches["v2_tabular"][split] = (
            torch.tensor(
                np.stack(
                    [np.concatenate([g.x[g.targets].reshape(-1), g.transaction_features]) for g in new_graphs]
                )
            ),
        )
        print(json.dumps({"prepared": split, "samples": len(rows)}), flush=True)
    validation_rows, test_rows = datasets["validation"][0], datasets["test"][0]
    frozen_scores = {
        split: np.array([frozen.predict(g) for g in datasets[split][1]]) for split in ("validation", "test")
    }
    predictions = {split: {"frozen_v1": values.tolist()} for split, values in frozen_scores.items()}
    report = {
        "scope": "SYNTHETIC OFFLINE EXPERIMENT ONLY; no API/policy/model replacement or fraud efficacy claim",
        "label_target": "Synthetic SOURCE mule intent; never mixed with legacy transaction-intent labels",
        "policy": asdict(policy),
        "feature_version": FEATURE_VERSION,
        "design": {
            "months": [1, 5, 9],
            "seeds": [42, 43, 44],
            "samples": {split: len(value[0]) for split, value in datasets.items()},
            "kinds": list(KINDS),
            "threshold_budgets": [0, 0.01, 0.05],
            "selection": "Best epoch by validation BCE; threshold by validation FPR; three predeclared seeds, no winner chosen on test",
            "neighborhood": "Both models receive the same full supplied synthetic history, max 300 events; broader than current API's one-neighborhood query",
            "evidence": "Rule-only independent untrust; simulated chronological receipt time; non-rejected attempts are not settled payments",
            "comparison": "Frozen v1 has old transaction-intent training; retrained v1, v2 tabular and v2 graph share source-intent training data",
            "limits": "Same artificial generator across splits, no confirmed outcomes, no delayed/out-of-order receipt simulation, no production calibration",
            "development": "Exploratory experiment; all budgets and seeds are reported, no untouched confirmatory holdout claim",
        },
        "frozen_v1": summarize(
            validation_rows,
            test_rows,
            frozen_scores["validation"],
            frozen_scores["test"],
        ),
        "frozen_v1_at_original_runtime_0_8": {
            "test": metrics(np.array([r["label"] for r in test_rows]), frozen_scores["test"], 0.8),
            "policy_with_20_point_cap": decisions(test_rows, frozen_scores["test"], 0.8),
        },
        "baseline": decisions(test_rows, np.zeros(len(test_rows)), 1),
        "runs": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for seed in (42, 43, 44):
        for name, constructor in (
            ("v1_retrained", GraphSage),
            ("v2_tabular", Tabular),
            ("v2_directed", DirectedSage),
        ):
            torch.manual_seed(seed)
            model = constructor()
            training = fit(
                model,
                batches[name]["train"],
                batches[name]["validation"],
                labels["train"],
                labels["validation"],
                args.epochs,
            )
            with torch.no_grad():
                val_scores = model(*batches[name]["validation"]).sigmoid().numpy()
                test_scores = model(*batches[name]["test"]).sigmoid().numpy()
            run = {
                "seed": seed,
                "method": name,
                "training": training,
                "comparison": summarize(validation_rows, test_rows, val_scores, test_scores),
            }
            predictions["validation"][f"{name}_seed_{seed}"] = val_scores.tolist()
            predictions["test"][f"{name}_seed_{seed}"] = test_scores.tolist()
            if name == "v2_directed":
                path = args.output.parent / f"gnn-directed-temporal-v2-seed-{seed}.json"
                exported = export_model(model, path, seed)
                numpy_scores = np.array([exported.predict(g) for g in datasets["test"][2]])
                error = float(np.max(np.abs(numpy_scores - test_scores)))
                if error > 1e-5:
                    raise RuntimeError(f"Export parity failed: {error}")
                run.update(export_max_absolute_error=error, model_sha256=exported.sha256)
            report["runs"].append(run)
            print(json.dumps({"seed": seed, "method": name, "done": True}), flush=True)
    report["source_sha256"] = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            Path(__file__),
            Path("scripts/temporal_graph_examples.py"),
            Path("src/gnn/temporal_graph.py"),
            Path("src/gnn/temporal_model.py"),
            Path("src/gnn/evaluation.py"),
            Path("scripts/evaluate_graph_untrust.py"),
            Path("config/risk-policy.json"),
            Path("models/gnn-synthetic-v1.json"),
        )
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.rows_output.parent.mkdir(parents=True, exist_ok=True)
    row_report = {
        split: [
            {
                "id": row["id"],
                "kind": row["kind"],
                "label": row["label"],
                "baseline_status": row["status"],
                "baseline_score": row["metadata"]["risk_score"],
                "model_scores": {name: values[index] for name, values in predictions[split].items()},
            }
            for index, row in enumerate(datasets[split][0])
        ]
        for split in ("validation", "test")
    }
    args.rows_output.write_text(json.dumps(row_report, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output)}), flush=True)


if __name__ == "__main__":
    main()
