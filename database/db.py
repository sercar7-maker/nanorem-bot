"""Database Connection and Session Management for NANOREM MLM System.
Using SQLAlchemy for ORM and session handling.
"""
import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import SQLAlchemyError

# Import Base from models to enable table creation
from .models import Base
from config import DATABASE_URL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine and Session Setup
# ---------------------------------------------------------------------------
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

_engine = create_engine(DATABASE_URL, connect_args=_connect_args)
_session_factory = sessionmaker(bind=_engine)

# Thread-local scoped session (safe for multi-threaded bot)
SessionLocal = scoped_session(_session_factory)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables defined in models.py.
    Call once at application startup.
    """
    try:
        Base.metadata.create_all(_engine)
        logger.info("init_db: all tables created successfully.")
    except SQLAlchemyError as e:
        logger.error(f"init_db: failed to create tables: {e}")
        raise


@contextmanager
def get_session():
    """Context manager for obtaining a DB session with auto-commit/rollback."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"check_connection: failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Legacy DatabaseManager class (kept for backward compatibility)
# ---------------------------------------------------------------------------
class DatabaseManager:
    """Wrapper around module-level engine/session for backward compatibility."""

    def __init__(self, db_url: str = None):
        self.db_url = db_url or DATABASE_URL
        self.engine = _engine
        self.Session = SessionLocal

    def init_db(self):
        return init_db()

    def get_session(self):
        return SessionLocal()

    def remove_session(self):
        SessionLocal.remove()

    def check_connection(self) -> bool:
        return check_connection()


# Singleton instance (legacy usage)
db = DatabaseManager()
