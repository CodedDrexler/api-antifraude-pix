from datetime import datetime, timedelta, timezone
from hashlib import sha256

from sqlalchemy import and_, case, cast, func, or_, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from src.constants import Policy
from src.controllers.account_untrust import OWN_EVIDENCE_VERSION, UntrustHistory
from src.entity_risk import OwnEvidence
from src.financial_features import PaymentEvidence
from src.gnn.temporal_graph import GraphEvent
from src.gnn.temporal_service import (
    MAX_GRAPH_ENTITIES,
    MAX_OWN_EVIDENCE,
    MAX_TEMPORAL_HISTORY,
    TEMPORAL_HOPS,
    TemporalHistory,
)
from src.models.pix import PixAnalysis
from src.risk.contextual_trust import reference_fields
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate


class PixRepository:
    def __init__(self, session: Session):
        self.session = session

    def lock(self, transaction_id: str, document: str, device_id: str):
        # Stable across processes. Ordering prevents cycles between lock keys.
        keys = {
            int.from_bytes(sha256(value.encode()).digest()[:8], "big", signed=True)
            for value in ("transaction:" + transaction_id, "payer:" + document, "device:" + device_id)
        }
        for key in sorted(keys):
            self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    def get(self, transaction_id: str) -> PixAnalysis | None:
        return self.session.scalar(select(PixAnalysis).where(PixAnalysis.transaction_id == transaction_id))

    def history(
        self,
        transaction: PixTransactionCreate,
        destination: str,
        policy: Policy,
        source_account: str,
        *,
        received_at=None,
    ) -> History:
        at = transaction.transaction_date
        received_at = received_at or datetime.now(timezone.utc)
        payer = and_(
            PixAnalysis.source_document == transaction.source_account.owner.document_number,
            PixAnalysis.created_at <= received_at,
        )
        # Future event timestamps never influence an earlier event.
        recent = (
            payer,
            PixAnalysis.transaction_date >= at - timedelta(minutes=policy.velocity_minutes),
            PixAnalysis.transaction_date <= at,
        )
        count, amount = self.session.execute(
            select(func.count(), func.coalesce(func.sum(PixAnalysis.amount), 0)).where(*recent)
        ).one()
        approved = (
            payer,
            PixAnalysis.status == "approved",
            PixAnalysis.transaction_date >= at - timedelta(days=policy.profile_days),
            PixAnalysis.transaction_date <= at,
        )
        local_hour = func.extract("hour", func.timezone("Etc/GMT+3", PixAnalysis.transaction_date))
        night_condition = or_(local_hour >= policy.night_start_hour, local_hour < policy.night_end_hour)
        approved_count, night_count = self.session.execute(
            select(
                func.count(),
                func.count().filter(night_condition),
            ).where(*approved)
        ).one()
        registered_count = self.session.scalar(
            select(func.count()).where(payer, PixAnalysis.transaction_date <= at)
        )
        # Only local approvals form the value reference. A requested 2FA does
        # not prove that authentication or payment was completed.
        amounts = self.session.scalars(
            select(PixAnalysis.amount)
            .where(payer, PixAnalysis.status == "approved", PixAnalysis.transaction_date <= at)
            .order_by(PixAnalysis.transaction_date.desc(), PixAnalysis.id.desc())
            .limit(policy.profile_history_size)
        ).all()
        profile_basis = "approved" if amounts else "unavailable"
        device_window = (
            PixAnalysis.created_at <= received_at,
            PixAnalysis.transaction_date >= at - timedelta(hours=policy.device_window_hours),
            PixAnalysis.transaction_date <= at,
        )
        other_owners = self.session.scalar(
            select(func.count(func.distinct(PixAnalysis.source_document))).where(
                *device_window,
                PixAnalysis.device_id == transaction.source.device_id,
                PixAnalysis.source_document != transaction.source_account.owner.document_number,
            )
        )
        other_devices = self.session.scalar(
            select(func.count(func.distinct(PixAnalysis.device_id))).where(
                *device_window,
                payer,
                PixAnalysis.device_id != transaction.source.device_id,
            )
        )
        known_destination = (
            self.session.scalar(
                select(PixAnalysis.id)
                .where(*approved, PixAnalysis.destination_identity == destination)
                .limit(1)
            )
            is not None
        )
        known_device = (
            self.session.scalar(
                select(PixAnalysis.id)
                .where(*approved, PixAnalysis.device_id == transaction.source.device_id)
                .limit(1)
            )
            is not None
        )
        # Distinct IDs only: replays have already returned in the controller.
        # Rejections do not suggest that a previous payment might have succeeded.
        duplicate = self.session.execute(
            select(PixAnalysis.transaction_id, PixAnalysis.transaction_date)
            .where(
                PixAnalysis.source_account_identity == source_account,
                PixAnalysis.created_at <= received_at,
                PixAnalysis.destination_identity == destination,
                PixAnalysis.amount == transaction.amount,
                PixAnalysis.status.in_(("approved", "two_factor_required")),
                PixAnalysis.transaction_id != transaction.id,
                PixAnalysis.transaction_date >= at - timedelta(seconds=policy.duplicate_window_seconds),
                PixAnalysis.transaction_date <= at,
            )
            .order_by(PixAnalysis.transaction_date.desc(), PixAnalysis.id.desc())
            .limit(1)
        ).first()
        references = {}
        if policy.contextual_trust.enabled:
            eligible = (
                *approved,
                func.coalesce(PixAnalysis.decision_metadata["hard_limits"], cast([], JSONB))
                == cast([], JSONB),
            )

            def samples(*conditions):
                return self.session.execute(
                    select(PixAnalysis.amount, PixAnalysis.created_at)
                    .where(*eligible, *conditions)
                    .order_by(PixAnalysis.created_at.desc(), PixAnalysis.id.desc())
                    .limit(policy.contextual_trust.history_size)
                ).all()

            references = reference_fields(samples(), samples(PixAnalysis.destination_identity == destination))
        return History(
            recent_count=count,
            recent_amount=int(amount),
            approved_count=approved_count,
            known_destination=known_destination,
            known_device=known_device,
            profile_count=len(amounts),
            profile_amount=sum(amounts),
            registered_count=registered_count,
            profile_basis=profile_basis,
            device_other_owners=other_owners,
            payer_other_devices=other_devices,
            approved_night_count=night_count,
            duplicate_transaction_id=duplicate.transaction_id if duplicate else None,
            duplicate_elapsed_seconds=(at - duplicate.transaction_date).total_seconds()
            if duplicate
            else None,
            **references,
        )

    def create(self, **values) -> PixAnalysis:
        analysis = PixAnalysis(**values)
        self.session.add(analysis)
        self.session.flush()
        return analysis

    def untrust_history(self, account_identity, at, hours):
        increment = PixAnalysis.decision_metadata["account_untrust"]["increment"].as_integer()
        points, events = self.session.execute(
            select(func.coalesce(func.sum(increment), 0), func.count().filter(increment > 0)).where(
                PixAnalysis.source_account_identity == account_identity,
                PixAnalysis.decision_metadata["account_untrust"]["evidence_version"].as_string()
                == OWN_EVIDENCE_VERSION,
                PixAnalysis.created_at > at - timedelta(hours=hours),
                PixAnalysis.created_at <= at,
            )
        ).one()
        return UntrustHistory(int(points), events)

    def entity_evidence(self, documents, at, hours=24, limit=2000):
        """Independent own-account increments across accounts, by trusted receipt time.

        Never read propagated entity assessments as new evidence. Explicitly flag
        incomplete history instead of representing missing increments as zero.
        """
        increment = PixAnalysis.decision_metadata["account_untrust"]["increment"].as_integer()
        rows = self.session.execute(
            select(
                PixAnalysis.transaction_id,
                PixAnalysis.source_document,
                PixAnalysis.created_at,
                increment,
                PixAnalysis.source_account_identity,
            )
            .where(
                PixAnalysis.source_document.in_(documents),
                PixAnalysis.decision_metadata["account_untrust"]["evidence_version"].as_string()
                == OWN_EVIDENCE_VERSION,
                increment > 0,
                PixAnalysis.created_at > at - timedelta(hours=hours),
                PixAnalysis.created_at <= at,
            )
            .order_by(PixAnalysis.created_at.desc(), PixAnalysis.id.desc())
            .limit(limit + 1)
        ).all()
        return [OwnEvidence(*row) for row in rows[:limit]], len(rows) > limit

    def entity_payments(self, document, at, limit=300):
        destination_document = PixAnalysis.payload["destination_account"]["owner"][
            "document_number"
        ].as_string()
        rows = self.session.execute(
            select(
                PixAnalysis.transaction_id,
                PixAnalysis.source_document,
                destination_document,
                PixAnalysis.amount,
                PixAnalysis.transaction_date,
                PixAnalysis.created_at,
                PixAnalysis.status,
            )
            .where(
                or_(PixAnalysis.source_document == document, destination_document == document),
                PixAnalysis.created_at > at - timedelta(hours=24),
                PixAnalysis.created_at <= at,
                PixAnalysis.transaction_date > at - timedelta(hours=24),
                PixAnalysis.transaction_date <= at,
            )
            .order_by(PixAnalysis.created_at.desc(), PixAnalysis.id.desc())
            .limit(limit + 1)
        ).all()
        return [PaymentEvidence(*row) for row in rows[:limit]], len(rows) > limit

    def temporal_history(self, transaction, received_at):
        """Two bounded rounds of holder/payment/device context, plus independent evidence.

        Never scan/return an unbounded network or silently score a sampled history.
        Money relations use event time; own increments use trusted receipt time.
        Database failures intentionally propagate through the API's 503 handling.
        """
        at = transaction.transaction_date
        receiver = PixAnalysis.payload["destination_account"]["owner"]["document_number"].as_string()
        increment = case(
            (
                PixAnalysis.decision_metadata["account_untrust"]["evidence_version"].as_string()
                == OWN_EVIDENCE_VERSION,
                func.coalesce(PixAnalysis.decision_metadata["account_untrust"]["increment"].as_integer(), 0),
            ),
            else_=0,
        )
        documents = {
            transaction.source_account.owner.document_number,
            transaction.destination_account.owner.document_number,
        }
        frontier_docs = documents.copy()
        frontier_devices = {transaction.source.device_id}
        events, expanded_docs = {}, set()
        coverage = {
            "hops_completed": 0,
            "entities": len(documents),
            "events": 0,
            "own_evidence_events": 0,
            "selection": "bounded_holder_payment_device_neighborhood",
            "own_evidence_time_basis": "server_received_time",
        }

        def snapshot(reason=None, own=()):
            coverage.update(entities=len(documents), events=len(events), own_evidence_events=len(own))
            return TemporalHistory(list(events.values()), list(own), coverage.copy(), reason)

        def columns():
            return select(PixAnalysis.payload, PixAnalysis.created_at, PixAnalysis.status, increment)

        for depth in range(TEMPORAL_HOPS):
            if not frontier_docs and not frontier_devices:
                break
            rows = self.session.execute(
                columns()
                .where(
                    or_(
                        PixAnalysis.source_document.in_(frontier_docs),
                        receiver.in_(frontier_docs),
                        PixAnalysis.device_id.in_(frontier_devices),
                    ),
                    PixAnalysis.transaction_id != transaction.id,
                    PixAnalysis.transaction_date >= at - timedelta(days=30),
                    PixAnalysis.transaction_date <= at,
                    PixAnalysis.created_at <= received_at,
                )
                .order_by(PixAnalysis.transaction_date.desc(), PixAnalysis.id.desc())
                .limit(MAX_TEMPORAL_HISTORY + 1)
            ).all()
            if len(rows) > MAX_TEMPORAL_HISTORY:
                return snapshot("history_truncated")
            next_docs, next_devices, discovered_docs = set(), set(), set()
            expanded_docs.update(frontier_docs)
            for payload, received, status, points in rows:
                try:
                    event_id = payload["id"]
                    source_doc = payload["source_account"]["owner"]["document_number"]
                    destination_doc = payload["destination_account"]["owner"]["document_number"]
                    device_id = payload["source"]["device_id"]
                except (KeyError, TypeError):
                    return snapshot("invalid_history")
                events[event_id] = GraphEvent(payload, received, status, points)
                discovered_docs.update((source_doc, destination_doc))
                if status != "rejected":
                    next_docs.update((source_doc, destination_doc))
                    next_devices.add(device_id)
            if len(events) > MAX_TEMPORAL_HISTORY:
                return snapshot("history_truncated")
            frontier_docs = next_docs - expanded_docs
            documents.update(discovered_docs)
            frontier_devices = next_devices
            coverage["hops_completed"] = depth + 1
            if len(documents) > MAX_GRAPH_ENTITIES:
                return snapshot("neighborhood_truncated")
        own_rows = self.session.execute(
            columns()
            .where(
                PixAnalysis.source_document.in_(documents),
                PixAnalysis.transaction_id != transaction.id,
                increment > 0,
                PixAnalysis.created_at > received_at - timedelta(hours=24),
                PixAnalysis.created_at <= received_at,
            )
            .order_by(PixAnalysis.created_at.desc(), PixAnalysis.id.desc())
            .limit(MAX_OWN_EVIDENCE + 1)
        ).all()
        if len(own_rows) > MAX_OWN_EVIDENCE:
            return snapshot("own_evidence_truncated")
        own = [GraphEvent(*row) for row in own_rows]
        return snapshot(own=own)
