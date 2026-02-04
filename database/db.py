"""Database Connection and Session Management for NANOREM MLM System."""

import logging
import sqlite3
from pathlib import Path

from config import DATABASE_URL, BASE_DIR

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manage database connection and basic operations."""

    def __init__(self, db_url: str = None):
        """Initialize database manager."""
        self.db_url = db_url or DATABASE_URL
        self.connection = None
        logger.info(f"DatabaseManager initialized with {self.db_url}")

    def connect(self):
        """Connect to database."""
        try:
            if "sqlite" in self.db_url:
                db_path = self.db_url.replace("sqlite:///", "")
                self.connection = sqlite3.connect(db_path)
                logger.info(f"Connected to SQLite: {db_path}")
            else:
                logger.error(f"Unsupported database: {self.db_url}")
                raise ValueError(f"Unsupported database URL: {self.db_url}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def check_connection(self) -> bool:
        """Check if database connection is working."""
        try:
            if not self.connection:
                self.connect()
            
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            logger.info("Database connection check: OK")
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False

    def init_db(self):
        """Initialize database schema."""
        if not self.connection:
            self.connect()
        
        try:
            cursor = self.connection.cursor()
            
            # Create users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    telegram_id INTEGER UNIQUE,
                    first_name TEXT,
                    last_name TEXT,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create partners table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS partners (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER UNIQUE,
                    sponsor_id INTEGER,
                    level INTEGER DEFAULT 0,
                    commission_balance REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (sponsor_id) REFERENCES partners(id)
                )
            """)
            
            self.connection.commit()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")

    def __del__(self):
        """Cleanup on object destruction."""
        self.close()
