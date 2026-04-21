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


@pytest.mark.asyncio
async def test_vendored_asset_served() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(
            "/assets/environments/hex-grid.png",
            headers={"X-Forwarded-For": "192.168.1.5"},
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert len(resp.content) > 0


@pytest.mark.asyncio
async def test_vendored_glb_asset_served_with_model_mime() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(
            "/assets/poly-pizza/planet-18Uxrb2dIc/planet-18Uxrb2dIc.glb",
            headers={"X-Forwarded-For": "192.168.1.5"},
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "model/gltf-binary"
    assert resp.content[:4] == b"glTF"


@pytest.mark.asyncio
async def test_ultimate_space_kit_glb_served_with_model_mime() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(
            "/assets/poly-pizza/ultimate-space-kit/models/Astronaut.glb",
            headers={"X-Forwarded-For": "192.168.1.5"},
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "model/gltf-binary"
    assert resp.content[:4] == b"glTF"
