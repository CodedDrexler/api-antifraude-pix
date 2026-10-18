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
