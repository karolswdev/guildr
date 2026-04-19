"""FastAPI application — orchestrator control plane."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.backend.middleware import LanOnlyMiddleware

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

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

    # PWA shell. Mounted last so /api/* and /healthz win on conflict.
    # dist/ is the esbuild output; built by web/frontend/build.sh.
    if _FRONTEND_DIR.is_dir():
        dist_dir = _FRONTEND_DIR / "dist"
        if dist_dir.is_dir():
            app.mount("/dist", StaticFiles(directory=dist_dir), name="dist")

        @app.get("/")
        async def _index() -> FileResponse:
            return FileResponse(_FRONTEND_DIR / "index.html")

        @app.get("/manifest.json")
        async def _manifest() -> FileResponse:
            return FileResponse(_FRONTEND_DIR / "manifest.json")

        @app.get("/sw.js")
        async def _sw() -> FileResponse:
            return FileResponse(
                _FRONTEND_DIR / "sw.js",
                media_type="application/javascript",
            )

    return app


app = create_app()
