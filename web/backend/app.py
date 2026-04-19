"""FastAPI application — orchestrator control plane."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from web.backend.middleware import LanOnlyMiddleware

logger = logging.getLogger(__name__)


def _include_router(app: FastAPI, module_name: str, prefix: str) -> None:
    """Try to include a route module; log debug on failure."""
    try:
        mod = __import__(f"web.backend.routes.{module_name}", fromlist=["router"])
        app.include_router(mod.router, prefix=prefix, tags=[module_name])
    except ImportError:
        logger.debug("Route module '%s' not yet available", module_name)


def create_app(store=None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        store: Optional ProjectStore override (for testing).
    """
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

    # Include route modules (each is independent; missing modules are logged)
    _include_router(app, "projects", "/api/projects")
    _include_router(app, "quiz", "/api/projects")
    _include_router(app, "gates", "/api/projects")
    _include_router(app, "stream", "/api/projects")
    _include_router(app, "artifacts", "/api/projects")
    _include_router(app, "metrics", "/api/llama")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
