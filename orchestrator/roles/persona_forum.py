"""Persona forum role for founding-team style PRD discussion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from orchestrator.lib.control import append_operator_context, write_compact_context
from orchestrator.lib.state import State


@dataclass
class PersonaForum:
    """Creates a persona roster and discussion artifact before architecture."""

    llm: Any | None
    state: State
    step_config: dict[str, Any] | None = None
    _phase_logger: Any = None
    _phase: str = "persona_forum"
    _role: str = "persona_forum"

    def execute(self) -> str:
        brief = self.state.read_file("qwendea.md")
        personas = self._personas(brief)
        self.state.write_file("FOUNDING_TEAM.json", json.dumps({"personas": personas}, indent=2) + "\n")

        forum_text = self._forum_markdown(brief, personas)
        self.state.write_file("PERSONA_FORUM.md", forum_text)
        write_compact_context(self.state.project_dir, max_chars=18000)
        return "PERSONA_FORUM.md"

    def _personas(self, brief: str) -> list[dict[str, str]]:
        config = self.step_config or {}
        raw = config.get("personas")
        personas: list[dict[str, str]] = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                perspective = str(item.get("perspective", "")).strip()
                mandate = str(item.get("mandate", "")).strip()
                if not name:
                    continue
                personas.append({
                    "name": name,
                    "perspective": perspective or "stakeholder",
                    "mandate": mandate or "Provide concise review feedback.",
                })
        if personas:
            return personas
        return self._default_personas(brief)

    @staticmethod
    def _default_personas(brief: str) -> list[dict[str, str]]:
        lowered = brief.lower()
        if any(term in lowered for term in ("game", "gameplay", "player", "steam", "combat", "level")):
            return [
                {
                    "name": "Player Advocate",
                    "perspective": "client",
                    "mandate": "Push for delight, clarity, and moment-to-moment usability.",
                },
                {
                    "name": "Studio Head",
                    "perspective": "business owner",
                    "mandate": "Guard scope, shipping risk, and team leverage.",
                },
                {
                    "name": "Vision Holder",
                    "perspective": "creative visionary",
                    "mandate": "Protect the emotional core and long-term identity of the product.",
                },
                {
                    "name": "Gameplay Engineer",
                    "perspective": "implementer",
                    "mandate": "Translate ideas into testable technical slices.",
                },
            ]
        if any(term in lowered for term in ("api", "backend", "service", "auth", "database")):
            return [
                {
                    "name": "Product Owner",
                    "perspective": "client",
                    "mandate": "Keep the feature set tied to the real user problem.",
                },
                {
                    "name": "Platform Engineer",
                    "perspective": "implementer",
                    "mandate": "Optimize for maintainable architecture and operational simplicity.",
                },
                {
                    "name": "Security Reviewer",
                    "perspective": "risk",
                    "mandate": "Call out abuse paths, auth gaps, and data handling issues.",
                },
                {
                    "name": "Operator",
                    "perspective": "runtime owner",
                    "mandate": "Demand predictable deploy, observability, and recovery paths.",
                },
            ]
        return [
            {
                "name": "End User",
                "perspective": "client",
                "mandate": "Represent usability, clarity, and value.",
            },
            {
                "name": "Founder",
                "perspective": "business owner",
                "mandate": "Keep the project aligned with purpose and scope.",
            },
            {
                "name": "Domain Specialist",
                "perspective": "subject matter expert",
                "mandate": "Surface domain-specific correctness and edge cases.",
            },
            {
                "name": "Implementation Lead",
                "perspective": "implementer",
                "mandate": "Break work into verifiable, low-context execution steps.",
            },
        ]

    def _forum_markdown(self, brief: str, personas: list[dict[str, str]]) -> str:
        prompt = self._prompt(brief, personas)
        if self.llm is None:
            return self._fallback_forum(brief, personas)
        try:
            response = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are moderating a founding-team product forum. "
                            "Return markdown with sections: Founding Team, Roundtable, "
                            "Convergence, Open Questions, and Architecture Pressure."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=8192,
            )
        except Exception:
            return self._fallback_forum(brief, personas)
        content = getattr(response, "content", "") or ""
        if not content.strip():
            return self._fallback_forum(brief, personas)
        return content.strip() + "\n"

    def _prompt(self, brief: str, personas: list[dict[str, str]]) -> str:
        roster = "\n".join(
            f"- {item['name']} ({item['perspective']}): {item['mandate']}"
            for item in personas
        )
        prompt = (
            "Project brief:\n\n"
            f"{brief.strip()}\n\n"
            "Founding team roster:\n"
            f"{roster}\n\n"
            "Simulate a tight forum where these personas debate the PRD, name tradeoffs, "
            "and converge on implementation-shaping guidance. Make the output actionable "
            "for architecture and low-context execution."
        )
        return append_operator_context(self.state.project_dir, self._phase, prompt)

    @staticmethod
    def _fallback_forum(brief: str, personas: list[dict[str, str]]) -> str:
        lines = [
            "# Persona Forum",
            "",
            "## Founding Team",
            "",
        ]
        for item in personas:
            lines.append(f"- **{item['name']}** ({item['perspective']}): {item['mandate']}")
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
