"""Validation-only threshold selection, including constant scores and tied predictions."""

import numpy as np


def select_threshold(labels, scores, budget):
    labels = np.asarray(labels, dtype=bool)
    scores = np.asarray(scores, dtype=np.float64)
    if (
        scores.ndim != 1
        or labels.shape != scores.shape
        or not len(scores)
        or not np.isfinite(scores).all()
        or not 0 <= budget <= 1
        or not labels.any()
        or labels.all()
    ):
        raise ValueError("Threshold selection needs finite scores, both labels and an FPR budget in [0,1]")
    candidates = np.r_[np.unique(scores), np.nextafter(max(scores), np.inf)]
    feasible = []
    for threshold in candidates:
        predicted = scores >= threshold
        tp, fp = int(np.sum(predicted & labels)), int(np.sum(predicted & ~labels))
        fpr = fp / int(np.sum(~labels))
        if fpr <= budget:
            feasible.append((-tp, fp, -float(threshold), float(threshold)))
    return min(feasible)[-1]
