"""The temporal case exercises real SQL history, decision, observation and replay."""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from scripts.demo_temporal_graph import reproduce
from scripts.evaluate_graph_untrust import history_for, replay
from scripts.temporal_graph_examples import source_scenario
from src.constants import Policy
from src.controllers.account_untrust import OWN_EVIDENCE_VERSION
from src.controllers.decision_engine import DecisionEngine
from src.controllers.pix_controller import PixController, fingerprint
from src.gnn.temporal_service import ORIGINAL_TEMPORAL_MODEL, TemporalGraphService
from src.models.pix import PixAnalysis
from src.schemas.pix import PixTransactionCreate


def test_export_contains_actual_nodes_edges_and_all_rule_results():
    result = reproduce()
    fast, slow = result["cases"]
    assert len(fast["graph_nodes"]) == 21
    assert len(fast["rules_evaluated"]) == 13
    assert sum(row["triggered"] for row in fast["rules_evaluated"]) == 2
    assert sum(row["contribution"] for row in fast["rules_evaluated"]) == 25
    assert fast["rapid_pairs"] == 2 and slow["rapid_pairs"] == 0
    assert fast["v2_score"] > slow["v2_score"]
    assert {edge["relation"] for edge in fast["graph_edges"]} == {
        "paid_to",
        "received_from",
        "uses_device",
        "used_by",
        "owns",
        "owned_by",
    }
    assert all(edge["source"] < 21 and edge["target"] < 21 for edge in fast["graph_edges"])


def test_v2_case_runs_through_database_decision_and_replay(database_engine, monkeypatch):
    candidate, records, _, _ = source_scenario(500_001, "test", "temporal_fast")
    tx, past, _, _, _ = replay(candidate, records, Policy())
    at = tx.transaction_date

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return at

    monkeypatch.setattr("src.controllers.pix_controller.datetime", Clock)
    with (
        database_engine.connect() as connection,
        connection.begin() as transaction,
        Session(bind=connection, join_transaction_mode="create_savepoint") as session,
    ):
        for index, row in enumerate(past):
            payload = row.tx.model_dump(mode="json")
            _, evidence = DecisionEngine(Policy()).evaluate(
                row.tx, history_for(row.tx, past[:index], Policy())
            )
            evidence["account_untrust"] = {
                "increment": row.increment,
                "evidence_version": OWN_EVIDENCE_VERSION,
            }
            source = {k: v for k, v in payload["source_account"].items() if k != "opening_date"}
            destination = {k: v for k, v in payload["destination_account"].items() if k != "opening_date"}
            session.add(
                PixAnalysis(
                    analysis_key=str(uuid4()),
                    transaction_id=row.tx.id,
                    payload_hash=fingerprint(payload),
                    source_document=row.tx.source_account.owner.document_number,
                    source_account_identity=fingerprint(source),
                    destination_identity=fingerprint(destination),
                    device_id=row.tx.source.device_id,
                    amount=row.tx.amount,
                    transaction_date=row.tx.transaction_date,
                    payload=payload,
                    status=row.status,
                    decision_metadata=evidence,
                    created_at=row.tx.transaction_date,
                )
            )
        session.flush()
        controller = PixController(
            session, Policy(), temporal_service=TemporalGraphService(model_path=ORIGINAL_TEMPORAL_MODEL)
        )
        result = controller.analyze(PixTransactionCreate.model_validate(candidate))
        assert result.status == "approved" and result.metadata["risk_score"] == 25
        assert "gnn" not in result.metadata and "gnn" not in result.metadata["policy"]
        assert result.metadata["gnn_v2"]["status"] == "scored"
        # SQL selects two hops (14 events, 18 nodes). The offline slide supplies
        # all 20 events and 21 nodes, so its 96.9626 prediction is a different input.
        assert result.metadata["gnn_v2"]["history_transactions"] == 14
        assert result.metadata["gnn_v2"]["graph_nodes"] == 18
        assert result.metadata["gnn_v2"]["coverage"]["hops_completed"] == 2
        assert result.metadata["gnn_v2"]["gnn_score"] == pytest.approx(97.3076, abs=0.001)
        assert result.metadata["gnn_v2"]["normalized_transaction_features"]["rapid_repass_pairs"] == 0.5
        assert result.metadata["gnn_v2"]["applied_points"] == 0
        assert result.metadata["account_untrust"]["increment"] == 0
        assert controller.get_analysis(candidate["id"]) == result
        assert controller.analyze(PixTransactionCreate.model_validate(candidate)) == result
        transaction.rollback()
