"""Persona forum role for founding-team style PRD discussion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from orchestrator.lib.control import append_operator_context, write_compact_context
from orchestrator.lib.state import State
from orchestrator.lib.workflow import update_step_config


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
        self._persist_personas(personas)
        self.state.write_file("FOUNDING_TEAM.json", json.dumps({"personas": personas}, indent=2) + "\n")

        forum_text = self._forum_markdown(brief, personas)
        self.state.write_file("PERSONA_FORUM.md", forum_text)
        write_compact_context(self.state.project_dir, max_chars=18000)
        return "PERSONA_FORUM.md"

    def _personas(self, brief: str) -> list[dict[str, Any]]:
        config = self.step_config or {}
        raw = config.get("personas")
        personas: list[dict[str, Any]] = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                normalized = self._normalize_persona(item, default_turn_order=len(personas) + 1)
                name = normalized.get("name", "")
                if not name:
                    continue
                personas.append(normalized)
        if personas:
            return personas
        synthesized = self._synthesize_personas(brief)
        if synthesized:
            return synthesized
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

    def _synthesize_personas(self, brief: str) -> list[dict[str, Any]]:
        config = self.step_config or {}
        if config.get("auto_generate") is False:
            return []
        if self.llm is None:
            return []
        prompt = append_operator_context(
            self.state.project_dir,
            self._phase,
            (
                "Project brief:\n\n"
                f"{brief.strip()}\n\n"
                "Generate 4 to 6 founding-team personas as JSON. Each persona must contain "
                "`name`, `perspective`, `mandate`, `turn_order`, and `veto_scope`. "
                "Make them domain-specific and useful for PRD debate and decomposition. "
                "Return only JSON in the form {\"personas\": [...]}."
            ),
        )
        try:
            response = self.llm.chat(
                [
                    {"role": "system", "content": "Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4096,
            )
        except Exception:
            return []
        content = getattr(response, "content", "") or ""
        parsed = self._parse_personas_json(content)
        if not parsed:
            return []
        return parsed

    @classmethod
    def _parse_personas_json(cls, raw: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        items = data.get("personas") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        personas: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            normalized = cls._normalize_persona(item, default_turn_order=index)
            if normalized["name"]:
                personas.append(normalized)
        return personas

    def _persist_personas(self, personas: list[dict[str, Any]]) -> None:
        update_step_config(
            self.state.project_dir,
            "persona_forum",
            {"personas": personas},
        )

    def _forum_markdown(self, brief: str, personas: list[dict[str, Any]]) -> str:
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

    def _prompt(self, brief: str, personas: list[dict[str, Any]]) -> str:
        roster = "\n".join(
            f"- {item['turn_order']}. {item['name']} ({item['perspective']}): "
            f"{item['mandate']} [veto: {item['veto_scope']}]"
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
