"""Database Connection and Session Management for NANOREM MLM System"""

import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
from typing import Generator

from .models import Base
from config import DATABASE_URL

logger = logging.getLogger(__name__)

# Create database engine
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    poolclass=StaticPool if "sqlite" in DATABASE_URL else None,
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

def init_db() -> None:
    """
    Initialize database by creating all tables.
    Should be called once at application startup.
    """
    try:
        logger.info("Initializing database...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

def drop_all_tables() -> None:
    """
    Drop all tables from database.
    WARNING: This will delete all data!
    """
    try:
        logger.warning("Dropping all tables from database...")
        Base.metadata.drop_all(bind=engine)
        logger.info("All tables dropped successfully")
    except Exception as e:
        logger.error(f"Failed to drop tables: {e}")
        raise

def get_db() -> Generator[Session, None, None]:
    """
    Get database session.
    Use as dependency injection in FastAPI or similar.
    
    Example:
        @app.get("/partners/")
        def get_partners(db: Session = Depends(get_db)):
            return db.query(Partner).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database session.
    
    Example:
        with get_db_session() as db:
            partner = db.query(Partner).filter_by(id=1).first()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        session.close()

class DatabaseManager:
    """
    Database manager with helper methods for common operations.
    """
    
    def __init__(self):
        self.engine = engine
        self.SessionLocal = SessionLocal
    
    def create_session(self) -> Session:
        """Create new database session."""
        return self.SessionLocal()
    
    def init_database(self) -> None:
        """Initialize database tables."""
        init_db()
    
    def reset_database(self) -> None:
        """Drop and recreate all tables."""
        drop_all_tables()
        init_db()
    
    def check_connection(self) -> bool:
        """
        Check if database connection is working.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            with self.engine.connect() as conn:
                conn.execute("SELECT 1")
            logger.info("Database connection successful")
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False
    
    def get_table_count(self, table_name: str) -> int:
        """
        Get count of records in a table.
        
        Args:
            table_name: Name of the table
        
        Returns:
            Number of records
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = result.fetchone()[0]
                return count
        except Exception as e:
            logger.error(f"Failed to get count from {table_name}: {e}")
            return 0

# Global database manager instance
db_manager = DatabaseManager()

# Event listeners for logging (optional)
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Log database connections."""
    logger.debug("Database connection established")

@event.listens_for(engine, "close")
def receive_close(dbapi_conn, connection_record):
    """Log database disconnections."""
    logger.debug("Database connection closed")
