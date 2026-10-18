from datetime import timedelta
from hashlib import sha256

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from src.constants import Policy
from src.controllers.account_untrust import UntrustHistory
from src.models.pix import PixAnalysis
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
        self, transaction: PixTransactionCreate, destination: str, policy: Policy, source_account: str
    ) -> History:
        at = transaction.transaction_date
        payer = PixAnalysis.source_document == transaction.source_account.owner.document_number
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
        # Rejected/pending attempts must not raise an established amount baseline.
        # Until the first approval, one initial pending request bootstraps the demo.
        amounts = self.session.scalars(
            select(PixAnalysis.amount)
            .where(payer, PixAnalysis.status == "approved", PixAnalysis.transaction_date <= at)
            .order_by(PixAnalysis.transaction_date.desc(), PixAnalysis.id.desc())
            .limit(policy.profile_history_size)
        ).all()
        profile_basis = "approved" if amounts else "unavailable"
        if not amounts:
            bootstrap = self.session.scalar(
                select(PixAnalysis.amount)
                .where(payer, PixAnalysis.status == "two_factor_required", PixAnalysis.transaction_date <= at)
                .order_by(PixAnalysis.transaction_date, PixAnalysis.id)
                .limit(1)
            )
            if bootstrap is not None:
                amounts = [bootstrap]
                profile_basis = "initial_pending_attempt"
        device_window = (
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
                PixAnalysis.created_at > at - timedelta(hours=hours),
                PixAnalysis.created_at <= at,
            )
        ).one()
        return UntrustHistory(int(points), events)

    def graph_history(self, transaction, destination, limit=300, days=30):
        at = transaction.transaction_date
        related = or_(
            PixAnalysis.source_document == transaction.source_account.owner.document_number,
            PixAnalysis.destination_identity == destination,
            PixAnalysis.device_id == transaction.source.device_id,
        )
        rows = self.session.scalars(
            select(PixAnalysis.payload)
            .where(
                related,
                PixAnalysis.transaction_date >= at - timedelta(days=days),
                PixAnalysis.transaction_date <= at,
            )
            .order_by(PixAnalysis.transaction_date.desc(), PixAnalysis.id.desc())
            .limit(limit + 1)
        ).all()
        # Refuse an incomplete graph instead of treating a truncated neighborhood as complete.
        return list(rows[:limit]), len(rows) > limit
