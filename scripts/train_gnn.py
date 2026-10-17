"""Train a real GraphSAGE network on synthetic graphs and export safe, portable JSON weights."""

import argparse
import copy
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from src.gnn.graph import FEATURE_VERSION, NODE_FEATURES, TRANSACTION_FEATURES, build_graph
from src.gnn.model import HIDDEN, GraphSageModel
from src.gnn.synthetic import scenario


def pack(graphs):
    features, edges, targets, transactions = [], [], [], []
    offset = 0
    for graph in graphs:
        features.append(graph.x)
        edges.append(graph.edges + offset)
        targets.append(graph.targets + offset)
        transactions.append(graph.transaction_features)
        offset += len(graph.x)
    return tuple(
        torch.from_numpy(array)
        for array in (
            np.concatenate(features),
            np.concatenate(edges, axis=1),
            np.stack(targets),
            np.stack(transactions),
        )
    )


class GraphSage(nn.Module):
    def __init__(self):
        super().__init__()
        self.layer1 = nn.Linear(NODE_FEATURES * 2, HIDDEN)
        self.layer2 = nn.Linear(HIDDEN * 2, HIDDEN)
        self.classifier = nn.Linear(HIDDEN * 3 + TRANSACTION_FEATURES, HIDDEN)
        self.output = nn.Linear(HIDDEN, 1)

    @staticmethod
    def mean_neighbors(x, edges):
        sums = torch.zeros_like(x).index_add_(0, edges[1], x[edges[0]])
        counts = torch.zeros((len(x), 1), dtype=x.dtype).index_add_(
            0, edges[1], torch.ones((edges.shape[1], 1))
        )
        return sums / counts.clamp_min(1)

    def forward(self, x, edges, targets, transaction_features):
        h = self.layer1(torch.cat([x, self.mean_neighbors(x, edges)], dim=1)).relu()
        h = self.layer2(torch.cat([h, self.mean_neighbors(h, edges)], dim=1)).relu()
        z = torch.cat([h[targets].reshape(len(targets), -1), transaction_features], dim=1)
        return self.output(self.classifier(z).relu()).squeeze(1)


def dataset(split, count):
    examples = [scenario(i, split) for i in range(count)]
    graphs = [build_graph(candidate, history) for candidate, history, _, _ in examples]
    return graphs, np.array([item[2] for item in examples], dtype=np.float32)


def metrics(labels, predictions, threshold):
    predicted = predictions >= threshold
    positive = labels.astype(bool)
    tp, fp = int(np.sum(predicted & positive)), int(np.sum(predicted & ~positive))
    tn, fn = int(np.sum(~predicted & ~positive)), int(np.sum(~predicted & positive))
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    # Pairwise AUROC correctly gives half credit for tied predictions.
    positives, negatives = predictions[positive], predictions[~positive]
    auc = float(
        np.mean((positives[:, None] > negatives).astype(float) + 0.5 * (positives[:, None] == negatives))
    )
    return {
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "false_positive_rate": fp / max(fp + tn, 1),
        "f1": 2 * precision * recall / max(precision + recall, 1e-9),
        "roc_auc": auc,
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("models/gnn-synthetic-v1.json"))
    parser.add_argument("--epochs", type=int, default=160)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("epochs must be positive")
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    train_graphs, train_labels = dataset("train", 500)
    val_graphs, val_labels = dataset("validation", 150)
    test_graphs, test_labels = dataset("test", 200)
    train_batch, val_batch, test_batch = pack(train_graphs), pack(val_graphs), pack(test_graphs)
    model = GraphSage()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.005, weight_decay=0.0001)
    criterion = nn.BCEWithLogitsLoss()
    best_loss, best_state, best_epoch = float("inf"), None, None
    initial_loss = float(criterion(model(*train_batch), torch.from_numpy(train_labels)).detach())
    for epoch in range(args.epochs):
        model.train()
        optimizer.zero_grad()
        loss = criterion(model(*train_batch), torch.from_numpy(train_labels))
        loss.backward()
        optimizer.step()
        model.eval()
        with torch.no_grad():
            validation_loss = float(criterion(model(*val_batch), torch.from_numpy(val_labels)))
        if validation_loss < best_loss:
            best_loss, best_state, best_epoch = validation_loss, copy.deepcopy(model.state_dict()), epoch + 1
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        val_scores = model(*val_batch).sigmoid().numpy()
        test_scores = model(*test_batch).sigmoid().numpy()
        final_loss = float(criterion(model(*train_batch), torch.from_numpy(train_labels)))
    # Select the threshold on validation only, then freeze before evaluating test.
    thresholds = np.arange(0.5, 0.96, 0.05)
    chosen = min(thresholds, key=lambda t: (-metrics(val_labels, val_scores, float(t))["f1"], -t))
    weights = {}
    for index, layer in enumerate((model.layer1, model.layer2, model.classifier, model.output), 1):
        weights[f"w{index}"] = layer.weight.detach().numpy().T.tolist()
        weights[f"b{index}"] = layer.bias.detach().numpy().tolist()
    artifact = {
        "architecture": "mean-graphsage-2",
        "feature_version": FEATURE_VERSION,
        "model_version": "gnn-synthetic-v1",
        "training_data": "synthetic",
        "seed": args.seed,
        "weights": weights,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, separators=(",", ":")) + "\n")
    exported = GraphSageModel(args.output)
    numpy_scores = np.array([exported.predict(graph) for graph in test_graphs])
    max_error = float(np.max(np.abs(numpy_scores - test_scores)))
    if max_error > 1e-5:
        raise RuntimeError(f"Export parity check failed: {max_error}")
    times = []
    for graph in test_graphs:
        started = time.perf_counter()
        exported.predict(graph)
        times.append((time.perf_counter() - started) * 1000)
    no_edges = (test_batch[0], torch.empty((2, 0), dtype=torch.long), test_batch[2], test_batch[3])
    with torch.no_grad():
        ablated = model(*no_edges).sigmoid().numpy()
    report = {
        "scope": "SYNTHETIC DATA ONLY; no claim about real Pix fraud detection",
        "seed": args.seed,
        "torch_version": torch.__version__,
        "best_epoch": best_epoch,
        "initial_training_loss": initial_loss,
        "final_training_loss": final_loss,
        "split": {
            "train": 500,
            "validation": 150,
            "test": 200,
            "entity_disjoint": True,
            "chronological_months": [1, 5, 9],
        },
        "validation": metrics(val_labels, val_scores, float(chosen)),
        "test": metrics(test_labels, test_scores, float(chosen)),
        "test_at_runtime_threshold_0_8": metrics(test_labels, test_scores, 0.8),
        "no_message_passing_ablation": metrics(test_labels, ablated, float(chosen)),
        "export_max_absolute_error": max_error,
        "numpy_inference_p95_ms": float(np.percentile(times, 95)),
        "model_sha256": exported.sha256,
    }
    args.output.with_suffix(".metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key not in {"validation"}}, indent=2))


if __name__ == "__main__":
    main()
