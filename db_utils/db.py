import logging
import os
from typing import Any, Dict, List, Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/lead_enricher")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "lead_enricher")


class MongoDB:
    client: Optional[MongoClient] = None
    db = None
    default_db_name: str = MONGO_DB_NAME

    @classmethod
    def connect(cls) -> bool:
        """Initialise the MongoDB connection if it is not already available."""
        if cls.client is not None:
            return True

        logger.info("Attempting to connect to MongoDB at %s", MONGO_URI)
        try:
            cls.client = MongoClient(MONGO_URI)
            cls.client.admin.command("ping")
            cls.db = cls.client[cls.default_db_name]
            logger.info("Connected to MongoDB database '%s'", cls.default_db_name)
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
    def get_db(cls, db_name: Optional[str] = None):
        """Return a MongoDB database instance, creating the connection when needed."""
        if cls.client is None and not cls.connect():
            return None
        if cls.client is None:
            return None
        if db_name:
            return cls.client[db_name]
        if cls.db is None:
            cls.db = cls.client[cls.default_db_name]
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
    def status(cls, db_name: Optional[str] = None) -> dict:
        """Return health information for the MongoDB connection."""
        database = cls.get_db(db_name)
        if database is None:
            return {"status": "disconnected"}
        try:
            collections = database.list_collection_names()
            return {
                "status": "connected",
                "database": database.name,
                "collections": collections,
            }
        except PyMongoError as exc:
            logger.warning("Failed to list MongoDB collections: %s", exc)
            return {"status": "error", "error": str(exc)}


def _get_collection(collection_name: str, db_name: Optional[str] = None) -> Optional[Collection]:
    database = MongoDB.get_db(db_name)
    if database is None:
        logger.error("MongoDB database '%s' is not available", db_name or MongoDB.default_db_name)
        return None
    return database[collection_name]

def insert_document(collection_name: str, document: Dict[str, Any], db_name: Optional[str] = None) -> Optional[str]:
    """Insert a single document into the specified collection."""
    collection = _get_collection(collection_name, db_name)
    if collection is None:
        return None
    try:
        result = collection.insert_one(document)
        return str(result.inserted_id)
    except PyMongoError as exc:
        logger.error("Failed to insert document into %s: %s", collection_name, exc)
        return None

def insert_many_documents(collection_name: str, documents: List[Dict[str, Any]], db_name: Optional[str] = None) -> List[str]:
    """Insert multiple documents at once into the specified collection."""
    if not documents:
        return []
    collection = _get_collection(collection_name, db_name)
    if collection is None:
        return []
    try:
        result = collection.insert_many(documents)
        return [str(doc_id) for doc_id in result.inserted_ids]
    except PyMongoError as exc:
        logger.error("Failed to insert documents into %s: %s", collection_name, exc)
        return []

def update_document(
    collection_name: str,
    filters: Dict[str, Any],
    update: Dict[str, Any],
    db_name: Optional[str] = None,
) -> int:
    """Update a single document matching the filters."""
    collection = _get_collection(collection_name, db_name)
    if collection is None:
        return 0
    try:
        result = collection.update_one(filters, update)
        return result.modified_count
    except PyMongoError as exc:
        logger.error("Failed to update documents in %s: %s", collection_name, exc)
        return 0

def update_many_documents(
    collection_name: str,
    filters: Dict[str, Any],
    update: Dict[str, Any],
    db_name: Optional[str] = None,
) -> int:
    """Update multiple documents matching the filters."""
    collection = _get_collection(collection_name, db_name)
    if collection is None:
        return 0
    try:
        result = collection.update_many(filters, update)
        return result.modified_count
    except PyMongoError as exc:
        logger.error("Failed to update documents in %s: %s", collection_name, exc)
        return 0

def fetch_documents(
    collection_name: str,
    filters: Optional[Dict[str, Any]] = None,
    projection: Optional[Dict[str, Any]] = None,
    limit: Optional[int] = None,
    db_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch documents from a collection using optional filters and projection."""
    collection = _get_collection(collection_name, db_name)
    if collection is None:
        return []
    try:
        cursor = collection.find(filters or {}, projection)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)
    except PyMongoError as exc:
        logger.error("Failed to fetch documents from %s: %s", collection_name, exc)
        return []
