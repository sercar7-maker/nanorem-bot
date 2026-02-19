"""Database Connection and Session Management for NANOREM MLM System.
Using SQLAlchemy for ORM and session handling.
"""
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import SQLAlchemyError

# Import Base from models to enable table creation
from .models import Base
from config import DATABASE_URL

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Manager for SQLAlchemy engine and sessions.
    
    Handles:
    - Engine initialization.
    - Table creation (init_db).
    - Scoped session management.
    """
    
    def __init__(self, db_url: str = None):
        """
        Initialize the database manager.
        
        Args:
            db_url: SQLAlchemy-compatible database URL. 
                    Defaults to config.DATABASE_URL.
        """
        self.db_url = db_url or DATABASE_URL
        
        # SQLite specific: allow multi-threaded access for the bot
        connect_args = {}
        if self.db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            
        try:
            self.engine = create_engine(self.db_url, connect_args=connect_args)
            self.session_factory = sessionmaker(bind=self.engine)
            self.Session = scoped_session(self.session_factory)
            logger.info(f"DatabaseManager: engine initialized for {self.db_url}")
        except Exception as e:
            logger.error(f"DatabaseManager: failed to initialize engine: {e}")
            raise

    def init_db(self):
        """
        Create all tables defined in models.py.
        Should be called once during application startup.
        """
        try:
            Base.metadata.create_all(self.engine)
            logger.info("DatabaseManager: all tables created successfully.")
            return True
        except SQLAlchemyError as e:
            logger.error(f"DatabaseManager: failed to create tables: {e}")
            return False

    def get_session(self):
        """
        Get a thread-local scoped session.
        """
        return self.Session()

    def remove_session(self):
        """
        Close and remove the current thread-local session.
        """
        self.Session.remove()

    def check_connection(self) -> bool:
        """
        Check if the database is reachable.
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"DatabaseManager: connection check failed: {e}")
            return False

# ---------------------------------------------------------------------------
# Global Singleton Instance
# ---------------------------------------------------------------------------
# Use this instance across the bot to share the same engine/pool.
db = DatabaseManager()
