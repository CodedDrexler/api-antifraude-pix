from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from src.constants import Policy
from src.controllers.account_untrust import OWN_EVIDENCE_VERSION, assess_untrust
from src.controllers.decision_engine import DecisionEngine
from src.models.pix import PixAnalysis
from src.repositories.pix_repository import PixRepository
from src.risk.types import History
from src.schemas.pix import PixTransactionCreate


def test_untrust_window_expiry_removes_restriction_and_excludes_future_and_other_accounts(
    database_engine, payload
):
    at = datetime.now(timezone.utc)
    account_id, other_id = uuid4().hex * 2, uuid4().hex * 2
    policy = Policy()
    status, baseline = DecisionEngine(policy).evaluate(
        PixTransactionCreate.model_validate(payload), History(0, 0, 1, True, True, 1, 1000)
    )
    assert status == "approved"
    with Session(database_engine) as session:
        for hours, account in [(23.99, account_id), (24, account_id), (-1, account_id), (1, other_id)]:
            session.add(
                PixAnalysis(
                    analysis_key=str(uuid4()),
                    transaction_id="window-" + uuid4().hex,
                    payload_hash="0" * 64,
                    source_document="11122233344",
                    source_account_identity=account,
                    destination_identity="0" * 64,
                    device_id="window-device",
                    amount=1,
                    transaction_date=at,
                    payload={},
                    status="two_factor_required",
                    decision_metadata={
                        "account_untrust": {"increment": 40, "evidence_version": OWN_EVIDENCE_VERSION}
                    },
                    created_at=at - timedelta(hours=hours),
                )
            )
        session.flush()
        history = PixRepository(session).untrust_history(account_id, at, 24)
        assert history.points == 40
        assert history.events == 1
        result, untrust, _ = assess_untrust(status, baseline, history, policy.untrust)
        assert result == "two_factor_required"
        assert untrust["increment"] == 0
        expired = PixRepository(session).untrust_history(account_id, at + timedelta(minutes=1), 24)
        assert expired.points == expired.events == 0
        assert assess_untrust(status, baseline, expired, policy.untrust)[0] == "approved"
        session.rollback()  # No test history survives this isolated database test.
