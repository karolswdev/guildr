"""Configuration loading from YAML with env var overrides."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _consult_config_from_mapping(value: object) -> "ConsultConfig":
    """Build a ConsultConfig from a plain dict, tolerating missing keys."""
    if isinstance(value, ConsultConfig):
        return value
    if not isinstance(value, dict):
        return ConsultConfig()
    known = {f.name for f in fields(ConsultConfig)}
    cleaned: dict[str, object] = {}
    for key, val in value.items():
        normal_key = str(key).replace("-", "_")
        if normal_key not in known:
            continue
        if normal_key == "disabled_triggers" and isinstance(val, list):
            cleaned[normal_key] = set(val)
        else:
            cleaned[normal_key] = val
    return ConsultConfig(**cleaned)  # type: ignore[arg-type]


@dataclass
class ConsultConfig:
    """Routing + budget for founding-team consults (A-8.5)."""

    mode: str = "deterministic"
    mode_overrides: dict[str, str] = field(default_factory=dict)
    provider: str = "primary"
    provider_overrides: dict[str, str] = field(default_factory=dict)
    model: str = "qwen2.5-coder-32b"
    model_overrides: dict[str, str] = field(default_factory=dict)
    max_tokens: int = 1200
    max_tokens_overrides: dict[str, int] = field(default_factory=dict)
    temperature: float = 0.4
    timeout_s: float = 45.0
    fallback_on_error: bool = True
    disabled_triggers: set[str] = field(default_factory=set)


@dataclass
class Config:
    llama_server_url: str
    project_dir: Path
    max_retries: int = 3
    max_total_iterations: int = 20
    architect_max_passes: int = 3
    architect_pass_threshold: int = 4
    quiz_min_turns: int = 3
    quiz_max_turns: int = 10
    require_human_approval: bool = True
    expose_public: bool = False
    consult: ConsultConfig = field(default_factory=ConsultConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "Config":
        """Load config from a YAML file.

        Raises:
            yaml.YAMLError: if the file is not valid YAML.
            ValueError: if required fields are missing.
        """
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError(f"Config YAML must be a mapping, got {type(data).__name__}")

        # Map yaml keys to dataclass fields (allow hyphenated yaml keys)
        # and silently drop keys that belong to other loaders (e.g.
        # ``endpoints`` / ``routing`` → ``orchestrator.lib.endpoints``).
        known_fields = {f.name for f in fields(cls)}
        normalised: dict[str, object] = {}
        for key, value in data.items():
            normal_key = key.replace("-", "_")
            if normal_key in known_fields:
                normalised[normal_key] = value

        # Only llama_server_url and project_dir are strictly required
        required = {"llama_server_url", "project_dir"}
        missing = required - set(normalised)
        if missing:
            raise ValueError(f"Missing required config fields: {', '.join(sorted(missing))}")

        # Ensure project_dir is a Path
        normalised["project_dir"] = Path(normalised["project_dir"])

        # Materialize nested ConsultConfig from a plain mapping, if provided.
        if "consult" in normalised:
            normalised["consult"] = _consult_config_from_mapping(normalised["consult"])

        return cls(**normalised)  # type: ignore[arg-type]

    @classmethod
    def from_env(cls) -> "Config":
        """Build config from environment variables.

        Required: LLAMA_SERVER_URL (or LLAMA_URL), PROJECT_DIR.
        Optional overrides for all other fields.
        """
        url = (
            os.environ.get("LLAMA_SERVER_URL")
            or os.environ.get("LLAMA_URL")
            or os.environ.get("LLAMA_PRIMARY_URL")
        )
        if not url:
            raise ValueError(
                "LLAMA_SERVER_URL (or LLAMA_URL / LLAMA_PRIMARY_URL) is required"
            )

        project_dir_str = os.environ.get(
            "PROJECT_DIR", os.environ.get("ORCHESTRATOR_PROJECT_DIR", ".")
        )

        def _int(name: str, default: int) -> int:
            v = os.environ.get(name)
            if v is not None:
                return int(v)
            return default

        def _bool(name: str, default: bool) -> bool:
            v = os.environ.get(name)
            if v is None:
                return default
            return v.lower() in ("1", "true", "yes", "on")

        def _str(name: str, default: str) -> str:
            return os.environ.get(name, default)

        return cls(
            llama_server_url=_str("LLAMA_SERVER_URL", url),
            project_dir=Path(project_dir_str),
            max_retries=_int("ORCHESTRATOR_MAX_RETRIES", cls.max_retries),
            max_total_iterations=_int(
                "ORCHESTRATOR_MAX_ITERATIONS", cls.max_total_iterations
            ),
            architect_max_passes=_int(
                "ARCHITECT_MAX_PASSES", cls.architect_max_passes
            ),
            architect_pass_threshold=_int(
                "ARCHITECT_PASS_THRESHOLD", cls.architect_pass_threshold
            ),
            quiz_min_turns=_int("QUIZ_MIN_TURNS", cls.quiz_min_turns),
            quiz_max_turns=_int("QUIZ_MAX_TURNS", cls.quiz_max_turns),
            require_human_approval=_bool(
                "REQUIRE_HUMAN_APPROVAL", cls.require_human_approval
            ),
            expose_public=_bool("EXPOSE_PUBLIC", cls.expose_public),
        )

    def with_env_overrides(self) -> "Config":
        """Return a new Config with env vars overriding yaml defaults.

        Only overrides fields that are explicitly set in the environment.
        """
        data = {f.name: getattr(self, f.name) for f in fields(self)}

        def _int(name: str) -> int | None:
            v = os.environ.get(name)
            return int(v) if v is not None else None

        def _bool(name: str) -> bool | None:
            v = os.environ.get(name)
            if v is None:
                return None
            return v.lower() in ("1", "true", "yes", "on")

        def _str(name: str) -> str | None:
            v = os.environ.get(name)
            return v if v else None

        overrides: dict[str, object] = {}
        url = _str("LLAMA_SERVER_URL") or _str("LLAMA_URL") or _str("LLAMA_PRIMARY_URL")
        if url:
            overrides["llama_server_url"] = url

        pd = _str("PROJECT_DIR") or _str("ORCHESTRATOR_PROJECT_DIR")
        if pd:
            overrides["project_dir"] = Path(pd)

        for f in fields(self):
            if f.type is int:
                v = _int(f"ORCHESTRATOR_{f.name.upper()}")
                if v is not None:
                    overrides[f.name] = v
            elif f.type is bool:
                env_name = f.name.upper()
                if f.name not in ("llama_server_url", "project_dir"):
                    env_name = f"ORCHESTRATOR_{env_name}" if "ORCHESTRATOR_" not in env_name else env_name.upper()
                v = _bool(env_name)
                if v is not None:
                    overrides[f.name] = v

        return type(self)(**{**data, **overrides})  # type: ignore[arg-type]
