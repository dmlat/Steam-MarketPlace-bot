"""Database session management."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from steam_scanner.config import DATABASE_URL
from steam_scanner.db.models import Base

_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            echo=False,
        )
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables from ORM models."""
    Base.metadata.create_all(bind=get_engine())


def init_db_from_sql(sql_path: str) -> None:
    """Apply raw SQL schema file."""
    engine = get_engine()
    with open(sql_path, encoding="utf-8") as f:
        sql = f.read()
    with engine.connect() as conn:
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
