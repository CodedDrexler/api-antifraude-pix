import json
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

from sqlalchemy.orm import Session

from src.constants import Policy
from src.controllers.decision_engine import DecisionEngine
from src.dtos.pix_dto import PixAnalysisDTO
from src.errors.pix_errors import AnalysisNotFound, TransactionConflict
from src.gnn.service import HISTORY_DAYS, MAX_HISTORY, GraphRiskService, combine_graph_risk
from src.repositories.pix_repository import PixRepository
from src.schemas.pix import PixTransactionCreate


def fingerprint(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PixController:
    def __init__(self, session: Session, policy: Policy, graph_service: GraphRiskService | None = None):
        self.session = session
        self.repository = PixRepository(session)
        self.engine = DecisionEngine(policy)
        self.graph_service = graph_service or GraphRiskService(mode="off")

    def analyze(self, transaction: PixTransactionCreate) -> PixAnalysisDTO:
        payload = transaction.model_dump(mode="json")
        payload_hash = fingerprint(payload)
        document = transaction.source_account.owner.document_number
        self.repository.lock(transaction.id, document)
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
        history = self.repository.history(transaction, destination_identity, self.engine.policy)
        status, metadata = self.engine.evaluate(transaction, history)
        graph_history, truncated = [], False
        if self.graph_service.enabled:
            graph_history, truncated = self.repository.graph_history(
                transaction, destination_identity, MAX_HISTORY, HISTORY_DAYS
            )
        graph_result = self.graph_service.assess(payload, graph_history, truncated)
        status, metadata = combine_graph_risk(status, metadata, graph_result)
        analysis = self.repository.create(
            analysis_key=str(uuid4()),
            transaction_id=transaction.id,
            payload_hash=payload_hash,
            source_document=document,
            destination_identity=destination_identity,
            device_id=transaction.source.device_id,
            amount=transaction.amount,
            transaction_date=transaction.transaction_date,
            payload=payload,
            status=status,
            decision_metadata=metadata,
            created_at=datetime.now(timezone.utc),
        )
        result = PixAnalysisDTO.from_model(analysis)
        self.session.commit()
        return result

    def get_analysis(self, transaction_id: str) -> PixAnalysisDTO:
        analysis = self.repository.get(transaction_id)
        if analysis is None:
            raise AnalysisNotFound()
        return PixAnalysisDTO.from_model(analysis)
