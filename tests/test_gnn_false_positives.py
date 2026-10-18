"""Legitimate lookalikes, split isolation and honest false-positive accounting."""

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from scripts.calibrate_temporal_gnn import evaluate_worker, initialize_worker, select_conservative_threshold
from scripts.false_positive_cases import EXPANDED_KINDS, MONTHS, OFFSETS, false_positive_scenario
from scripts.validate_temporal_gnn import (
    evaluate_case,
    numerical_gate,
    select_intervention_threshold,
    summarize,
)
from src.constants import Policy
from src.gnn.common import account_identity
from src.gnn.temporal_model import TemporalModel
from src.gnn.temporal_service import DEFAULT_TEMPORAL_MODEL, ORIGINAL_TEMPORAL_MODEL, TemporalGraphService
from src.schemas.pix import PixTransactionCreate

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "models/false-positive-v1"


def calibration_row(score, *, label=0, kind="legitimate"):
    return {"kind": kind, "label": label, "baseline_status": "approved", "live_scores": {"42": score}}


def test_conservative_cut_leaves_room_for_sampling_uncertainty():
    rows = [calibration_row(10) for _ in range(549)]
    rows += [calibration_row(94), calibration_row(95, label=1), calibration_row(90, label=1)]
    assert select_intervention_threshold(rows, 42, "score_only_2fa") == pytest.approx(0.9)
    threshold = select_conservative_threshold(rows, 42, "score_only_2fa")
    assert threshold == pytest.approx(0.95)
    measured = summarize(rows, 42, "score_only_2fa", threshold)
    assert measured["additional_fraud_2fa"] == 1
    assert measured["additional_legitimate_2fa"] == 0
    assert measured["additional_legitimate_rate_ci95"][1] <= 0.01


def test_conservative_cut_cannot_hide_errors_in_a_small_legitimate_group():
    rows = [calibration_row(10) for _ in range(1000)]
    rows += [calibration_row(90, kind="rare"), calibration_row(95, kind="rare")]
    rows += [calibration_row(100, label=1), calibration_row(80, label=1)]
    threshold = select_conservative_threshold(rows, 42, "score_only_2fa")
    assert threshold == 1
    assert summarize(rows, 42, "score_only_2fa", threshold)["by_scenario"]["rare"]["additional_2fa"] == 0


def test_conservative_cut_disables_intervention_when_sample_is_too_small():
    rows = [calibration_row(0) for _ in range(10)] + [calibration_row(100, label=1)]
    assert select_conservative_threshold(rows, 42, "score_only_2fa") > 1


@pytest.mark.parametrize("kind", EXPANDED_KINDS)
@pytest.mark.parametrize("split", OFFSETS)
def test_false_positive_histories_are_valid_reproducible_and_strictly_before_candidate(kind, split):
    value = false_positive_scenario(OFFSETS[split], split, kind)
    assert value == false_positive_scenario(OFFSETS[split], split, kind)
    candidate, records, label, returned_kind = value
    tx = PixTransactionCreate.model_validate(candidate)
    assert tx.transaction_date.month == MONTHS[split]
    assert label in (0, 1) and returned_kind == kind
    ids = {tx.id}
    for payload in records:
        previous = PixTransactionCreate.model_validate(payload)
        assert previous.transaction_date < tx.transaction_date
        assert previous.id not in ids
        ids.add(previous.id)


def test_identical_observations_do_not_prove_the_synthetic_source_intent():
    positive = false_positive_scenario(OFFSETS["test"], "test", "mule_direct")
    legitimate = false_positive_scenario(OFFSETS["test"], "test", "ambiguous_legitimate_repass")
    assert positive[:2] == legitimate[:2]
    assert positive[2] == 1 and legitimate[2] == 0


def test_split_identities_and_transaction_ids_do_not_overlap():
    seen_documents, seen_ids, seen_devices = set(), set(), set()
    for split, offset in OFFSETS.items():
        documents, ids, devices = set(), set(), set()
        for kind in EXPANDED_KINDS:
            candidate, history, _, _ = false_positive_scenario(offset, split, kind)
            for payload in [candidate, *history]:
                ids.add(payload["id"])
                devices.add(payload["source"]["device_id"])
                documents.update(
                    payload[side]["owner"]["document_number"]
                    for side in ("source_account", "destination_account")
                )
        assert not documents & seen_documents
        assert not ids & seen_ids
        assert not devices & seen_devices
        seen_documents.update(documents)
        seen_ids.update(ids)
        seen_devices.update(devices)


def test_incoming_and_outgoing_bootcamp_flows_keep_one_account_identity():
    candidate, records, label, _ = false_positive_scenario(
        OFFSETS["test"], "test", "contract_fast_settlement"
    )
    assert label == 0
    root = account_identity(candidate["source_account"])
    incoming = [record for record in records if account_identity(record["destination_account"]) == root]
    outgoing = [record for record in records if account_identity(record["source_account"]) == root]
    assert len(incoming) == 2 and len(outgoing) == 5


def test_suppressing_every_alarm_cannot_pass_the_improvement_gate():
    rows = [
        {
            "kind": "legitimate" if index < 600 else "synthetic_positive",
            "label": int(index >= 600),
            "baseline_status": "approved",
            "live_scores": {"42": 0},
            "amount": 1000,
            "no_history_min_amount": 50_000,
        }
        for index in range(700)
    ]
    measured = summarize(rows, 42, "score_only_2fa", 0.9)
    assert measured["additional_legitimate_2fa"] == 0
    assert measured["additional_fraud_2fa"] == 0
    assert numerical_gate(measured)["additional_recall_at_least_5_percent"] is False


@pytest.mark.parametrize(
    "kind,score,status",
    [
        ("contract_habitual", 0, "approved"),
        ("contract_new_recipient", 15, "approved"),
        ("contract_fast_settlement", 0, "approved"),
        ("contract_changed_device", 20, "approved"),
        ("contract_shared_device", 30, "two_factor_required"),
    ],
)
def test_legitimate_contexts_preserve_bounded_rule_scores_without_a_gnn(database_engine, kind, score, status):
    candidate, records, label, _ = false_positive_scenario(1_800_001, "test", kind)
    assert label == 0
    row = evaluate_case(database_engine, {}, Policy(), candidate, records, label, kind)
    assert row["baseline_score"] == score
    assert row["baseline_status"] == status


@pytest.mark.parametrize(
    "kind", ["contract_fast_settlement", "contract_risky_senders", "ambiguous_legitimate_repass"]
)
def test_training_graph_matches_the_bounded_sql_inference_graph(database_engine, kind):
    candidate, records, label, _ = false_positive_scenario(OFFSETS["validation"], "validation", kind)
    graphs = []
    service = TemporalGraphService()
    row = evaluate_case(
        database_engine, {42: service}, Policy(), candidate, records, label, kind, graph_sink=graphs
    )
    assert len(graphs) == 1
    assert graphs[0].history_count >= 3
    assert np.isfinite(graphs[0].x).all()
    assert (
        round(TemporalModel(DEFAULT_TEMPORAL_MODEL).predict(graphs[0]) * 100, 4) == row["live_scores"]["42"]
    )
    assert datetime.fromisoformat(candidate["transaction_date"]).month == MONTHS["validation"]


def test_parallel_scenarios_keep_their_own_simulated_clock_and_match_sequential_sql(database_engine):
    items = [
        ("test", 1_700_001, "contract_fast_settlement"),
        ("calibration", 1_700_002, "contract_risky_senders"),
    ]
    paths = {42: DEFAULT_TEMPORAL_MODEL}
    url = database_engine.url.render_as_string(hide_password=False)
    with ProcessPoolExecutor(
        max_workers=2, initializer=initialize_worker, initargs=(url, paths, Policy())
    ) as pool:
        parallel = list(pool.map(evaluate_worker, items))
    for (split, seed, kind), (observed, _) in zip(items, parallel, strict=True):
        candidate, records, label, _ = false_positive_scenario(seed, split, kind)
        sequential = evaluate_case(
            database_engine, {42: TemporalGraphService()}, Policy(), candidate, records, label, kind
        )
        assert observed == sequential


def test_frozen_experiment_keeps_separate_thresholds_artifacts_and_all_three_seeds():
    report = json.loads((EXPERIMENT / "evaluation.metrics.json").read_text())
    frozen = json.loads((EXPERIMENT / "frozen-thresholds.json").read_text())
    assert report["models"] == frozen["models"]
    assert len(report["runs"]) == 12
    assert report["design"]["offsets"] == OFFSETS
    assert report["design"]["counts_per_kind"] == {
        "train": 40,
        "validation": 20,
        "calibration": 50,
        "test": 100,
    }
    assert len(set(report["split_sha256"].values())) == 4
    assert len(report["bootcamp_regressions"]) == 5
    for run in report["runs"]:
        key = f"{run['model']}/{run['method']}"
        assert run["calibration"]["threshold"] == frozen["thresholds"][key] == run["test"]["threshold"]
        assert sum(run["test"]["baseline_statuses"].values()) == 1800
        assert run["test"]["additional_rejections"] == 0
    assert hashlib.sha256(ORIGINAL_TEMPORAL_MODEL.read_bytes()).hexdigest() == frozen["models"]["original-42"]
    assert hashlib.sha256(DEFAULT_TEMPORAL_MODEL.read_bytes()).hexdigest() == frozen["models"]["candidate-42"]
    assert report["decision"]["enable_contribution"] is False
    assert report["decision"]["replace_default_model"] is False
    assert all(run["export_max_absolute_error"] < 1e-5 for run in report["training"])


@pytest.mark.parametrize("seed", [42, 43, 44])
def test_candidate_artifact_matches_frozen_hash_and_preserves_its_training_policy(seed):
    path = EXPERIMENT / f"gnn-false-positive-v1-seed-{seed}.json"
    model = TemporalModel(path)
    data = json.loads(path.read_text())
    frozen = json.loads((EXPERIMENT / "frozen-thresholds.json").read_text())
    assert model.sha256 == frozen["models"][f"candidate-{seed}"]
    assert data["training_evidence_policy"] == "pix-score-v9"
    assert model.version == f"gnn-false-positive-v1-seed-{seed}"


@pytest.mark.parametrize("kind", ["contract_fast_settlement", "contract_risky_senders"])
def test_default_shadow_model_separates_bootcamp_regressions_with_frozen_cut(database_engine, kind):
    candidate, history, label, _ = false_positive_scenario(1_900_001, "test", kind)
    row = evaluate_case(
        database_engine, {42: TemporalGraphService()}, Policy(), candidate, history, label, kind
    )
    frozen = json.loads((EXPERIMENT / "conservative/frozen-thresholds.json").read_text())
    threshold = frozen["thresholds"]["candidate-42/score_only_2fa/confidence_budget"]
    assert row["baseline_status"] == "approved"
    assert row["baseline_score"] == 0
    assert (row["live_scores"]["42"] >= threshold * 100) == bool(label)


@pytest.mark.parametrize("invalid", [None, 1, {}, "", "x" * 129])
def test_model_rejects_invalid_training_policy_metadata(tmp_path, invalid):
    data = json.loads(DEFAULT_TEMPORAL_MODEL.read_text())
    data["training_evidence_policy"] = invalid
    path = tmp_path / "invalid-policy.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="training evidence policy"):
        TemporalModel(path)


def test_conservative_experiment_uses_fresh_splits_and_frozen_cuts_for_both_strategies():
    report = json.loads((EXPERIMENT / "conservative/evaluation.metrics.json").read_text())
    frozen = json.loads((EXPERIMENT / "conservative/frozen-thresholds.json").read_text())
    original = json.loads((EXPERIMENT / "frozen-thresholds.json").read_text())
    assert report["design"]["offsets"] == {"calibration": 1_500_000, "test": 1_600_000}
    assert report["models"] == frozen["models"] == original["models"]
    assert len(report["runs"]) == 24
    for run in report["runs"]:
        key = f"{run['model']}/{run['method']}/{run['strategy']}"
        assert run["test"]["threshold"] == run["calibration"]["threshold"] == frozen["thresholds"][key]
        assert sum(run["test"]["baseline_statuses"].values()) == 1800
        assert run["test"]["additional_rejections"] == 0
        if run["strategy"] == "confidence_budget":
            assert run["calibration"]["additional_legitimate_rate_ci95"][1] <= 0.01
            assert all(
                (group["additional_rate"] or 0) <= 0.05
                for group in run["calibration"]["by_scenario"].values()
                if not group["label"]
            )


@pytest.mark.parametrize("filename", ["evaluation.metrics.json", "conservative/evaluation.metrics.json"])
def test_measured_models_cannot_separate_identical_histories_with_opposite_assumed_intents(filename):
    report = json.loads((EXPERIMENT / filename).read_text())
    for run in report["runs"]:
        for split in ("calibration", "test"):
            groups = run[split]["by_scenario"]
            assert (
                groups["mule_direct"]["additional_2fa"]
                == groups["ambiguous_legitimate_repass"]["additional_2fa"]
            )
