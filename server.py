from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
from logging.handlers import RotatingFileHandler
from db_utils.db import MongoDB
from db_utils.postgres import PostgresDB

# Configure logging with rotation
os.makedirs('data/logs', exist_ok=True)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create a rotating file handler (10 MB per file, max 5 files)
file_handler = RotatingFileHandler(
    'data/logs/api.log',
    maxBytes=10 * 1024 * 1024,
    backupCount=5
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Add handlers to logger if they are not already present
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# Initialize FastAPI app
app = FastAPI(
    title="Lead Enricher AI",
    description="AI for lead enrichment services",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint that returns service information."""
    return {
        "message": "Lead Enricher AI is running",
        "version": "1.0.0"
    }

#define routes below


@app.get("/db-status")
async def db_status():
    """Return the health status for MongoDB and PostgreSQL."""
    return {
        "mongo": MongoDB.status(),
        "postgres": PostgresDB.status(),
    }

@app.on_event("startup")
def startup_db_client():
    """Connect to MongoDB and PostgreSQL on application startup."""
    if MongoDB.connect():
        logger.info("MongoDB connection established")
    else:
        logger.warning("Failed to connect to MongoDB - some features may not work")

    if PostgresDB.connect():
        logger.info("PostgreSQL connection established")
    else:
        logger.warning("Failed to connect to PostgreSQL - some features may not work")

@app.on_event("shutdown")
def shutdown_db_client():
    """Close database connections on shutdown."""
    MongoDB.close()
    PostgresDB.close()
    logger.info("Database connections closed")
