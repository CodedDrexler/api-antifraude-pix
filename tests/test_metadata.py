from copy import deepcopy
from dataclasses import fields
from unittest.mock import Mock
from uuid import uuid4

import pytest
from conftest import request, seed_profile
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants import Policy, RuleWeights
from src.controllers.account_untrust import UntrustHistory
from src.controllers.pix_controller import PixController, fingerprint
from src.dtos.pix_dto import PixAnalysisDTO
from src.dtos.rule_aliases import RULE_ALIASES
from src.models.pix import PixAnalysis
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate


def test_minimal_http_response_details_and_saved_audit(database_engine, payload):
    payload["amount"] = 100_000
    # Graph expansion follows holders as well as accounts; isolate the recipient.
    payload["destination_account"]["owner"]["document_number"] = f"{uuid4().int % 10**11:011d}"
    status, response, _ = request("POST", "/pix/transaction", payload)
    assert status == 200
    assert set(response) == {"key", "status", "metadata"}
    assert response["metadata"] == {
        "risk_score": 30,
        "bank_notification_required": False,
    }
    assert request("GET", "/pix/transaction/" + payload["id"])[1] == response
    assert request("POST", "/pix/transaction", payload)[1] == response
    detailed = {**response, "metadata": {**response["metadata"], "rules": ["Primeira transação"]}}
    assert request("POST", "/pix/transaction", payload, include_details=True)[1] == detailed
    assert request("GET", "/pix/transaction/" + payload["id"], include_details=True)[1] == detailed
    with Session(database_engine) as session:
        saved = session.scalar(select(PixAnalysis).where(PixAnalysis.transaction_id == payload["id"]))
        assert "policy" in saved.decision_metadata
        assert type(saved.decision_metadata["processing_time_ms"]) is float
        assert saved.decision_metadata["processing_time_ms"] >= 0
        assert "gnn_v2" in saved.decision_metadata


def test_hard_limit_has_readable_rule_name(payload):
    payload["amount"] = 3_000_000
    status, response, _ = request("POST", "/pix/transaction", payload, include_details=True)
    assert status == 200
    assert response["status"] == "rejected"
    assert "Valor acumulado acima do limite" in response["metadata"]["rules"]
    assert set(response["metadata"]) - {"untrust_score"} == {
        "risk_score",
        "bank_notification_required",
        "rules",
    }


def test_approved_http_response_has_empty_rules_only_when_requested(api, payload):
    seed_profile(api, payload, 1)
    status, response, _ = request("POST", "/pix/transaction", payload)
    assert status == 200
    assert response["status"] == "approved"
    assert response["metadata"]["risk_score"] == 0
    assert "rules" not in response["metadata"]
    for method, path, body in (
        ("POST", "/pix/transaction", payload),
        ("GET", "/pix/transaction/" + payload["id"], None),
    ):
        detailed = request(method, path, body, include_details=True)[1]
        assert detailed == {**response, "metadata": {**response["metadata"], "rules": []}}


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


def test_legacy_summary_does_not_change_evidence():
    evidence = {
        "risk_score": 30,
        "policy": {"version": "pix-score-v2"},
        "group_scores": {"exposure": {"score": 30}},
        "reasons": ["amount_requires_two_factor"],
    }
    original = deepcopy(evidence)
    summary = PixAnalysisDTO(key="saved", status="two_factor_required", metadata=evidence).to_response(
        include_details=True
    )
    assert summary.metadata.rules == ["Valor exige autenticação adicional"]
    assert summary.metadata.untrust_score is None
    assert "untrust_score" not in summary.model_dump()["metadata"]
    assert evidence == original


@pytest.mark.parametrize("legacy_mapping", [True, False])
def test_factor_list_and_uncapped_sum_stay_internal(legacy_mapping):
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
    assert detailed.metadata["risk_factors"] == factors
    assert detailed.metadata["risk_factors_sum"] == 160
    assert detailed.metadata["risk_score"] == 100
    summary = detailed.to_response(include_details=True)
    assert summary.metadata.risk_score == 100
    assert summary.metadata.rules == ["Valor acima do perfil do cliente", "Muitas transações em pouco tempo"]
    assert "risk_factors_sum" not in summary.metadata.model_dump()
    assert evidence == original


def test_all_current_rules_have_readable_aliases():
    assert {field.name for field in fields(RuleWeights)} <= RULE_ALIASES.keys()
    assert all("_" not in label for label in RULE_ALIASES.values())


@pytest.mark.parametrize(
    "graph,expected_score",
    [
        ({}, None),
        ({"gnn_v2": {"mode": "off", "gnn_score": None}}, None),
        ({"gnn_v2": {"mode": "shadow", "status": "unavailable", "gnn_score": None}}, None),
        ({"gnn_v2": {"mode": "shadow", "status": "insufficient_history"}}, None),
        ({"gnn_v2": {"mode": "shadow", "status": "inference_failed", "gnn_score": None}}, None),
        ({"gnn_v2": {"mode": "shadow", "gnn_score": 0}}, 0),
        ({"gnn_v2": {"mode": "shadow", "gnn_score": 97.3076, "applied_points": 0}}, 97.3076),
        ({"gnn": {"mode": "contribute", "gnn_score": 82, "applied_points": 20}}, 82),
        ({"gnn_v2": {"mode": "off"}, "gnn": {"mode": "shadow", "gnn_score": 80}}, None),
    ],
)
def test_public_graph_score_is_present_only_when_available(graph, expected_score):
    evidence = {"risk_score": 0, "bank_notification": {"required": True}, **graph}
    original = deepcopy(evidence)
    result = PixAnalysisDTO(key="saved", status="approved", metadata=evidence).to_response()
    expected = {
        "risk_score": 0,
        "bank_notification_required": True,
    }
    if expected_score is not None:
        expected["untrust_score"] = expected_score
    assert result.model_dump(exclude_unset=True)["metadata"] == expected
    assert ("untrust_score" in result.model_dump()["metadata"]) == (expected_score is not None)
    assert evidence == original


def test_details_only_list_effective_rules_and_mandatory_controls():
    evidence = {
        "risk_score": 0,
        "triggered_rules": [
            {"code": "amount_above_customer_profile", "contribution": 0},
            {"code": "unfamiliar_device", "contribution": 20},
            {"code": "unfamiliar_device", "contribution": 20},
            {"code": "first_transaction", "contribution": 0},
            {"code": "velocity_above_limit", "contribution": 0, "hard_limit": True},
        ],
        "decision_causes": [{"rule_id": "first_transaction"}],
    }
    result = PixAnalysisDTO(key="saved", status="two_factor_required", metadata=evidence)
    basic = result.to_response().model_dump(exclude_unset=True)
    detailed = result.to_response(include_details=True).model_dump(exclude_unset=True)
    assert detailed == {
        **basic,
        "metadata": {
            **basic["metadata"],
            "rules": ["Dispositivo desconhecido", "Primeira transação", "Muitas transações em pouco tempo"],
        },
    }


@pytest.mark.parametrize(
    "cause,label",
    [
        ("account_untrust", "Desconfiança acumulada da conta"),
        ("own_entity_untrust", "Desconfiança acumulada do titular"),
    ],
)
def test_rule_names_explain_accumulated_risk_overrides(cause, label):
    result = PixAnalysisDTO(
        key="saved",
        status="two_factor_required",
        metadata={"risk_score": 0, "triggered_rules": [], "decision_causes": [{"rule_id": cause}]},
    )
    assert result.to_response(include_details=True).metadata.rules == [label]


def test_no_rules_returns_empty_details_instead_of_a_no_rule_alias():
    result = PixAnalysisDTO(
        key="saved", status="approved", metadata={"risk_score": 0, "reasons": ["no_rule_triggered"]}
    )
    assert result.to_response(include_details=True).metadata.rules == []
