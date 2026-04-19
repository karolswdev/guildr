"""Tests for metrics passthrough routes."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from web.backend.app import create_app


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def mock_upstream_url() -> str:
    """Override the upstream URL to point at the mock server."""
    return "http://mock-llama:8080"


@respx.mock
@pytest.mark.asyncio
async def test_metrics_passthrough(app: FastAPI, mock_upstream_url: str) -> None:
    """GET /llama/metrics returns llama-server's raw metrics."""
    # Mock the upstream response
    metrics_body = "# HELP http_requests_total\n# TYPE http_requests_total counter\nhttp_requests_total 42\n"
    respx.get(f"{mock_upstream_url}/metrics").respond(content=metrics_body)

    with patch("web.backend.routes.metrics._DEFAULT_PRIMARY_URL", mock_upstream_url):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/llama/metrics")

    assert response.status_code == 200
    assert metrics_body in response.text


@respx.mock
@pytest.mark.asyncio
async def test_health_passthrough(app: FastAPI, mock_upstream_url: str) -> None:
    """GET /llama/health returns llama-server's health JSON."""
    respx.get(f"{mock_upstream_url}/health").respond(json={"status": "ok"})

    with patch("web.backend.routes.metrics._DEFAULT_PRIMARY_URL", mock_upstream_url):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/llama/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@respx.mock
@pytest.mark.asyncio
async def test_metrics_upstream_error_returns_502(app: FastAPI, mock_upstream_url: str) -> None:
    """Upstream errors → 502 with useful message."""
    respx.get(f"{mock_upstream_url}/metrics").respond(status_code=503)

    with patch("web.backend.routes.metrics._DEFAULT_PRIMARY_URL", mock_upstream_url):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/llama/metrics")

    assert response.status_code == 502


@respx.mock
@pytest.mark.asyncio
async def test_metrics_connection_refused_returns_502(app: FastAPI, mock_upstream_url: str) -> None:
    """Connection refused → 502 with useful message."""
    respx.get(f"{mock_upstream_url}/metrics").mock(side_effect=Exception("Connection refused"))

    with patch("web.backend.routes.metrics._DEFAULT_PRIMARY_URL", mock_upstream_url):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/llama/metrics")

    assert response.status_code == 502


@respx.mock
@pytest.mark.asyncio
async def test_health_upstream_error_returns_502(app: FastAPI, mock_upstream_url: str) -> None:
    """Health upstream errors → 502."""
    respx.get(f"{mock_upstream_url}/health").respond(status_code=503)

    with patch("web.backend.routes.metrics._DEFAULT_PRIMARY_URL", mock_upstream_url):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/llama/health")

    assert response.status_code == 502
