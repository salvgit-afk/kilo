"""Fixture condivise dei test.

I test girano su uno SQLite in memoria: non toccano mai il database Neon
reale e non richiedono rete.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
import app.models  # noqa: F401  (registra le tabelle sulla metadata)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://", future=True)

    # SQLite ignora le foreign key se non gli si dice di applicarle, mentre
    # Postgres le applica sempre. Senza questo, i test non vedrebbero gli
    # effetti di ON DELETE CASCADE e SET NULL, e passerebbero comportamenti
    # che in produzione si comportano diversamente.
    @event.listens_for(engine, "connect")
    def _abilita_foreign_key(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
