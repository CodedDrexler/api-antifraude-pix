"""Live shadow contract, receipt-clock separation and optional-model failures."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock

import pytest
from conftest import post, seed_profile
from sqlalchemy.exc import OperationalError

from src.constants import Policy
from src.controllers.account_untrust import UntrustHistory
from src.controllers.pix_controller import PixController
from src.gnn.graph import parse_date
from src.gnn.temporal_graph import GraphEvent, build_temporal_graph
from src.gnn.temporal_service import TemporalGraphService, TemporalHistory
from src.models.pix import PixAnalysis
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate


def events_for(payload, received_at):
    result = []
    for index in range(3):
        row = deepcopy(payload)
        row.update(
            id=f"prior-{index}",
            transaction_date=(
                parse_date(payload["transaction_date"]) - timedelta(hours=index + 1)
            ).isoformat(),
        )
        result.append(GraphEvent(row, received_at - timedelta(minutes=index + 1), "approved"))
    return result


def test_live_receipt_clock_allows_backdated_pix_to_use_already_received_history(payload):
    event_at = parse_date(payload["transaction_date"])
    received_at = event_at + timedelta(days=2)
    events = events_for(payload, received_at)
    service = TemporalGraphService()
    result = service.assess(payload, received_at, TemporalHistory(events, []))
    assert result["status"] == "scored"
    assert result["history_transactions"] == 3
    assert result["received_time_cutoff"] == received_at.isoformat()
    assert result["event_time_cutoff"] == payload["transaction_date"]
    assert result["applied_points"] == 0 and result["decision_override"] is False


def test_future_event_date_cannot_hide_independent_own_evidence_received_before_analysis(payload):
    at = parse_date(payload["transaction_date"])
    received_at = at + timedelta(days=2)
    future = deepcopy(payload)
    future.update(id="own-prior", transaction_date=(at + timedelta(days=1)).isoformat())
    own = GraphEvent(future, received_at - timedelta(hours=1), "rejected", 20)
    graph = build_temporal_graph(payload, [own], received_at=received_at, own_events=[own, own])
    assert graph.history_count == 0
    assert graph.x[graph.targets[0], 11] == pytest.approx(0.2)
    assert graph.x[graph.targets[3], 11] == pytest.approx(0.2)
    # The same received evidence expires by server time, not by caller date.
    expired = build_temporal_graph(
        payload, [], received_at=received_at + timedelta(hours=23), own_events=[own]
    )
    assert expired.x[:, 11].max() == 0


@pytest.mark.parametrize("mode,status", [("off", "disabled"), ("shadow", "unavailable")])
def test_missing_v2_model_has_explicit_zero_contribution(tmp_path, payload, mode, status):
    service = TemporalGraphService(mode, tmp_path / "missing.json")
    assert not service.enabled
    result = service.assess(payload, parse_date(payload["transaction_date"]), TemporalHistory())
    assert result["status"] == status
    assert result["gnn_score"] is None
    assert result["applied_points"] == 0 and result["decision_override"] is False


@pytest.mark.parametrize("mode", ["contribute", "on", "typo"])
def test_unvalidated_v2_contribution_cannot_be_enabled_accidentally(mode):
    with pytest.raises(ValueError, match="off or shadow"):
        TemporalGraphService(mode)


@pytest.mark.parametrize(
    "reason", ["history_truncated", "neighborhood_truncated", "own_evidence_truncated", "invalid_history"]
)
def test_incomplete_neighborhood_abstains_without_calling_model(payload, reason):
    service = TemporalGraphService()
    service.model.predict = Mock(side_effect=AssertionError("Must abstain"))
    result = service.assess(
        payload, parse_date(payload["transaction_date"]), TemporalHistory(abstention=reason)
    )
    assert result["status"] == reason and result["gnn_score"] is None
    assert result["history_status"] == "incomplete"
    service.model.predict.assert_not_called()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 2])
def test_invalid_prediction_does_not_escape_as_a_fraud_score(payload, value):
    at = parse_date(payload["transaction_date"])
    service = TemporalGraphService()
    service.model.predict = Mock(return_value=value)
    result = service.assess(payload, at, TemporalHistory(events_for(payload, at), []))
    assert result["status"] == "inference_failed"
    assert result["gnn_score"] is None and result["applied_points"] == 0


def test_high_v2_prediction_remains_observational(payload):
    at = parse_date(payload["transaction_date"])
    service = TemporalGraphService()
    service.model.predict = Mock(return_value=1.0)
    result = service.assess(payload, at, TemporalHistory(events_for(payload, at), []))
    assert result["status"] == "scored" and result["gnn_score"] == 100
    assert result["applied_points"] == 0 and result["decision_override"] is False


def test_http_v2_runs_by_default_and_saved_evidence_is_replayed(api, payload):
    # Distinct recipient documents keep this neighborhood independent of other tests.
    payload["destination_account"]["owner"]["document_number"] = (
        f"{(int(payload['source_account']['owner']['document_number']) + 1) % 10**11:011d}"
    )
    seed_profile(api, payload, 3)
    result = post(api, payload)
    observed = result["metadata"]["gnn_v2"]
    assert observed["mode"] == "shadow" and observed["status"] == "scored"
    assert observed["applied_points"] == 0 and observed["decision_override"] is False
    assert len(observed["model_sha256"]) == 64
    assert result["metadata"]["policy"]["gnn_v2"]["model_sha256"] == observed["model_sha256"]
    assert result["metadata"]["account_untrust"]["increment"] == 0
    assert api("GET", "/pix/transaction/" + payload["id"])[1] == result
    assert post(api, payload) == result


@pytest.mark.parametrize("model_json", ["[]", "null", '"text"', '{"architecture":"invalid"}'])
def test_bad_model_json_is_unavailable_without_breaking_startup(tmp_path, model_json):
    path = tmp_path / "invalid.json"
    path.write_text(model_json)
    assert TemporalGraphService(model_path=path).enabled is False


def mocked_controller(service):
    session = Mock()
    controller = PixController(session, Policy(), temporal_service=service)
    repository = Mock()
    repository.get.return_value = None
    repository.history.return_value = History(0, 0, 3, True, True, 3, 3000)
    repository.untrust_history.return_value = UntrustHistory()
    repository.create.side_effect = lambda **values: PixAnalysis(**values)
    controller.repository = repository
    return controller


@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_disabled_or_unavailable_model_does_not_query_optional_history(tmp_path, payload, mode):
    controller = mocked_controller(TemporalGraphService(mode, tmp_path / "missing.json"))
    controller.repository.temporal_history.side_effect = AssertionError("Should not query")
    assert controller.analyze(PixTransactionCreate.model_validate(payload)).status == "approved"
    controller.repository.temporal_history.assert_not_called()


def test_database_error_in_neighborhood_is_not_hidden_as_a_successful_analysis(payload):
    controller = mocked_controller(TemporalGraphService())
    controller.repository.temporal_history.side_effect = OperationalError("query", {}, Exception("timeout"))
    with pytest.raises(OperationalError):
        controller.analyze(PixTransactionCreate.model_validate(payload))
    controller.session.commit.assert_not_called()


def test_model_prediction_failure_cannot_modify_or_break_rule_decision(payload):
    service = TemporalGraphService()
    service.model.predict = Mock(side_effect=ValueError("invalid output"))
    controller = mocked_controller(service)
    at = parse_date(payload["transaction_date"])
    controller.repository.temporal_history.return_value = TemporalHistory(events_for(payload, at), [])
    result = controller.analyze(PixTransactionCreate.model_validate(payload))
    assert result.status == "approved" and result.metadata["risk_score"] == 0
    assert result.metadata["gnn_v2"]["status"] == "inference_failed"
    assert result.metadata["account_untrust"]["increment"] == 0
