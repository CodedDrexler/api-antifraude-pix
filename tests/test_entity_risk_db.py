"""PostgreSQL and saved API evidence for independent entity histories."""

import copy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from src.constants import Policy
from src.controllers.account_untrust import UntrustHistory, assess_untrust
from src.controllers.decision_engine import DecisionEngine
from src.controllers.pix_controller import PixController, fingerprint
from src.entity_risk import ConfirmedIncident, CorporateLink, EntityRegistry, EntityRiskService
from src.models.pix import PixAnalysis
from src.repositories.pix_repository import PixRepository
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate


def seed_independent_evidence(session, payload, account_number, at):
    row = copy.deepcopy(payload)
    row.update(id="own-evidence-" + uuid4().hex, amount=100_000, transaction_date=at.isoformat())
    row["source_account"]["account_number"] = account_number
    tx = PixTransactionCreate.model_validate(row)
    normalized = tx.model_dump(mode="json")
    status, metadata = DecisionEngine(Policy()).evaluate(tx, History(0, 0, 3, True, True, 3, 30_000))
    status, untrust, _ = assess_untrust(status, metadata, UntrustHistory(), Policy().untrust)
    assert untrust["increment"] == 20  # Derived from the actual profile rule, not fabricated risk.
    metadata["account_untrust"] = untrust
    metadata["entity_risk"] = {"relationships": {"exposure_score": 100}}  # Must never become evidence.
    analysis = PixAnalysis(
        analysis_key=str(uuid4()),
        transaction_id=tx.id,
        payload_hash=fingerprint(normalized),
        source_document=tx.source_account.owner.document_number,
        source_account_identity=fingerprint(
            {k: v for k, v in normalized["source_account"].items() if k != "opening_date"}
        ),
        destination_identity=fingerprint(
            {k: v for k, v in normalized["destination_account"].items() if k != "opening_date"}
        ),
        device_id=tx.source.device_id,
        amount=tx.amount,
        transaction_date=tx.transaction_date,
        payload=normalized,
        status=status,
        decision_metadata=metadata,
        created_at=at,
    )
    session.add(analysis)
    session.flush()
    return analysis


def test_postgres_document_history_spans_accounts_expires_and_ignores_relational_score(
    database_engine, payload
):
    at = datetime.now(timezone.utc)
    doc = payload["source_account"]["owner"]["document_number"]
    with Session(database_engine) as session:
        seed_independent_evidence(session, payload, "account-a", at - timedelta(hours=2))
        seed_independent_evidence(session, payload, "account-b", at - timedelta(hours=1))
        seed_independent_evidence(session, payload, "expired", at - timedelta(hours=24))
        seed_independent_evidence(session, payload, "future", at + timedelta(hours=1))
        repo = PixRepository(session)
        evidence, incomplete = repo.entity_evidence([doc], at)
        assert not incomplete and len(evidence) == 2
        result = EntityRiskService("contribute").assess(doc, at, evidence)
        assert result["own_entity"]["score"] == 40
        assert result["own_entity"]["accounts_with_evidence"] == 2
        assert result["relationships"]["exposure_score"] == 0
        limited, incomplete = repo.entity_evidence([doc], at, limit=1)
        assert incomplete and len(limited) == 1
        session.rollback()


def test_controller_new_account_preserves_own_titular_risk_and_saved_decision(database_engine, payload):
    at = datetime.now(timezone.utc)
    doc = payload["source_account"]["owner"]["document_number"]
    with Session(database_engine) as session:
        seed_independent_evidence(session, payload, "account-a", at - timedelta(hours=2))
        seed_independent_evidence(session, payload, "account-b", at - timedelta(hours=1))
        payload["transaction_date"] = at.isoformat()
        payload["source_account"]["account_number"] = "new-account"
        controller = PixController(session, Policy(), entity_service=EntityRiskService("contribute"))
        result = controller.analyze(PixTransactionCreate.model_validate(payload))
        assert result.status == "two_factor_required"
        assert result.metadata["decision_source"] == "entity_risk"
        assert result.metadata["account_untrust"]["score"] == 0
        assert result.metadata["account_untrust"]["increment"] == 0
        assert result.metadata["entity_risk"]["own_entity"]["score"] == 40
        assert result.metadata["risk_score"] == 0
        # A replay cannot change when the registry/mode changes.
        replay = PixController(session, Policy(), entity_service=EntityRiskService("off"))
        assert replay.analyze(PixTransactionCreate.model_validate(payload)) == result
    with Session(database_engine) as session:
        saved = PixRepository(session).get(payload["id"])
        assert saved.decision_metadata["entity_risk"] == result.metadata["entity_risk"]
        # The new relationship action added no own-account increment.
        evidence, _ = PixRepository(session).entity_evidence([doc], datetime.now(timezone.utc))
        assert sum(event.increment for event in evidence) == 40


def test_postgres_payment_query_includes_receipts_and_bounds_history(database_engine, payload):
    at = datetime.now(timezone.utc)
    doc = payload["destination_account"]["owner"]["document_number"]
    # Give the recipient a fresh identity to keep this test independent of other fixtures.
    doc = f"{uuid4().int % 10**11:011d}"
    payload["destination_account"]["owner"]["document_number"] = doc
    with Session(database_engine) as session:
        seed_independent_evidence(session, payload, "incoming-a", at - timedelta(hours=2))
        seed_independent_evidence(session, payload, "incoming-b", at - timedelta(hours=1))
        rows, incomplete = PixRepository(session).entity_payments(doc, at)
        assert not incomplete and len(rows) == 2
        assert all(row.destination_document == doc and row.source_document != doc for row in rows)
        _, incomplete = PixRepository(session).entity_payments(doc, at, limit=1)
        assert incomplete
        session.rollback()


def test_confirmed_corporate_exposure_reaches_saved_controller_result(database_engine, payload):
    at = datetime.now(timezone.utc)
    doc = payload["source_account"]["owner"]["document_number"]
    links, incidents = [], []
    for index in range(10):
        company = f"{10_000_000 + index:08d}000199"
        links.append(
            CorporateLink(
                link_id=f"link-{index}",
                person_or_company=doc,
                company=company,
                role="controller",
                verified=True,
                valid_from=at - timedelta(days=90),
                known_at=at - timedelta(days=80),
                reference="synthetic-control",
            )
        )
        incidents.append(
            ConfirmedIncident(
                incident_id=f"fraud-{index}",
                documents=(company,),
                severity=90,
                occurred_at=at - timedelta(days=2),
                known_at=at - timedelta(days=1),
                reference="synthetic-fraud",
            )
        )
    registry = EntityRegistry(version="test-ten-companies", links=tuple(links), incidents=tuple(incidents))
    with Session(database_engine) as session:
        # Establish normal payer history without any entity evidence.
        plain = PixController(session, Policy())
        for hours in (3, 2):
            previous = copy.deepcopy(payload)
            previous.update(
                id="bootstrap-" + uuid4().hex, transaction_date=(at - timedelta(hours=hours)).isoformat()
            )
            plain.analyze(PixTransactionCreate.model_validate(previous))
        payload["transaction_date"] = at.isoformat()
        controller = PixController(
            session, Policy(), entity_service=EntityRiskService("contribute", registry=registry)
        )
        result = controller.analyze(PixTransactionCreate.model_validate(payload))
        assert result.status == "two_factor_required"
        assert result.metadata["decision_source"] == "entity_risk"
        assert result.metadata["account_untrust"]["score"] == 0
        assert result.metadata["entity_risk"]["own_entity"]["score"] == 0
        assert result.metadata["entity_risk"]["relationships"]["strong_confirmed_incidents"] == 10
        assert result.metadata["risk_score"] == 20
        assert result.metadata["entity_risk"]["registry_sha256"]
