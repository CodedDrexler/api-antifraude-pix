from fastapi import Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.database import get_session


class HealthCheckResource:
    def on_get_health_check(self):
        return Response(status_code=204)

    def on_get_health(self):
        return {"status": "ok"}

    def on_get_ready(self, session: Session = Depends(get_session)):
        # Checking the table also detects a missing schema, not only a live DB.
        session.execute(text("SELECT id FROM pix_analysis LIMIT 1"))
        return Response(status_code=204)
