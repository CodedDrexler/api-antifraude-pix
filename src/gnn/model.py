"""Safe JSON weights and NumPy inference for a trained two-layer mean GraphSAGE network."""

import hashlib
import json
from pathlib import Path

import numpy as np

from src.gnn.graph import FEATURE_VERSION, NODE_FEATURES, TRANSACTION_FEATURES, neighbor_mean

HIDDEN = 16
SHAPES = {
    "w1": (NODE_FEATURES * 2, HIDDEN),
    "b1": (HIDDEN,),
    "w2": (HIDDEN * 2, HIDDEN),
    "b2": (HIDDEN,),
    "w3": (HIDDEN * 3 + TRANSACTION_FEATURES, HIDDEN),
    "b3": (HIDDEN,),
    "w4": (HIDDEN, 1),
    "b4": (1,),
}


class GraphSageModel:
    def __init__(self, path: str | Path):
        raw = Path(path).read_bytes()
        if len(raw) > 1_000_000:
            raise ValueError("GNN model artifact is too large")
        artifact = json.loads(raw)
        if (
            artifact.get("feature_version") != FEATURE_VERSION
            or artifact.get("architecture") != "mean-graphsage-2"
        ):
            raise ValueError("Unsupported GNN architecture or feature schema")
        if artifact.get("training_data") != "synthetic":
            raise ValueError("This prototype accepts only explicitly synthetic models")
        self.weights = {name: np.array(artifact["weights"][name], dtype=np.float32) for name in SHAPES}
        for name, shape in SHAPES.items():
            if self.weights[name].shape != shape or not np.isfinite(self.weights[name]).all():
                raise ValueError(f"Invalid GNN parameter: {name}")
        self.version = artifact["model_version"]
        self.sha256 = hashlib.sha256(raw).hexdigest()

    def predict(self, graph):
        w = self.weights
        h = np.maximum(
            np.concatenate([graph.x, neighbor_mean(graph.x, graph.edges)], axis=1) @ w["w1"] + w["b1"], 0
        )
        h = np.maximum(np.concatenate([h, neighbor_mean(h, graph.edges)], axis=1) @ w["w2"] + w["b2"], 0)
        z = np.concatenate([h[graph.targets].reshape(-1), graph.transaction_features])
        z = np.maximum(z @ w["w3"] + w["b3"], 0)
        logit = float((z @ w["w4"] + w["b4"])[0])
        return float(1 / (1 + np.exp(-np.clip(logit, -60, 60))))
