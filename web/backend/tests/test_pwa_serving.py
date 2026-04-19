"""Verify the FastAPI app actually serves the PWA shell.

Without this, the frontend bundle could exist on disk but be unreachable
through the backend — exactly the gap that hid for most of phase 6.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from web.backend.app import create_app


@pytest.mark.asyncio
async def test_index_html_served() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/", headers={"X-Forwarded-For": "192.168.1.5"})
    assert resp.status_code == 200
    assert "<html" in resp.text.lower()
    assert "/dist/app.js" in resp.text


@pytest.mark.asyncio
async def test_manifest_served() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/manifest.json", headers={"X-Forwarded-For": "192.168.1.5"})
    assert resp.status_code == 200
    assert "start_url" in resp.text


@pytest.mark.asyncio
async def test_sw_served() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/sw.js", headers={"X-Forwarded-For": "192.168.1.5"})
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_bundle_served() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dist/app.js", headers={"X-Forwarded-For": "192.168.1.5"})
    assert resp.status_code == 200
    assert len(resp.content) > 0
