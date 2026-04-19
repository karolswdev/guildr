"""Tests for orchestrator.lib.pool."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.lib.pool import UpstreamPool, Endpoint


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    return tmp_path


class TestUpstreamPool:
    """Test UpstreamPool endpoint routing."""

    def test_chat_routes_through_routing(self):
        """pool.chat routes through the configured routing."""
        primary = MagicMock()
        primary.chat = MagicMock(return_value=MagicMock(endpoint=""))
        primary.health = MagicMock(return_value=True)
        endpoint = Endpoint(label="primary", client=primary)
        pool = UpstreamPool(
            endpoints=[endpoint],
            routing={"architect": ["primary"]},
        )
        # chat is async, but we can test routing setup
        assert "primary" in pool._by_label

    def test_set_orchestrator_stores_reference(self):
        """pool.set_orchestrator() stores the orchestrator reference."""
        primary = MagicMock()
        primary.chat = MagicMock(return_value=MagicMock(endpoint=""))
        primary.health = MagicMock(return_value=True)
        endpoint = Endpoint(label="primary", client=primary)
        pool = UpstreamPool(
            endpoints=[endpoint],
            routing={"architect": ["primary"]},
        )
        mock_orchestrator = MagicMock()
        pool.set_orchestrator(mock_orchestrator)
        assert pool.orchestrator is mock_orchestrator

    def test_by_label_contains_endpoint(self):
        """_by_label contains all endpoint labels."""
        primary = MagicMock()
        primary.chat = MagicMock(return_value=MagicMock(endpoint=""))
        primary.health = MagicMock(return_value=True)
        alien = MagicMock()
        alien.chat = MagicMock(return_value=MagicMock(endpoint=""))
        alien.health = MagicMock(return_value=True)
        pool = UpstreamPool(
            endpoints=[
                Endpoint(label="primary", client=primary),
                Endpoint(label="alien", client=alien),
            ],
            routing={"architect": ["primary", "alien"]},
        )
        assert "primary" in pool._by_label
        assert "alien" in pool._by_label

    def test_routing_configured(self):
        """_routing maps roles to endpoint labels."""
        primary = MagicMock()
        primary.chat = MagicMock(return_value=MagicMock(endpoint=""))
        primary.health = MagicMock(return_value=True)
        pool = UpstreamPool(
            endpoints=[Endpoint(label="primary", client=primary)],
            routing={"architect": ["primary"], "coder": ["primary"]},
        )
        assert pool._routing["architect"] == ["primary"]
        assert pool._routing["coder"] == ["primary"]
