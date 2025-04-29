import logging
import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# Configure logging
logger = logging.getLogger(__name__)

# MongoDB connection string - using 27018 to avoid conflicts
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27019/lead_enricher")

# Database name
DB_NAME = "lead_enricher"

class MongoDB:
    client = None
    db = None
    
    @classmethod
    def connect(cls):
        """
        Creates connection to MongoDB
        """
        if cls.client is None:
            try:
                cls.client = MongoClient(MONGO_URI)
                # Verify connection is successful
                cls.client.admin.command('ping')
                cls.db = cls.client[DB_NAME]
                logger.info("Connected to MongoDB at %s", MONGO_URI)
                return True
            except ConnectionFailure as e:
                logger.error("Failed to connect to MongoDB: %s", str(e))
                return False
            except Exception as e:
                logger.error("MongoDB connection error: %s", str(e))
                return False
                
    @classmethod
    def close(cls):
        """
        Closes MongoDB connection
        """
        if cls.client is not None:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("Closed MongoDB connection")
            
    @classmethod
    def get_db(cls):
        """
        Returns database instance
        """
        return cls.db