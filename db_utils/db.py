import logging
import os
from typing import Optional
from pymongo import MongoClient
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/lead_enricher")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "lead_enricher")


class MongoDB:
    client: Optional[MongoClient] = None
    db = None

    @classmethod
    def connect(cls) -> bool:
        """Initialise the MongoDB connection if it is not already available."""
        if cls.client is not None:
            return True

        logger.info("Attempting to connect to MongoDB at %s", MONGO_URI)
        try:
            cls.client = MongoClient(MONGO_URI)
            cls.client.admin.command("ping")
            cls.db = cls.client[MONGO_DB_NAME]
            logger.info("Connected to MongoDB database '%s'", MONGO_DB_NAME)
            return True
        except PyMongoError as exc:
            logger.error("Failed to connect to MongoDB: %s", exc)
            cls.client = None
            cls.db = None
            return False

    @classmethod
    def close(cls) -> None:
        """Close the MongoDB connection."""
        if cls.client is not None:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("Closed MongoDB connection")

    @classmethod
    def get_db(cls):
        """Return the active MongoDB database instance."""
        return cls.db

    @classmethod
    def is_connected(cls) -> bool:
        """Return whether a MongoDB connection is active and responding."""
        if cls.client is None:
            return False
        try:
            cls.client.admin.command("ping")
            return True
        except PyMongoError as exc:
            logger.warning("MongoDB ping failed: %s", exc)
            return False

    @classmethod
    def status(cls) -> dict:
        """Return health information for the MongoDB connection."""
        if not cls.is_connected():
            return {"status": "disconnected"}
        try:
            collections = cls.db.list_collection_names()
            return {
                "status": "connected",
                "database": cls.db.name,
                "collections": collections,
            }
        except PyMongoError as exc:
            logger.warning("Failed to list MongoDB collections: %s", exc)
            return {"status": "error", "error": str(exc)}
