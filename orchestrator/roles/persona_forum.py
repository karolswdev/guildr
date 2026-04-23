"""Persona forum role for founding-team style PRD discussion.

Post-H6 this role is fully deterministic: it picks a persona roster
(operator-supplied or keyword-derived from the brief) and emits a
templated forum markdown. The pre-H6 path that called an LLM through
the sync pool was removed when the pool machinery was sunset —
``PERSONA_FORUM.md`` is a pre-phase scaffold, not a model-generated
artifact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from orchestrator.lib.control import write_compact_context
from orchestrator.lib.discussion import append_persona_discussion_entries
from orchestrator.lib.state import State
from orchestrator.lib.workflow import update_step_config


@dataclass
class PersonaForum:
    """Creates a persona roster and discussion artifact before architecture."""

    state: State
    step_config: dict[str, Any] | None = None
    _phase_logger: Any = None
    _phase: str = "persona_forum"
    _role: str = "persona_forum"

    def execute(self) -> str:
        self.synthesize(
            event_bus=self.state.events,
            project_id=self.state.project_dir.name,
            compact=True,
        )
        return "PERSONA_FORUM.md"

    def synthesize_without_compaction(
        self,
        *,
        event_bus: Any | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Write persona artifacts for HTTP control without compacting context."""
        return self.synthesize(
            event_bus=event_bus,
            project_id=project_id,
            compact=False,
        )

    def synthesize(
        self,
        *,
        event_bus: Any | None = None,
        project_id: str | None = None,
        compact: bool = True,
    ) -> dict[str, Any]:
        """Create founding-team artifacts and optional discussion projections."""
        brief = self.state.read_file("qwendea.md")
        personas = self._personas(brief)
        self._persist_personas(personas)
        self.state.write_file(
            "FOUNDING_TEAM.json", json.dumps({"personas": personas}, indent=2) + "\n"
        )

        forum_text = self._fallback_forum(brief, personas)
        self.state.write_file("PERSONA_FORUM.md", forum_text)
        discussion_entries: list[dict[str, Any]] = []
        if event_bus is not None:
            discussion_entries = append_persona_discussion_entries(
                self.state.project_dir,
                personas,
                event_bus=event_bus,
                project_id=project_id or self.state.project_dir.name,
                source_refs=["artifact:FOUNDING_TEAM.json", "artifact:PERSONA_FORUM.md"],
            )
            from orchestrator.lib.memory_palace import memory_event_fields

            provenance = memory_event_fields(
                project_id or self.state.project_dir.name, self.state.project_dir
            )
            event_bus.emit(
                "persona_forum_created",
                project_id=project_id or self.state.project_dir.name,
                personas=personas,
                forum_path="PERSONA_FORUM.md",
                founding_team_path="FOUNDING_TEAM.json",
                artifact_refs=["FOUNDING_TEAM.json", "PERSONA_FORUM.md"],
                source_refs=[
                    "artifact:FOUNDING_TEAM.json",
                    "artifact:PERSONA_FORUM.md",
                ],
                wake_up_hash=provenance.get("wake_up_hash"),
                memory_refs=list(provenance.get("memory_refs") or []),
            )
        if compact:
            write_compact_context(self.state.project_dir, max_chars=18000)
        return {
            "personas": personas,
            "forum_path": "PERSONA_FORUM.md",
            "discussion_entries": discussion_entries,
        }

    def _personas(self, brief: str) -> list[dict[str, Any]]:
        config = self.step_config or {}
        raw = config.get("personas")
        personas: list[dict[str, Any]] = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                normalized = self._normalize_persona(
                    item, default_turn_order=len(personas) + 1
                )
                name = normalized.get("name", "")
                if not name:
                    continue
                personas.append(normalized)
        if personas:
            return personas
        return self._default_personas(brief)

    @staticmethod
    def _normalize_persona(item: dict[str, Any], default_turn_order: int) -> dict[str, Any]:
        return {
            "name": str(item.get("name", "")).strip(),
            "perspective": str(item.get("perspective", "")).strip() or "stakeholder",
            "mandate": str(item.get("mandate", "")).strip() or "Provide concise review feedback.",
            "turn_order": int(item.get("turn_order", default_turn_order) or default_turn_order),
            "veto_scope": str(item.get("veto_scope", "")).strip() or "advisory",
        }

    @classmethod
    def _default_personas(cls, brief: str) -> list[dict[str, Any]]:
        lowered = brief.lower()
        if any(term in lowered for term in ("game", "gameplay", "player", "steam", "combat", "level")):
            return cls._finalize_defaults([
                {
                    "name": "Player Advocate",
                    "perspective": "client",
                    "mandate": "Push for delight, clarity, and moment-to-moment usability.",
                    "veto_scope": "player experience regression",
                },
                {
                    "name": "Studio Head",
                    "perspective": "business owner",
                    "mandate": "Guard scope, shipping risk, and team leverage.",
                    "veto_scope": "scope explosion",
                },
                {
                    "name": "Vision Holder",
                    "perspective": "creative visionary",
                    "mandate": "Protect the emotional core and long-term identity of the product.",
                    "veto_scope": "loss of product identity",
                },
                {
                    "name": "Gameplay Engineer",
                    "perspective": "implementer",
                    "mandate": "Translate ideas into testable technical slices.",
                    "veto_scope": "non-implementable mechanics",
                },
            ])
        if any(term in lowered for term in ("api", "backend", "service", "auth", "database")):
            return cls._finalize_defaults([
                {
                    "name": "Product Owner",
                    "perspective": "client",
                    "mandate": "Keep the feature set tied to the real user problem.",
                    "veto_scope": "user value drift",
                },
                {
                    "name": "Platform Engineer",
                    "perspective": "implementer",
                    "mandate": "Optimize for maintainable architecture and operational simplicity.",
                    "veto_scope": "unbounded technical debt",
                },
                {
                    "name": "Security Reviewer",
                    "perspective": "risk",
                    "mandate": "Call out abuse paths, auth gaps, and data handling issues.",
                    "veto_scope": "security regression",
                },
                {
                    "name": "Operator",
                    "perspective": "runtime owner",
                    "mandate": "Demand predictable deploy, observability, and recovery paths.",
                    "veto_scope": "operational fragility",
                },
            ])
        return cls._finalize_defaults([
            {
                "name": "End User",
                "perspective": "client",
                "mandate": "Represent usability, clarity, and value.",
                "veto_scope": "usability regression",
            },
            {
                "name": "Founder",
                "perspective": "business owner",
                "mandate": "Keep the project aligned with purpose and scope.",
                "veto_scope": "product misalignment",
            },
            {
                "name": "Domain Specialist",
                "perspective": "subject matter expert",
                "mandate": "Surface domain-specific correctness and edge cases.",
                "veto_scope": "domain correctness",
            },
            {
                "name": "Implementation Lead",
                "perspective": "implementer",
                "mandate": "Break work into verifiable, low-context execution steps.",
                "veto_scope": "non-deterministic implementation",
            },
        ])

    @classmethod
    def _finalize_defaults(cls, raw_personas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            cls._normalize_persona(item, default_turn_order=index)
            for index, item in enumerate(raw_personas, start=1)
        ]

    def _persist_personas(self, personas: list[dict[str, Any]]) -> None:
        update_step_config(
            self.state.project_dir,
            "persona_forum",
            {"personas": personas},
        )

    @staticmethod
    def _fallback_forum(brief: str, personas: list[dict[str, Any]]) -> str:
        lines = [
            "# Persona Forum",
            "",
            "## Founding Team",
            "",
        ]
        for item in personas:
            lines.append(
                f"- **{item['turn_order']}. {item['name']}** ({item['perspective']}): "
                f"{item['mandate']} [veto: {item['veto_scope']}]"
            )
        lines.extend([
            "",
            "## Roundtable",
            "",
        ])
        for item in personas:
            lines.append(
                f"### {item['name']}\n"
                f"- Core concern: {item['mandate']}\n"
                "- What must stay true: keep the project brief legible and decomposable.\n"
                "- What to avoid: hidden scope, vague evidence, and context-heavy coupling.\n"
            )
        lines.extend([
            "## Convergence",
            "",
            "- Preserve the core user outcome from the brief.",
            "- Prefer architecture that can be tested with bounded commands.",
            "- Break work into narrowly scoped tasks with explicit file ownership and evidence.",
            "",
            "## Open Questions",
            "",
            "- Which non-core ideas should be delayed until after the first working slice?",
            "- Which personas need explicit veto power on scope or quality?",
            "",
            "## Architecture Pressure",
            "",
            "- Keep the initial architecture small enough for low-context models to reason about.",
            "- Favor framework-native commands and manifests already present in the repo.",
            "",
            "## Brief Snapshot",
            "",
            brief.strip(),
            "",
        ])
        return "\n".join(lines)
