"""Real PostgreSQL evidence for persistence, history eligibility and append-only data."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from conftest import new_transaction, post, seed_profile
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.constants import Policy
from src.controllers.pix_controller import fingerprint
from src.models.pix import PixAnalysis
from src.repositories.pix_repository import PixRepository
from src.schemas.pix import PixTransactionCreate


def account_identity(account):
    return fingerprint({key: value for key, value in account.items() if key != "opening_date"})


def add_history(session, payload, status, at, *, legacy=False):
    historical_payload = new_transaction(payload, amount=20_000, transaction_date=at.isoformat())
    normalized = PixTransactionCreate.model_validate(historical_payload).model_dump(mode="json")
    analysis = PixAnalysis(
        analysis_key=str(uuid4()),
        transaction_id=normalized["id"],
        payload_hash=fingerprint(normalized),
        source_document=normalized["source_account"]["owner"]["document_number"],
        source_account_identity=None if legacy else account_identity(normalized["source_account"]),
        destination_identity=account_identity(normalized["destination_account"]),
        device_id=normalized["source"]["device_id"],
        amount=normalized["amount"],
        transaction_date=datetime.fromisoformat(normalized["transaction_date"]),
        payload=normalized,
        status=status,
        decision_metadata={"test_fixture": True},
        created_at=datetime.now(timezone.utc),
    )
    session.add(analysis)
    session.flush()
    return analysis


@pytest.mark.parametrize("status", ["approved", "two_factor_required", "rejected"])
def test_history_status_eligibility_is_explicit(database_engine, payload, status):
    at = datetime.fromisoformat(payload["transaction_date"])
    with Session(database_engine) as session:
        previous = add_history(session, payload, status, at - timedelta(minutes=1))
        history = PixRepository(session).history(
            PixTransactionCreate.model_validate(payload),
            previous.destination_identity,
            Policy(),
            previous.source_account_identity,
        )
        assert history.recent_count == 1
        assert history.recent_amount == 20_000
        assert history.registered_count == 1
        assert history.approved_count == int(status == "approved")
        assert history.known_destination is (status == "approved")
        assert history.known_device is (status == "approved")
        assert history.profile_count == int(status != "rejected")
        assert history.profile_amount == (20_000 if status != "rejected" else 0)
        assert (
            history.profile_basis
            == {
                "approved": "approved",
                "two_factor_required": "initial_pending_attempt",
                "rejected": "unavailable",
            }[status]
        )
        session.rollback()


@pytest.mark.parametrize("seconds,known", [(30 * 86400, True), (30 * 86400 + 1, False), (-1, False)])
def test_familiarity_expires_but_amount_profile_has_no_day_cutoff(database_engine, payload, seconds, known):
    at = datetime.fromisoformat(payload["transaction_date"])
    with Session(database_engine) as session:
        previous = add_history(session, payload, "approved", at - timedelta(seconds=seconds))
        history = PixRepository(session).history(
            PixTransactionCreate.model_validate(payload),
            previous.destination_identity,
            Policy(),
            previous.source_account_identity,
        )
        assert history.approved_count == int(known)
        assert history.known_device is known
        assert history.known_destination is known
        assert history.profile_count == int(seconds >= 0)
        assert history.profile_amount == (20_000 if seconds >= 0 else 0)
        session.rollback()


@pytest.mark.parametrize("operation", [update, delete], ids=["update", "delete"])
def test_database_refuses_history_mutation(database_engine, payload, operation):
    with Session(database_engine) as session:
        analysis = add_history(
            session, payload, "approved", datetime.fromisoformat(payload["transaction_date"])
        )
        statement = operation(PixAnalysis).where(PixAnalysis.id == analysis.id)
        if operation is update:
            statement = statement.values(amount=999)
        with pytest.raises(IntegrityError, match="Pix history is immutable"):
            with session.begin_nested():
                session.execute(statement)
        assert session.scalar(select(PixAnalysis.amount).where(PixAnalysis.id == analysis.id)) == 20_000
        session.rollback()


@pytest.mark.parametrize("expected", ["approved", "two_factor_required", "rejected"])
def test_committed_payload_and_evidence_survive_new_connection(database_engine, api, payload, expected):
    if expected == "approved":
        seed_profile(api, payload, 1)
    elif expected == "rejected":
        payload["amount"] = 3_000_000
    decision = post(api, payload)
    assert decision["status"] == expected
    # NullPool opens a new physical connection, outside the API's session/pool.
    with Session(database_engine) as session:
        saved = PixRepository(session).get(payload["id"])
        assert saved is not None
        assert saved.analysis_key == decision["key"]
        assert saved.status == expected
        assert saved.payload == PixTransactionCreate.model_validate(payload).model_dump(mode="json")
        assert saved.payload_hash == fingerprint(saved.payload)
        assert saved.decision_metadata == decision["metadata"]
        assert saved.source_document == saved.payload["source_account"]["owner"]["document_number"]
        assert saved.source_account_identity == account_identity(saved.payload["source_account"])
        assert saved.destination_identity == account_identity(saved.payload["destination_account"])
    assert api("GET", "/pix/transaction/" + payload["id"])[1] == decision
    assert post(api, payload) == decision


def test_receiving_pix_does_not_establish_outgoing_payer_profile(api, payload):
    at = datetime.fromisoformat(payload["transaction_date"])
    inbound = new_transaction(payload, transaction_date=(at - timedelta(hours=1)).isoformat())
    inbound["source_account"]["owner"]["document_number"] = f"{uuid4().int % 10**11:011d}"
    inbound["destination_account"]["owner"] = payload["source_account"]["owner"].copy()
    post(api, inbound)
    decision = post(api, payload)
    assert decision["status"] == "two_factor_required"
    assert decision["metadata"]["registered_transactions"] == 0
    assert decision["metadata"]["profile_basis"] == "unavailable"
    assert decision["metadata"]["reasons"] == ["first_transaction"]


def test_legacy_rows_keep_payer_history_but_do_not_enter_account_controls(database_engine, payload):
    payload["amount"] = 20_000
    at = datetime.fromisoformat(payload["transaction_date"])
    with Session(database_engine) as session:
        previous = add_history(session, payload, "approved", at - timedelta(seconds=1), legacy=True)
        source_identity = account_identity(previous.payload["source_account"])
        history = PixRepository(session).history(
            PixTransactionCreate.model_validate(payload),
            previous.destination_identity,
            Policy(),
            source_identity,
        )
        assert history.registered_count == history.approved_count == history.profile_count == 1
        assert history.known_device is True
        assert history.known_destination is True
        assert history.duplicate_transaction_id is None
        untrust = PixRepository(session).untrust_history(source_identity, datetime.now(timezone.utc), 24)
        assert untrust.points == untrust.events == 0
        session.rollback()
