"""Founding-team roster loader (A-8.2).

Single entry point for engine code to pick up the persona roster without
caring where it came from — ``FOUNDING_TEAM.json`` on disk, workflow step
config, or empty. Returns a list of :class:`Persona` objects.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.lib.consult import Persona, personas_from_dicts

FOUNDING_TEAM_PATH = "FOUNDING_TEAM.json"


def load_personas(project_dir: Path) -> list[Persona]:
    """Read ``FOUNDING_TEAM.json`` and return personas, or an empty list."""
    path = project_dir / FOUNDING_TEAM_PATH
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, dict):
        return []
    personas_raw = raw.get("personas") or []
    if not isinstance(personas_raw, list):
        return []
    return personas_from_dicts(personas_raw)


def personas_to_dicts(personas: list[Persona]) -> list[dict[str, Any]]:
    return [
        {
            "name": p.name,
            "perspective": p.perspective,
            "mandate": p.mandate,
            "veto_scope": p.veto_scope,
            "turn_order": p.turn_order,
        }
        for p in personas
    ]
