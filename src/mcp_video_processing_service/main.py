"""FastAPI application entry point for the video processing service."""

from __future__ import annotations

import logging
import structlog
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router as api_router
from .celery_app import celery_app
from .config import settings
from .job_store import AbstractJobStore, InMemoryJobStore, RedisJobStore


def configure_logging() -> None:
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=log_level)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger(__name__)


def create_app(job_store: Optional[AbstractJobStore] = None) -> FastAPI:
    configure_logging()

    selected_job_store = job_store

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal selected_job_store
        if selected_job_store is None:
            try:
                selected_job_store = RedisJobStore(settings.redis_url)
            except Exception:  # pragma: no cover - defensive fallback
                logger.warning("Falling back to in-memory job store")
                selected_job_store = InMemoryJobStore()

        app.state.job_store = selected_job_store
        app.state.celery_app = celery_app
        yield
        if selected_job_store:
            await selected_job_store.close()

    app = FastAPI(
        title="MCP Video Processing Service",
        description="Asynchronous FFmpeg-based pipelines for concat and overlay operations",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str | list[str]]:
        return {
            "service": "mcp-video-processing-service",
            "version": "0.1.0",
            "operations": ["concat", "overlay"],
        }

    return app


app = create_app()
