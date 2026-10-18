import json
from datetime import datetime, timezone
from hashlib import sha256
from time import perf_counter_ns
from uuid import uuid4

from sqlalchemy.orm import Session

from src.constants import Policy
from src.controllers.account_untrust import UntrustHistory, assess_untrust
from src.controllers.decision_engine import DecisionEngine
from src.dtos.pix_dto import PixAnalysisDTO
from src.entity_risk import EntityRiskService, combine_entity_risk
from src.errors.pix_errors import AnalysisNotFound, TransactionConflict
from src.gnn.service import HISTORY_DAYS, MAX_HISTORY, GraphRiskService, combine_graph_risk
from src.gnn.temporal_service import TemporalGraphService, TemporalHistory
from src.repositories.pix_repository import PixRepository
from src.risk.attribution import decision_causes
from src.schemas.pix import PixTransactionCreate


def fingerprint(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PixController:
    def __init__(
        self,
        session: Session,
        policy: Policy,
        graph_service: GraphRiskService | None = None,
        entity_service: EntityRiskService | None = None,
        temporal_service: TemporalGraphService | None = None,
    ):
        self.session = session
        self.repository = PixRepository(session)
        self.engine = DecisionEngine(policy)
        self.graph_service = graph_service or GraphRiskService(mode="off")
        self.entity_service = entity_service or EntityRiskService(mode="off")
        self.temporal_service = temporal_service or TemporalGraphService(mode="off")

    def analyze(self, transaction: PixTransactionCreate) -> PixAnalysisDTO:
        started = perf_counter_ns()
        payload = transaction.model_dump(mode="json")
        payload_hash = fingerprint(payload)
        document = transaction.source_account.owner.document_number
        self.repository.lock(transaction.id, document, transaction.source.device_id)
        existing = self.repository.get(transaction.id)
        if existing:
            if existing.payload_hash != payload_hash:
                raise TransactionConflict()
            result = PixAnalysisDTO.from_model(existing)
            self.session.commit()
            return result
        destination = payload["destination_account"].copy()
        destination.pop("opening_date")
        destination_identity = fingerprint(destination)
        source_account = payload["source_account"].copy()
        source_account.pop("opening_date")
        account_identity = fingerprint(source_account)
        # Capture server time after serialization locks. Caller event timestamps
        # cannot rewind the accumulation window or erase earlier attempts.
        received_at = datetime.now(timezone.utc)
        history = self.repository.history(
            transaction, destination_identity, self.engine.policy, account_identity, received_at=received_at
        )
        status, baseline = self.engine.evaluate(transaction, history)
        graph_history, truncated = [], False
        if self.graph_service.enabled:
            graph_history, truncated = self.repository.graph_history(
                transaction, destination_identity, MAX_HISTORY, HISTORY_DAYS
            )
        graph_result = self.graph_service.assess(payload, graph_history, truncated)
        status, metadata = combine_graph_risk(status, baseline, graph_result)
        untrust_policy = self.engine.policy.untrust
        untrust_history = (
            self.repository.untrust_history(
                account_identity,
                received_at,
                untrust_policy.window_hours,
            )
            if untrust_policy.enabled
            else UntrustHistory()
        )
        status, untrust, notification = assess_untrust(
            status,
            baseline,
            untrust_history,
            untrust_policy,
            self.engine.policy.scoring.two_factor_threshold,
        )
        metadata["account_untrust"] = untrust
        metadata["bank_notification"] = notification
        if untrust["decision_override"]:
            metadata["decision_source"] = "account_untrust"
        if self.entity_service.enabled:
            payments, payments_incomplete = self.repository.entity_payments(document, received_at)
            documents = self.entity_service.documents(document, received_at, payments)
            evidence, incomplete = self.repository.entity_evidence(
                documents,
                received_at,
                untrust_policy.window_hours,
            )
            entity_assessment = self.entity_service.assess(
                document,
                received_at,
                evidence,
                current_increment=untrust["increment"],
                current_event_id=transaction.id,
                current_account_identity=account_identity,
                own_window_hours=untrust_policy.window_hours,
                own_threshold=untrust_policy.two_factor_threshold if untrust_policy.enabled else 101,
                history_truncated=incomplete,
                payments=payments,
                payments_truncated=payments_incomplete,
            )
            status, metadata = combine_entity_risk(status, metadata, entity_assessment)
        temporal_history = (
            self.repository.temporal_history(transaction, received_at)
            if self.temporal_service.enabled
            else TemporalHistory()
        )
        # Observation only. Run after all decisions; its output cannot feed own
        # increments, change status, consume graph points or relax another control.
        temporal_result = self.temporal_service.assess(payload, received_at, temporal_history)
        metadata["gnn_v2"] = temporal_result
        metadata["policy"]["gnn_v2"] = {
            key: value
            for key, value in temporal_result.items()
            if key
            in {
                "mode",
                "model_version",
                "model_sha256",
                "feature_version",
                "hops",
                "history_days",
                "history_limit",
                "own_evidence_limit",
                "entity_limit",
                "own_window_hours",
                "own_evidence_version",
                "training_evidence_policy",
                "minimum_history",
                "label_target",
            }
        }
        metadata["decision_causes"] = decision_causes(metadata, status)
        # Measure the original analysis before inserting its immutable snapshot.
        metadata["processing_time_ms"] = round((perf_counter_ns() - started) / 1_000_000, 3)
        analysis = self.repository.create(
            analysis_key=str(uuid4()),
            transaction_id=transaction.id,
            payload_hash=payload_hash,
            source_document=document,
            source_account_identity=account_identity,
            destination_identity=destination_identity,
            device_id=transaction.source.device_id,
            amount=transaction.amount,
            transaction_date=transaction.transaction_date,
            payload=payload,
            status=status,
            decision_metadata=metadata,
            created_at=received_at,
        )
        result = PixAnalysisDTO.from_model(analysis)
        self.session.commit()
        return result

    def get_analysis(self, transaction_id: str) -> PixAnalysisDTO:
        analysis = self.repository.get(transaction_id)
        if analysis is None:
            raise AnalysisNotFound()
        return PixAnalysisDTO.from_model(analysis)
