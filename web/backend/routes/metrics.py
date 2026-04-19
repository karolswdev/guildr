"""Metrics passthrough routes for llama-server observability.

GET /api/llama/metrics — Prometheus metrics from llama-server
GET /api/llama/health  — Health check passthrough
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import HTTPException
from starlette.responses import PlainTextResponse, JSONResponse

logger = logging.getLogger(__name__)

_DEFAULT_PRIMARY_URL = os.environ.get(
    "LLAMA_PRIMARY_URL", "http://127.0.0.1:8080"
)


def _get_upstream_url() -> str:
    """Get the primary llama-server URL."""
    return _DEFAULT_PRIMARY_URL


# -- routes ------------------------------------------------------------------


def _setup_routes(router_obj: Any) -> Any:
    """Attach routes to the given router."""
    from fastapi import APIRouter

    router_obj = APIRouter()

    @router_obj.get("/metrics")
    async def llama_metrics() -> PlainTextResponse:
        """Passthrough to llama-server /metrics endpoint."""
        upstream = _get_upstream_url()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{upstream}/metrics")
                resp.raise_for_status()
                return PlainTextResponse(
                    content=resp.text,
                    media_type="text/plain; version=0.0.4",
                )
        except httpx.HTTPStatusError as e:
            logger.warning("Metrics passthrough failed: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Upstream metrics error: {e.response.status_code}",
            )
        except httpx.RequestError as e:
            logger.warning("Metrics passthrough connection error: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Cannot reach llama-server at {upstream}: {e}",
            )
        except Exception as e:
            logger.warning("Metrics passthrough unexpected error: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Upstream error: {e}",
            )

    @router_obj.get("/health")
    async def llama_health() -> JSONResponse:
        """Passthrough to llama-server /health endpoint."""
        upstream = _get_upstream_url()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{upstream}/health")
                resp.raise_for_status()
                return JSONResponse(content=resp.json())
        except httpx.HTTPStatusError as e:
            logger.warning("Health passthrough failed: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Upstream health error: {e.response.status_code}",
            )
        except httpx.RequestError as e:
            logger.warning("Health passthrough connection error: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Cannot reach llama-server at {upstream}: {e}",
            )
        except Exception as e:
            logger.warning("Health passthrough unexpected error: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Upstream error: {e}",
            )

    return router_obj


router = _setup_routes(None)
