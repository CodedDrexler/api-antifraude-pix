"""False-positive controls in the counterfactual promotion experiment."""

from copy import deepcopy
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scripts.bootcamp_graph_cases import cases
from scripts.temporal_graph_examples import source_scenario
from scripts.validate_temporal_gnn import (
    evaluate_case,
    numerical_gate,
    proposed_status,
    select_intervention_threshold,
    summarize,
    wilson_interval,
)
from src.constants import Policy
from src.controllers.pix_controller import PixController
from src.gnn.temporal_service import DEFAULT_TEMPORAL_MODEL, ORIGINAL_TEMPORAL_MODEL, TemporalGraphService
from src.models.pix import PixAnalysis
from src.schemas.pix import PixTransactionCreate


def row(score, *, label=0, status="approved", amount=50_000, pairs=2):
    return {
        "kind": "mule_direct" if label else "merchant",
        "label": label,
        "baseline_status": status,
        "amount": amount,
        "no_history_min_amount": 50_000,
        "live_rapid_pairs": pairs,
        "full_rapid_pairs": 2,
        "live_scores": {"42": score},
        "full_scores": {"42": 100},
    }


@pytest.mark.parametrize("status", ["two_factor_required", "rejected"])
@pytest.mark.parametrize("method", ["score_only_2fa", "corroborated_2fa"])
def test_candidate_never_relaxes_or_escalates_an_existing_intervention(status, method):
    sample = row(100, status=status)
    assert proposed_status(sample, 42, method, 0) == status


@pytest.mark.parametrize(
    "score,amount,pairs,expected",
    [
        (100, 49_999, 2, "approved"),
        (100, 50_000, 1, "approved"),
        (100, 50_000, 2, "two_factor_required"),
        (89, 50_000, 2, "approved"),
        (None, 50_000, 2, "approved"),
    ],
)
def test_corroborated_candidate_requires_live_score_amount_and_distinct_rapid_pairs(
    score, amount, pairs, expected
):
    sample = row(score, amount=amount, pairs=pairs)
    original = deepcopy(sample)
    assert proposed_status(sample, 42, "corroborated_2fa", 0.9) == expected
    assert sample == original


def test_unavailable_score_cannot_trigger_even_at_zero_threshold_and_zero_is_a_valid_score():
    assert proposed_status(row(None), 42, "score_only_2fa", 0) == "approved"
    assert proposed_status(row(0), 42, "score_only_2fa", 0) == "two_factor_required"


def test_calibration_cannot_dilute_false_positives_with_already_restricted_legitimate_cases():
    calibration = [row(94), row(20), row(95, label=1), row(90, label=1)]
    calibration.extend(row(100, status="two_factor_required") for _ in range(100))
    threshold = select_intervention_threshold(calibration, 42, "score_only_2fa")
    assert threshold == pytest.approx(0.95)
    assert summarize(calibration, 42, "score_only_2fa", threshold)["additional_legitimate_2fa"] == 0


@pytest.mark.parametrize("label", [0, 1])
def test_calibration_without_both_classes_disables_proposals(label):
    threshold = select_intervention_threshold([row(100, label=label)], 42, "score_only_2fa")
    assert threshold > 1
    assert proposed_status(row(100), 42, "score_only_2fa", threshold) == "approved"


def test_report_separates_false_alarm_rate_from_incremental_legitimate_friction():
    samples = [row(10) for _ in range(99)] + [row(99)]
    samples.extend(row(100, status="two_factor_required") for _ in range(20))
    samples.extend(row(99, label=1) for _ in range(8))
    samples.extend(row(10, label=1) for _ in range(2))
    report = summarize(samples, 42, "score_only_2fa", 0.9)
    assert report["additional_fraud_2fa"] == 8
    assert report["additional_legitimate_2fa"] == 1
    assert report["false_positive_rate"] == pytest.approx(1 / 120)
    assert report["additional_legitimate_rate"] == pytest.approx(1 / 100)
    assert report["additional_rejections"] == 0
    assert numerical_gate(report)["legitimate_rate_upper_ci95_at_most_1_percent"] is False


def test_uncertainty_gate_rejects_tiny_samples_and_point_estimates_at_budget():
    assert wilson_interval(0, 0) == [0, 1]
    assert wilson_interval(0, 10)[1] > 0.01
    assert wilson_interval(0, 600)[1] < 0.01
    assert wilson_interval(6, 600)[1] > 0.01
    with pytest.raises(ValueError):
        wilson_interval(2, 1)


def test_bootcamp_contract_histories_are_valid_and_keep_original_amount_and_account():
    fixtures = list(cases())
    assert fixtures[0][0] == "original_first_pix" and fixtures[0][2] == []
    for _, candidate, history, _ in fixtures:
        tx = PixTransactionCreate.model_validate(candidate)
        assert tx.amount == 150_000
        assert tx.source_account.account_number == "88213"
        for payload in history:
            previous = PixTransactionCreate.model_validate(payload)
            assert previous.transaction_date < tx.transaction_date
    assert fixtures[-1][3] == 1
    assert all(item[3] == 0 for item in fixtures[1:-1])


@pytest.mark.parametrize("model_path", [ORIGINAL_TEMPORAL_MODEL, DEFAULT_TEMPORAL_MODEL])
def test_bootcamp_legitimate_settlement_with_high_gnn_score_remains_approved_in_shadow(
    database_engine, model_path
):
    _, candidate, history, label = next(item for item in cases() if item[0] == "legitimate_fast_settlement")
    assert label == 0

    class Clock:
        current = None

        @classmethod
        def now(cls, tz):
            return cls.current.astimezone(tz)

    with database_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                controller = PixController(
                    session, Policy(), temporal_service=TemporalGraphService(model_path=model_path)
                )
                with patch("src.controllers.pix_controller.datetime", Clock):
                    for payload in sorted(
                        history, key=lambda value: datetime.fromisoformat(value["transaction_date"])
                    ):
                        previous = PixTransactionCreate.model_validate(payload)
                        Clock.current = previous.transaction_date
                        controller.analyze(previous)
                    tx = PixTransactionCreate.model_validate(candidate)
                    Clock.current = tx.transaction_date
                    result = controller.analyze(tx)
                    observed = result.metadata["gnn_v2"]
                    assert observed["status"] == "scored"
                    if model_path == ORIGINAL_TEMPORAL_MODEL:
                        assert observed["gnn_score"] > 99
                        assert observed["training_evidence_policy"] == "pix-score-v7"
                    else:
                        assert observed["gnn_score"] < 3
                        assert observed["training_evidence_policy"] == "pix-score-v9"
                    assert observed["applied_points"] == 0 and observed["decision_override"] is False
                    assert result.status == "approved" and result.metadata["risk_score"] == 0
                    assert result.metadata["account_untrust"]["increment"] == 0
                    assert controller.get_analysis(tx.id) == result
                    assert controller.analyze(tx) == result
        finally:
            transaction.rollback()


@pytest.mark.parametrize("kind", ["temporal_fast", "merchant_fast_settlement"])
def test_validation_uses_real_sql_without_persisting_synthetic_scenarios(database_engine, kind):
    candidate, records, label, _ = source_scenario(970_000, "test", kind)
    query = select(func.count()).select_from(PixAnalysis)
    with database_engine.connect() as connection:
        before = connection.scalar(query)
    result = evaluate_case(
        database_engine, {42: TemporalGraphService()}, Policy(), candidate, records, label, kind
    )
    assert result["label"] == label
    assert result["live_statuses"]["42"] == "scored"
    assert result["history_selected"] <= result["history_supplied"]
    assert 0 <= result["live_scores"]["42"] <= 100
    with database_engine.connect() as connection:
        assert connection.scalar(query) == before
