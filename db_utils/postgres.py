import logging
import os
from typing import Optional

import psycopg
from psycopg import sql
from psycopg.errors import DatabaseError, OperationalError

logger = logging.getLogger(__name__)

POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://postgres@127.0.0.1:5432/postgres")


class PostgresDB:
    connection: Optional[psycopg.Connection] = None

    @classmethod
    def connect(cls) -> bool:
        """Establish a PostgreSQL connection if one is not already open."""
        if cls.connection is not None:
            return True

        logger.info("Attempting to connect to PostgreSQL using DSN: %s", POSTGRES_DSN)
        try:
            cls.connection = psycopg.connect(POSTGRES_DSN, autocommit=True)
            cls.connection.execute(sql.SQL("SELECT 1"))
            logger.info("Connected to PostgreSQL")
            return True
        except (OperationalError, DatabaseError) as exc:
            logger.error("Failed to connect to PostgreSQL: %s", exc)
            cls.connection = None
            return False

    @classmethod
    def close(cls) -> None:
        """Close the PostgreSQL connection if it exists."""
        if cls.connection is not None:
            cls.connection.close()
            cls.connection = None
            logger.info("Closed PostgreSQL connection")

    @classmethod
    def get_connection(cls) -> Optional[psycopg.Connection]:
        """Return the active PostgreSQL connection."""
        return cls.connection

    @classmethod
    def is_connected(cls) -> bool:
        """Return whether PostgreSQL is connected and responding."""
        if cls.connection is None:
            return False
        try:
            cls.connection.execute(sql.SQL("SELECT 1"))
            return True
        except (OperationalError, DatabaseError) as exc:
            logger.warning("PostgreSQL ping failed: %s", exc)
            return False

    @classmethod
    def status(cls) -> dict:
        """Return diagnostic information for the PostgreSQL connection."""
        if not cls.is_connected():
            return {"status": "disconnected"}
        try:
            with cls.connection.cursor() as cur:
                cur.execute("SELECT current_database(), current_user")
                db_name, db_user = cur.fetchone()
            return {
                "status": "connected",
                "database": db_name,
                "user": db_user,
            }
        except (OperationalError, DatabaseError) as exc:
            logger.warning("Failed to query PostgreSQL status: %s", exc)
            return {"status": "error", "error": str(exc)}
