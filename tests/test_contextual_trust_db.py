"""Real PostgreSQL: receipt-time references, immutable snapshots and legacy isolation."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from conftest import post, request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants import Policy
from src.controllers.account_untrust import OWN_EVIDENCE_VERSION
from src.controllers.pix_controller import PixController, fingerprint
from src.models.pix import PixAnalysis
from src.repositories.pix_repository import PixRepository
from src.schemas.pix import PixTransactionCreate


def identity(account):
    return fingerprint({key: value for key, value in account.items() if key != "opening_date"})


def save(session, payload, event_at, received_at, amount=10_000, status="approved", metadata=None):
    value = deepcopy(payload)
    value.update(id="context-" + uuid4().hex, transaction_date=event_at.isoformat(), amount=amount)
    tx = PixTransactionCreate.model_validate(value)
    normalized = tx.model_dump(mode="json")
    row = PixAnalysis(
        analysis_key=str(uuid4()),
        transaction_id=tx.id,
        payload_hash=fingerprint(normalized),
        source_document=tx.source_account.owner.document_number,
        source_account_identity=identity(normalized["source_account"]),
        destination_identity=identity(normalized["destination_account"]),
        device_id=tx.source.device_id,
        amount=amount,
        transaction_date=event_at,
        created_at=received_at,
        payload=normalized,
        status=status,
        decision_metadata=metadata or {},
    )
    session.add(row)
    session.flush()
    return row


def references(session, payload, at):
    tx = PixTransactionCreate.model_validate(payload)
    normalized = tx.model_dump(mode="json")
    return PixRepository(session).history(
        tx,
        identity(normalized["destination_account"]),
        Policy(),
        identity(normalized["source_account"]),
        received_at=at,
    )


def test_reference_eligibility_respects_status_receipt_time_event_time_and_critical_signals(
    database_engine, payload
):
    at = datetime.fromisoformat(payload["transaction_date"])
    with Session(database_engine) as session:
        save(session, payload, at - timedelta(days=1), at - timedelta(days=1), amount=101)
        save(session, payload, at - timedelta(days=2), at - timedelta(days=2), amount=102)
        for status in ("two_factor_required", "rejected"):
            save(session, payload, at - timedelta(days=1), at - timedelta(days=1), status=status)
        save(session, payload, at - timedelta(days=1), at + timedelta(seconds=1))
        save(session, payload, at + timedelta(seconds=1), at - timedelta(days=1))
        save(session, payload, at - timedelta(days=31), at - timedelta(days=1))
        save(
            session,
            payload,
            at - timedelta(days=1),
            at - timedelta(days=1),
            metadata={"hard_limits": ["velocity_above_limit"]},
        )
        history = references(session, payload, at)
        assert sorted(history.payer_reference_values) == [101, 102]
        assert sorted(history.relationship_reference_values) == [101, 102]
        assert history.relationship_received_days == 2
        # Rejected/pending attempts remain in raw history, independently of reference eligibility.
        assert history.registered_count == 6
        session.rollback()


def test_backdated_requests_received_on_one_day_cannot_manufacture_trust(database_engine, payload):
    at = datetime.fromisoformat(payload["transaction_date"])
    with Session(database_engine) as session:
        for index in range(5):
            save(session, payload, at - timedelta(days=index + 1), at - timedelta(minutes=index + 1))
        history = references(session, payload, at)
        assert history.relationship_received_days == 1
        assert len(history.payer_reference_values) == 5
        session.rollback()


def test_legacy_increments_remain_auditable_but_cannot_propagate_as_own_risk(database_engine, payload):
    at = datetime.now(timezone.utc)
    tx_at = datetime.fromisoformat(payload["transaction_date"])
    with Session(database_engine) as session:
        legacy = save(
            session,
            payload,
            tx_at,
            at - timedelta(hours=1),
            status="rejected",
            metadata={"account_untrust": {"increment": 25}},
        )
        save(
            session,
            payload,
            tx_at,
            at - timedelta(minutes=1),
            status="two_factor_required",
            metadata={"account_untrust": {"increment": 20, "evidence_version": OWN_EVIDENCE_VERSION}},
        )
        repository = PixRepository(session)
        history = repository.untrust_history(legacy.source_account_identity, at, 24)
        assert history.points == 20 and history.events == 1
        own, incomplete = repository.entity_evidence([legacy.source_document], at)
        assert not incomplete and sum(row.increment for row in own) == 20
        assert repository.get(legacy.transaction_id).decision_metadata["account_untrust"]["increment"] == 25
        session.rollback()


def test_contextual_decision_is_persisted_and_retry_and_get_preserve_it(
    database_engine, payload, monkeypatch
):
    at = datetime.fromisoformat(payload["transaction_date"])

    class Clock:
        @staticmethod
        def now(tz):
            return at.astimezone(tz)

    monkeypatch.setattr("src.controllers.pix_controller.datetime", Clock)
    payload["amount"] = 200_000
    with Session(database_engine) as session:
        # Three larger relationship observations precede seventeen smaller payments elsewhere.
        for days in (6, 5, 4):
            save(session, payload, at - timedelta(days=days), at - timedelta(days=days), amount=200_000)
        other = deepcopy(payload)
        other["destination_account"]["account_number"] += "-other"
        for hours in range(20, 37):
            save(session, other, at - timedelta(hours=hours), at - timedelta(hours=hours))
        controller = PixController(session, Policy())
        tx = PixTransactionCreate.model_validate(payload)
        result = controller.analyze(tx)
        assert result.status == "approved"
        assert result.metadata["contextual_trust"]["applied"] is True
        assert result.metadata["account_untrust"]["increment"] == 0
        original_policy = result.metadata["policy"]["version"]
        controller.engine.policy = Policy(version="different-policy")
        assert controller.get_analysis(tx.id) == result
        assert controller.analyze(tx) == result
        assert controller.get_analysis(tx.id).metadata["policy"]["version"] == original_policy
        assert session.scalar(select(func.count()).where(PixAnalysis.transaction_id == tx.id)) == 1


def test_destination_attempts_remain_in_history_without_tainting_normal_next_payment(
    database_engine, payload, monkeypatch
):
    at = datetime.fromisoformat(payload["transaction_date"])

    class Clock:
        current = at

        @classmethod
        def now(cls, tz):
            return cls.current.astimezone(tz)

    monkeypatch.setattr("src.controllers.pix_controller.datetime", Clock)
    payload["source_account"]["opening_date"] = (at - timedelta(days=4)).isoformat()
    payload["source"]["channel"] = "internet_banking"
    with Session(database_engine) as session:
        for days in (3, 2, 1):
            save(session, payload, at - timedelta(days=days), at - timedelta(days=days), amount=20_000)
        controller = PixController(session, Policy())
        for index in range(6):
            attempt = deepcopy(payload)
            attempt.update(id="destination-" + uuid4().hex, amount=50_000)
            attempt["destination_account"]["account_number"] += f"-new-{index}"
            attempt["destination_account"]["opening_date"] = attempt["transaction_date"]
            result = controller.analyze(PixTransactionCreate.model_validate(attempt))
            assert result.status == "two_factor_required"
            assert result.metadata["account_untrust"]["increment"] == 0
            assert result.metadata["account_untrust"]["score"] == 0
            # Advance server/event clocks beyond the independent velocity and duplicate windows.
            Clock.current += timedelta(minutes=11)
            payload["transaction_date"] = Clock.current.isoformat()
        payload.update(id="normal-" + uuid4().hex, amount=20_000)
        clean = controller.analyze(PixTransactionCreate.model_validate(payload))
        assert clean.status == "approved"
        assert clean.metadata["account_untrust"]["score"] == 0
        assert clean.metadata["registered_transactions"] == 9
        assert controller.get_analysis(payload["id"]) == clean


def test_post_get_and_retry_preserve_contextual_response_without_duplicating_history(
    database_engine, api, payload
):
    at = datetime.fromisoformat(payload["transaction_date"])
    payload["amount"] = 200_000
    with Session(database_engine) as session:
        for days in (6, 5, 4):
            save(session, payload, at - timedelta(days=days), at - timedelta(days=days), amount=200_000)
        other = deepcopy(payload)
        other["destination_account"]["account_number"] += "-other"
        for hours in range(20, 37):
            save(session, other, at - timedelta(hours=hours), at - timedelta(hours=hours))
        session.commit()
    response = post(api, payload)
    assert response["status"] == "approved"
    assert response["metadata"]["contextual_trust"]["applied"] is True
    assert response["metadata"]["contextual_trust"]["profile_points_before"] == 80
    assert response["metadata"]["decision_causes"] == []
    assert post(api, payload) == response
    assert api("GET", "/pix/transaction/" + payload["id"])[1] == response
    compact = request("GET", "/pix/transaction/" + payload["id"])[1]
    assert compact["metadata"]["contextual_trust"] == {
        "applied": True,
        "reason": "compatible_relationship",
        "profile_points_before": 80,
        "profile_points_after": 0,
    }
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).where(PixAnalysis.transaction_id == payload["id"])) == 1
