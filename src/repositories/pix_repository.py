from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from src.constants import Policy
from src.models.pix import PixAnalysis
from src.schemas.pix import PixTransactionCreate


@dataclass(frozen=True)
class History:
    recent_count: int
    recent_amount: int
    approved_count: int
    approved_amount: int
    known_destination: bool
    known_device: bool


class PixRepository:
    def __init__(self, session: Session):
        self.session = session

    def lock(self, transaction_id: str, document: str):
        # Stable across processes. Ordering prevents cycles between lock keys.
        keys = {
            int.from_bytes(sha256(value.encode()).digest()[:8], "big", signed=True)
            for value in ("transaction:" + transaction_id, "payer:" + document)
        }
        for key in sorted(keys):
            self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    def get(self, transaction_id: str) -> PixAnalysis | None:
        return self.session.scalar(select(PixAnalysis).where(PixAnalysis.transaction_id == transaction_id))

    def history(self, transaction: PixTransactionCreate, destination: str, policy: Policy) -> History:
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
        profile_count, profile_amount = self.session.execute(
            select(func.count(), func.coalesce(func.sum(PixAnalysis.amount), 0)).where(*approved)
        ).one()
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
        return History(
            count, int(amount), profile_count, int(profile_amount), known_destination, known_device
        )

    def create(self, **values) -> PixAnalysis:
        analysis = PixAnalysis(**values)
        self.session.add(analysis)
        self.session.flush()
        return analysis

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
