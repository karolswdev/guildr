"""FastAPI application — orchestrator control plane."""

from __future__ import annotations

import logging
import os
import sys

from fastapi import FastAPI

from web.backend.middleware import LanOnlyMiddleware

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Orchestrator",
        description="AI Orchestrator — single-user LAN-only control plane",
        version="0.1.0",
    )

    # Log WARNING if exposing to public internet
    if os.environ.get("ORCHESTRATOR_EXPOSE_PUBLIC") == "1":
        logger.warning(
            "ORCHESTRATOR_EXPOSE_PUBLIC=1 — accepting non-RFC1918 connections"
        )

    # Mount LAN-only middleware BEFORE any routes
    app.add_middleware(LanOnlyMiddleware)

    # Import and include routes (lazy to avoid import errors if routes
    # modules don't exist yet during early phase development)
    try:
        from web.backend.routes import projects, quiz, gates, stream

        app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
        app.include_router(quiz.router, prefix="/api/projects", tags=["quiz"])
        app.include_router(gates.router, prefix="/api/projects", tags=["gates"])
        app.include_router(stream.router, prefix="/api/projects", tags=["stream"])
    except ImportError:
        logger.debug("Some route modules not yet available")

    try:
        from web.backend.routes import metrics

        app.include_router(metrics.router, prefix="/api/llama", tags=["llama"])
    except ImportError:
        logger.debug("Metrics route module not yet available")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
