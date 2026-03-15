"""
app/main.py
============
Huangting-Flux Hub — FastAPI Application Entry Point

The central API hub for the Huangting-Flux Agent Network.
Provides real-time Agent registration, signal broadcasting,
optimization strategy subscription, and live WebSocket streaming.

Author: Meng Yuanjing (Mark Meng) — XianDAO Labs
License: Apache 2.0
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.v1 import api_router
from app.db.base import create_tables
from app.db.seed import seed_strategies

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("Starting Huangting-Flux Hub...")

    # Create database tables
    await create_tables()
    logger.info("Database tables created/verified.")

    # Seed initial data
    from app.db.base import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await seed_strategies(db)

    logger.info("Huangting-Flux Hub is ready.")
    yield

    logger.info("Shutting down Huangting-Flux Hub...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Routes ---
app.include_router(api_router, prefix=settings.API_V1_STR)


# --- Health Check ---
@app.get("/health", tags=["Health"])
async def health_check():
    return JSONResponse({
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    })


@app.get("/", tags=["Root"])
async def root():
    return JSONResponse({
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "protocol": "Huangting Protocol v7.8",
        "author": "Meng Yuanjing (Mark Meng)",
        "website": "https://huangting.ai",
        "github": "https://github.com/XianDAO-Labs/huangting-protocol",
        "docs": "/docs",
        "endpoints": {
            "register": "POST /api/v1/register",
            "broadcast": "POST /api/v1/broadcast",
            "subscribe": "GET /api/v1/subscribe?task_type=...",
            "network_stats": "GET /api/v1/network/stats",
            "recent_signals": "GET /api/v1/signals/recent",
            "live_stream": "WS /api/v1/ws/live",
        }
    })
