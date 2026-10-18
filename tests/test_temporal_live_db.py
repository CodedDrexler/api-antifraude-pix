"""PostgreSQL neighborhood/evidence boundaries, saved decisions and CPF/CNPJ context."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from src.constants import Policy
from src.controllers.pix_controller import PixController, fingerprint
from src.entity_risk import ConfirmedIncident, CorporateLink, EntityRegistry, EntityRiskService
from src.gnn.temporal_service import TemporalGraphService
from src.models.pix import PixAnalysis
from src.repositories.pix_repository import PixRepository
from src.schemas.pix import PixTransactionCreate


def payment(payload, name, sender, receiver, at):
    row = deepcopy(payload)
    row.update(id=name + "-" + uuid4().hex, transaction_date=at.isoformat())
    for side, document in (("source_account", sender), ("destination_account", receiver)):
        row[side].update(participant="12345678", branch="0001", account_number="account-" + document)
        row[side]["owner"]["document_number"] = document
    row["source"]["device_id"] = "device-" + sender
    return row


def save(session, payload, received_at, *, increment=0, version="sender-evidence-v2", raw_payload=None):
    tx = PixTransactionCreate.model_validate(payload)
    normalized = tx.model_dump(mode="json")

    def account(side):
        return fingerprint({k: v for k, v in normalized[side].items() if k != "opening_date"})

    model = PixAnalysis(
        analysis_key=str(uuid4()),
        transaction_id=tx.id,
        payload_hash=fingerprint(normalized),
        source_document=tx.source_account.owner.document_number,
        source_account_identity=account("source_account"),
        destination_identity=account("destination_account"),
        device_id=tx.source.device_id,
        amount=tx.amount,
        transaction_date=tx.transaction_date,
        payload=normalized if raw_payload is None else raw_payload,
        status="two_factor_required" if increment else "approved",
        decision_metadata={"account_untrust": {"increment": increment, "evidence_version": version}},
        created_at=received_at,
    )
    session.add(model)
    session.flush()
    return model


def docs_for(payload, count=5):
    base = int(payload["source_account"]["owner"]["document_number"])
    return [f"{(base + index) % 10**11:011d}" for index in range(count)]


def test_query_finds_incoming_two_hops_and_own_evidence_beyond_payment_neighborhood(database_engine, payload):
    at = datetime.now(timezone.utc)
    root, receiver, contact, upstream, unrelated = docs_for(payload)
    candidate = payment(payload, "candidate", root, receiver, at)
    with Session(database_engine) as session:
        incoming = save(
            session,
            payment(payload, "incoming", contact, root, at - timedelta(hours=1)),
            at - timedelta(minutes=5),
        )
        second = save(
            session,
            payment(payload, "upstream", upstream, contact, at - timedelta(hours=2)),
            at - timedelta(minutes=10),
        )
        own = save(
            session,
            payment(payload, "own-future-clock", upstream, unrelated, at + timedelta(days=1)),
            at - timedelta(minutes=4),
            increment=20,
        )
        outside = save(
            session,
            payment(payload, "outside", unrelated, unrelated, at - timedelta(hours=1)),
            at - timedelta(minutes=3),
        )
        snapshot = PixRepository(session).temporal_history(PixTransactionCreate.model_validate(candidate), at)
        assert snapshot.abstention is None
        assert {row.payload["id"] for row in snapshot.events} == {
            incoming.transaction_id,
            second.transaction_id,
        }
        assert [row.payload["id"] for row in snapshot.own_events] == [own.transaction_id]
        assert outside.transaction_id not in {row.payload["id"] for row in snapshot.events}
        session.rollback()


def test_own_history_uses_received_window_and_rejects_legacy_evidence(database_engine, payload):
    at = datetime.now(timezone.utc)
    root, receiver, *_ = docs_for(payload)
    candidate = payment(payload, "candidate", root, receiver, at - timedelta(days=2))
    with Session(database_engine) as session:
        active = save(
            session,
            payment(payload, "active", root, receiver, at + timedelta(days=1)),
            at - timedelta(hours=1),
            increment=20,
        )
        for name, received, version in [
            ("at-cutoff", at - timedelta(hours=24), "sender-evidence-v2"),
            ("future-received", at + timedelta(microseconds=1), "sender-evidence-v2"),
            ("legacy", at - timedelta(hours=1), "legacy-v7"),
        ]:
            save(session, payment(payload, name, root, receiver, at), received, increment=20, version=version)
        snapshot = PixRepository(session).temporal_history(PixTransactionCreate.model_validate(candidate), at)
        assert snapshot.events == []
        assert [row.payload["id"] for row in snapshot.own_events] == [active.transaction_id]
        session.rollback()


@pytest.mark.parametrize(
    "reason,count,old_event",
    [
        ("history_truncated", 301, False),
        ("neighborhood_truncated", 100, False),
        ("own_evidence_truncated", 301, True),
    ],
)
def test_bounded_queries_report_incomplete_history_instead_of_scoring_a_sample(
    database_engine, payload, reason, count, old_event
):
    at = datetime.now(timezone.utc)
    root, receiver, *_ = docs_for(payload)
    candidate = payment(payload, "candidate", root, receiver, at)
    with Session(database_engine) as session:
        for index in range(count):
            target = (
                receiver
                if reason != "neighborhood_truncated"
                else f"{(int(root) + index + 10) % 10**11:011d}"
            )
            save(
                session,
                payment(
                    payload,
                    f"history-{index}",
                    root,
                    target,
                    at - timedelta(days=31) if old_event else at - timedelta(hours=1),
                ),
                at - timedelta(minutes=1),
                increment=20 if old_event else 0,
            )
        snapshot = PixRepository(session).temporal_history(PixTransactionCreate.model_validate(candidate), at)
        assert snapshot.abstention == reason
        result = TemporalGraphService().assess(candidate, at, snapshot)
        assert result["gnn_score"] is None and result["status"] == reason
        session.rollback()


def test_legacy_payload_cannot_break_optional_v2_observation(database_engine, payload):
    at = datetime.now(timezone.utc)
    root, receiver, *_ = docs_for(payload)
    candidate = payment(payload, "candidate", root, receiver, at)
    with Session(database_engine) as session:
        save(
            session,
            payment(payload, "legacy-payload", root, receiver, at - timedelta(hours=1)),
            at - timedelta(minutes=1),
            raw_payload={},
        )
        assert (
            PixRepository(session)
            .temporal_history(PixTransactionCreate.model_validate(candidate), at)
            .abstention
            == "invalid_history"
        )
        session.rollback()


@pytest.mark.parametrize(
    "role,exposure,action", [("controller", 95, "two_factor_required"), ("accountant", 0, "none")]
)
@pytest.mark.parametrize("entity_mode", ["shadow", "contribute"])
def test_clean_cpf_corporate_exposure_is_separate_from_v2_and_preserved_on_replay(
    database_engine, payload, role, exposure, action, entity_mode
):
    at = datetime.now(timezone.utc)
    root, receiver, *_ = docs_for(payload)
    payload = payment(payload, "candidate", root, receiver, at)
    companies = ("12345678000199", "23456789000199")
    registry = EntityRegistry(
        version="trusted-synthetic",
        links=tuple(
            CorporateLink(
                link_id=f"link-{index}",
                person_or_company=root,
                company=company,
                role=role,
                verified=True,
                valid_from=at - timedelta(days=90),
                known_at=at - timedelta(days=80),
                reference="verified-test-registry",
            )
            for index, company in enumerate(companies)
        ),
        incidents=tuple(
            ConfirmedIncident(
                incident_id=f"incident-{index}",
                documents=(company,),
                severity=90,
                occurred_at=at - timedelta(days=2),
                known_at=at - timedelta(days=1),
                reference="confirmed-test-incident",
            )
            for index, company in enumerate(companies)
        ),
    )
    with Session(database_engine) as session:
        for hours in (4, 3, 2):
            save(
                session,
                payment(payload, "normal", root, receiver, at - timedelta(hours=hours)),
                at - timedelta(minutes=hours),
            )
        controller = PixController(
            session,
            Policy(),
            entity_service=EntityRiskService(entity_mode, registry=registry),
            temporal_service=TemporalGraphService(),
        )
        result = controller.analyze(PixTransactionCreate.model_validate(payload))
        expected = (
            "two_factor_required" if role == "controller" and entity_mode == "contribute" else "approved"
        )
        assert result.status == expected
        assert result.metadata["account_untrust"]["score"] == 0
        entity = result.metadata["entity_risk"]
        assert entity["own_entity"]["score"] == 0
        assert entity["relationships"]["exposure_score"] == exposure
        assert entity["proposed_action"] == action
        assert result.metadata["gnn_v2"]["status"] == "scored"
        assert result.metadata["gnn_v2"]["applied_points"] == 0
        # A registry or mode change must not rewrite the original saved decision.
        assert (
            PixController(session, Policy()).analyze(PixTransactionCreate.model_validate(payload)) == result
        )
        assert controller.get_analysis(payload["id"]) == result
