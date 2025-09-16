import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.config import settings
from db_utils.db import MongoDB
from db_utils.postgres import PostgresDB

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to MongoDB and PostgreSQL on application startup."""
    if MongoDB.connect():
        logger.info("MongoDB connection established")
    else:
        logger.warning("Failed to connect to MongoDB - some features may not work")

    if PostgresDB.connect():
        logger.info("PostgreSQL connection established")
    else:
        logger.warning("Failed to connect to PostgreSQL - some features may not work")
    
    logger.info("Application is starting up...")
    yield
    
    """Close database connections on shutdown."""
    MongoDB.close()
    PostgresDB.close()
    logger.info("Database connections closed")

# Create the app ONCE with the lifespan handler
app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    lifespan=lifespan
)

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
        "message": f"{settings.app_name} is running",
        "version": settings.app_version,
    }

@app.get("/db-status")
async def db_status():
    """Return the health status for MongoDB and PostgreSQL."""
    return {
        "mongo": MongoDB.status(),
        "postgres": PostgresDB.status(),
    }