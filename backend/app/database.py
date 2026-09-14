"""Setup connessione al database (Neon PostgreSQL via SQLAlchemy sync).

Neon richiede TLS: la `DATABASE_URL` deve contenere `?sslmode=require`.
Usiamo il driver `psycopg` (v3) in modalità sincrona, che è più che
sufficiente per il carico dell'MVP e semplifica il codice degli endpoint.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# pool_pre_ping evita errori su connessioni chiuse dal serverless di Neon
# (che va in idle/sleep). pool_recycle chiude le connessioni troppo vecchie.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Base dichiarativa per tutti i modelli ORM."""


def get_db() -> Generator[Session, None, None]:
    """Dependency FastAPI: fornisce una sessione DB e la chiude a fine richiesta."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
