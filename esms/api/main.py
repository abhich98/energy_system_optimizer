"""FastAPI application for EsMS optimization service."""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from esms import __version__
from esms.api.routes import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="EsMS Optimization API",
    description="REST API for day-ahead or long-term energy management optimization",
    version=__version__,
    # Auto-generated docs will be available at /docs and /redoc
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)

logger.info("EsMS API initialized successfully")
