from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def build_database(database_url: str):
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=5,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=5000 -c lock_timeout=4000",
        },
    )
    return engine, sessionmaker(engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    # The controller owns commit. Every other exit rolls back before closing.
    with request.app.state.session_factory() as session:
        try:
            yield session
        finally:
            session.rollback()
