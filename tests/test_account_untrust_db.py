import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.models.pix import PixAnalysis
from src.repositories.pix_repository import PixRepository


@pytest.mark.skipif(
    not os.environ.get("PIX_TEST_DATABASE_URL"), reason="Requires the isolated verification database"
)
def test_untrust_window_expires_at_boundary_excludes_future_and_other_accounts():
    engine = create_engine(os.environ["PIX_TEST_DATABASE_URL"])
    at = datetime.now(timezone.utc)
    account_id, other_id = uuid4().hex * 2, uuid4().hex * 2
    try:
        with Session(engine) as session:
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
                        decision_metadata={"account_untrust": {"increment": 20}},
                        created_at=at - timedelta(hours=hours),
                    )
                )
            session.flush()
            history = PixRepository(session).untrust_history(account_id, at, 24)
            assert history.points == 20
            assert history.events == 1
            session.rollback()  # No test history survives this isolated database test.
    finally:
        engine.dispose()
