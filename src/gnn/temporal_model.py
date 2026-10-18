"""Safe, NumPy-only inference for the offline directed-temporal experiment."""

import hashlib
import json
from pathlib import Path

import numpy as np

from src.gnn.temporal_graph import (
    FEATURE_VERSION,
    NODE_FEATURES,
    RELATIONS,
    TRANSACTION_FEATURES,
    relation_mean,
)

HIDDEN = 16


class TemporalModel:
    def __init__(self, path):
        raw = Path(path).read_bytes()
        if len(raw) > 1_000_000:
            raise ValueError("Model artifact too large")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Model artifact must be a JSON object")
        if (
            data.get("feature_version") != FEATURE_VERSION
            or data.get("architecture") != "directed-temporal-sage-2"
            or data.get("training_data") != "synthetic"
            or data.get("relations") != list(RELATIONS)
            or data.get("node_features") != list(NODE_FEATURES)
            or data.get("transaction_features") != list(TRANSACTION_FEATURES)
            or data.get("label_target") != "synthetic_source_mule_intent"
            or not isinstance(data.get("model_version"), str)
            or not 0 < len(data["model_version"]) <= 128
        ):
            raise ValueError("Unsupported experimental schema")
        shapes = {
            "w1": (len(NODE_FEATURES) * (1 + len(RELATIONS)), HIDDEN),
            "b1": (HIDDEN,),
            "w2": (HIDDEN * (1 + len(RELATIONS)), HIDDEN),
            "b2": (HIDDEN,),
            "w3": (4 * HIDDEN + len(TRANSACTION_FEATURES), HIDDEN),
            "b3": (HIDDEN,),
            "w4": (HIDDEN, 1),
            "b4": (1,),
        }
        self.weights = {name: np.array(data["weights"][name], dtype=np.float32) for name in shapes}
        for name, shape in shapes.items():
            if self.weights[name].shape != shape or not np.isfinite(self.weights[name]).all():
                raise ValueError(f"Invalid model parameter: {name}")
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.version = data["model_version"]

    def predict(self, graph):
        w = self.weights
        h = graph.x
        for layer in (1, 2):
            messages = [
                relation_mean(h, edges, weights)
                for edges, weights in zip(graph.edges, graph.edge_weights, strict=True)
            ]
            h = np.maximum(np.concatenate([h, *messages], axis=1) @ w[f"w{layer}"] + w[f"b{layer}"], 0)
        z = np.concatenate([h[graph.targets].reshape(-1), graph.transaction_features])
        z = np.maximum(z @ w["w3"] + w["b3"], 0)
        logit = float((z @ w["w4"] + w["b4"])[0])
        return float(1 / (1 + np.exp(-np.clip(logit, -60, 60))))
