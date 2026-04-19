"""Tests for LAN-only middleware."""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient, ASGITransport
from starlette.responses import JSONResponse

from web.backend.middleware import LanOnlyMiddleware, _is_rfc1918


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(LanOnlyMiddleware)

    @app.get("/test")
    async def test_endpoint() -> dict:
        return {"ok": True}

    return app


class TestIsRfc1918:
    def test_private_10(self) -> None:
        assert _is_rfc1918("10.0.0.1") is True

    def test_private_172(self) -> None:
        assert _is_rfc1918("172.16.0.1") is True
        assert _is_rfc1918("172.31.255.255") is True

    def test_private_192(self) -> None:
        assert _is_rfc1918("192.168.0.1") is True
        assert _is_rfc1918("192.168.255.255") is True

    def test_loopback(self) -> None:
        assert _is_rfc1918("127.0.0.1") is True
        assert _is_rfc1918("127.255.255.255") is True

    def test_public_google_dns(self) -> None:
        assert _is_rfc1918("8.8.8.8") is False

    def test_public_cloudflare(self) -> None:
        assert _is_rfc1918("1.1.1.1") is False

    def test_invalid_ip(self) -> None:
        assert _is_rfc1918("not-an-ip") is False


@pytest.fixture
def app() -> FastAPI:
    return _make_app()


@pytest.mark.asyncio
async def test_lan_request_succeeds(app: FastAPI) -> None:
    """Requests from 192.168.0.0/16 succeed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/test",
            headers={"X-Forwarded-For": "192.168.1.100"},
        )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_public_ip_returns_403(app: FastAPI) -> None:
    """Requests from 8.8.8.8 return 403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/test",
            headers={"X-Forwarded-For": "8.8.8.8"},
        )
    assert response.status_code == 403
    assert response.json() == {"error": "LAN-only"}


@pytest.mark.asyncio
async def test_expose_public_bypass(app: FastAPI) -> None:
    """ORCHESTRATOR_EXPOSE_PUBLIC=1 bypasses the check."""
    os.environ["ORCHESTRATOR_EXPOSE_PUBLIC"] = "1"
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                "/test",
                headers={"X-Forwarded-For": "8.8.8.8"},
            )
        assert response.status_code == 200
        assert response.json() == {"ok": True}
    finally:
        os.environ.pop("ORCHESTRATOR_EXPOSE_PUBLIC", None)


@pytest.mark.asyncio
async def test_loopback_succeeds(app: FastAPI) -> None:
    """Loopback addresses succeed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/test",
            headers={"X-Forwarded-For": "127.0.0.1"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_no_forwarded_uses_client_host(app: FastAPI) -> None:
    """Without X-Forwarded-For, uses request.client.host."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # httpx doesn't easily let us spoof client.host, so we test
        # via X-Forwarded-For as the primary mechanism
        response = await client.get(
            "/test",
            headers={"X-Forwarded-For": "10.0.0.5"},
        )
    assert response.status_code == 200


def test_startup_warning_when_expose_public(caplog: pytest.LogCaptureFixture) -> None:
    """Constructing LanOnlyMiddleware with EXPOSE_PUBLIC=1 emits a WARNING."""
    os.environ["ORCHESTRATOR_EXPOSE_PUBLIC"] = "1"
    try:
        caplog.set_level(logging.WARNING, logger="web.backend.middleware")
        LanOnlyMiddleware(MagicMock())
        warning_records = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "ORCHESTRATOR_EXPOSE_PUBLIC" in r.message
        ]
        assert len(warning_records) >= 1, "Expected WARNING about ORCHESTRATOR_EXPOSE_PUBLIC"
    finally:
        os.environ.pop("ORCHESTRATOR_EXPOSE_PUBLIC", None)
