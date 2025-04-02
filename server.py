from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
from logging.handlers import RotatingFileHandler
from api.endpoints.google_sheets import router as google_sheet_router
from api.endpoints.workflow import router as workflow_router
from api.endpoints.orchestrator import router as orchestrator_router

# Configure logging with rotation
os.makedirs('data/logs', exist_ok=True)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create a rotating file handler (10 MB per file, max 5 files)
file_handler = RotatingFileHandler(
    'data/logs/api.log', 
    maxBytes=10*1024*1024,
    backupCount=5
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Add handlers to logger
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

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint that returns AI information"""
    return {
        "message": "Lead Enricher AI is running",
        "version": "1.0.0"
    }

# Include Other API via Router
app.include_router(google_sheet_router)
app.include_router(workflow_router)
app.include_router(orchestrator_router)