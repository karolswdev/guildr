"""Tests for PWA shell files."""

from __future__ import annotations

import json
from pathlib import Path


FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"


class TestManifest:
    """Verify manifest.json structure."""

    def test_manifest_exists(self) -> None:
        assert (FRONTEND_DIR / "manifest.json").exists()

    def test_has_name(self) -> None:
        manifest = json.loads((FRONTEND_DIR / "manifest.json").read_text())
        assert "name" in manifest
        assert len(manifest["name"]) > 0

    def test_has_start_url(self) -> None:
        manifest = json.loads((FRONTEND_DIR / "manifest.json").read_text())
        assert "start_url" in manifest

    def test_has_display_standalone(self) -> None:
        manifest = json.loads((FRONTEND_DIR / "manifest.json").read_text())
        assert manifest["display"] == "standalone"

    def test_has_icons(self) -> None:
        manifest = json.loads((FRONTEND_DIR / "manifest.json").read_text())
        assert "icons" in manifest
        assert len(manifest["icons"]) >= 1

    def test_icons_have_sizes(self) -> None:
        manifest = json.loads((FRONTEND_DIR / "manifest.json").read_text())
        for icon in manifest["icons"]:
            assert "sizes" in icon
            assert "src" in icon
            assert "type" in icon


class TestServiceWorker:
    """Verify service worker file."""

    def test_sw_exists(self) -> None:
        assert (FRONTEND_DIR / "sw.js").exists()

    def test_sw_registers_cache(self) -> None:
        sw = (FRONTEND_DIR / "sw.js").read_text()
        assert "CACHE_NAME" in sw
        assert "install" in sw
        assert "fetch" in sw

    def test_sw_offline_fallback(self) -> None:
        sw = (FRONTEND_DIR / "sw.js").read_text()
        assert "offline" in sw.lower()


class TestIndexHtml:
    """Verify index.html structure."""

    def test_html_exists(self) -> None:
        assert (FRONTEND_DIR / "index.html").exists()

    def test_has_manifest_link(self) -> None:
        html = (FRONTEND_DIR / "index.html").read_text()
        assert 'rel="manifest"' in html
        assert 'href="/manifest.json"' in html

    def test_has_apple_mobile_web_app(self) -> None:
        html = (FRONTEND_DIR / "index.html").read_text()
        assert "apple-mobile-web-app-capable" in html

    def test_has_service_worker_registration(self) -> None:
        html = (FRONTEND_DIR / "index.html").read_text()
        assert "serviceWorker" in html
        assert 'register("/sw.js")' in html

    def test_has_offline_banner(self) -> None:
        html = (FRONTEND_DIR / "index.html").read_text()
        assert "offline" in html.lower()
        assert "needs LAN" in html

    def test_has_viewport_meta(self) -> None:
        html = (FRONTEND_DIR / "index.html").read_text()
        assert "viewport" in html
        assert "width=device-width" in html


class TestAppTs:
    """Verify app.ts structure."""

    def test_app_ts_exists(self) -> None:
        assert (FRONTEND_DIR / "src" / "app.ts").exists()

    def test_has_hash_routing(self) -> None:
        app = (FRONTEND_DIR / "src" / "app.ts").read_text()
        assert "hashchange" in app
        assert "navigate" in app

    def test_has_api_functions(self) -> None:
        app = (FRONTEND_DIR / "src" / "app.ts").read_text()
        assert "apiGet" in app
        assert "apiPost" in app
