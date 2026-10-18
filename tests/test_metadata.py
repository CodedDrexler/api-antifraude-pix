from copy import deepcopy
from unittest.mock import Mock

import pytest
from conftest import request

from src.constants import Policy
from src.controllers.account_untrust import UntrustHistory
from src.controllers.pix_controller import PixController, fingerprint
from src.dtos.pix_dto import PixAnalysisDTO
from src.models.pix import PixAnalysis
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate


def test_compact_metadata_is_default_and_timing_is_saved(payload):
    payload["amount"] = 100_000
    status, response, _ = request("POST", "/pix/transaction", payload)
    assert status == 200
    metadata = response["metadata"]
    assert set(metadata) == {
        "risk_score",
        "risk_level",
        "decision_source",
        "policy_version",
        "processing_time_ms",
        "risk_factors",
        "risk_factors_sum",
        "gnn",
        "account_untrust",
        "bank_notification",
    }
    assert metadata["risk_factors"] == [
        {
            "name": "exposure",
            "label": "Histórico inicial",
            "weight": 100,
            "score": 30,
            "rules": ["first_transaction"],
        }
    ]
    assert metadata["risk_factors_sum"] == metadata["risk_score"] == 30
    assert type(metadata["processing_time_ms"]) is float
    assert metadata["processing_time_ms"] >= 0
    assert set(metadata["gnn"]) == {"mode", "status", "gnn_score", "applied_points"}
    assert request("GET", "/pix/transaction/" + payload["id"])[1] == response
    assert request("POST", "/pix/transaction", payload)[1] == response
    detailed = request("GET", "/pix/transaction/" + payload["id"], include_details=True)[1]
    assert detailed["metadata"]["processing_time_ms"] == metadata["processing_time_ms"]
    assert "policy" in detailed["metadata"]
    assert len(str(metadata)) < len(str(detailed["metadata"])) / 2


def test_compact_hard_limit_explains_block(payload):
    payload["amount"] = 3_000_000
    _, response, _ = request("POST", "/pix/transaction", payload)
    assert response["status"] == "rejected"
    assert response["metadata"]["decision_source"] == "hard_limit"
    assert response["metadata"]["hard_limits"] == ["accumulated_amount_above_limit"]


def test_processing_timer_covers_analysis_and_is_not_recomputed(payload, monkeypatch):
    clock = Mock(side_effect=[1_000_000_000, 1_012_345_000, 2_000_000_000])
    monkeypatch.setattr("src.controllers.pix_controller.perf_counter_ns", clock)
    session = Mock()
    controller = PixController(session, Policy())
    repository = Mock()
    repository.get.return_value = None
    repository.history.return_value = History(0, 0, 0, False, False)
    repository.untrust_history.return_value = UntrustHistory()

    def create(**values):
        assert clock.call_count == 2
        assert values["decision_metadata"]["processing_time_ms"] == 12.345
        return PixAnalysis(**values)

    repository.create.side_effect = create
    controller.repository = repository
    transaction = PixTransactionCreate.model_validate(payload)
    result = controller.analyze(transaction)
    assert result.metadata["processing_time_ms"] == 12.345
    assert session.commit.call_count == 1
    saved = PixAnalysis(analysis_key=result.key, status=result.status, decision_metadata=result.metadata)
    repository.get.return_value = saved
    # Replay needs the original normalized hash, just as a persisted row does.
    saved.payload_hash = fingerprint(transaction.model_dump(mode="json"))
    assert controller.analyze(transaction) == result
    assert repository.create.call_count == 1


def test_legacy_summary_has_no_invented_duration_and_does_not_change_evidence():
    evidence = {
        "risk_score": 30,
        "risk_level": "elevated",
        "decision_source": "risk_score",
        "policy": {"version": "pix-score-v2"},
        "group_scores": {"exposure": {"score": 30}},
        "triggered_rules": [{"code": "amount_requires_two_factor", "group": "exposure"}],
    }
    original = deepcopy(evidence)
    summary = PixAnalysisDTO(key="saved", status="two_factor_required", metadata=evidence).compact()
    assert summary.metadata["processing_time_ms"] is None
    assert summary.metadata["risk_factors"][0]["rules"] == ["amount_requires_two_factor"]
    assert evidence == original


@pytest.mark.parametrize("legacy_mapping", [True, False])
def test_factor_list_and_uncapped_sum_in_both_views(legacy_mapping):
    factors = [
        {"name": "profile", "weight": 100, "score": 80, "rules": ["amount_above_customer_profile"]},
        {"name": "activity", "weight": 100, "score": 80, "rules": ["velocity_above_limit"]},
    ]
    evidence = {"risk_score": 100, "risk_factors": factors}
    if legacy_mapping:
        evidence["risk_factors"] = {f["name"]: {k: v for k, v in f.items() if k != "name"} for f in factors}
    original = deepcopy(evidence)
    model = PixAnalysis(analysis_key="saved", status="rejected", decision_metadata=evidence)
    detailed = PixAnalysisDTO.from_model(model)
    for result in (detailed, detailed.compact()):
        assert result.metadata["risk_factors"] == factors
        assert result.metadata["risk_factors_sum"] == 160
        assert result.metadata["risk_score"] == 100
    assert evidence == original
