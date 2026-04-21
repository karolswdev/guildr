"""Secret-key scrubbing for structured payloads.

Shared by the orchestrator (raw LLM I/O logging) and the web backend
(operator intent persistence) so both surfaces honour the same redaction
rules. One definition, one set of markers.
"""

from __future__ import annotations

from typing import Any

_SECRET_MARKERS = (
    "authorization",
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
)


def is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SECRET_MARKERS)


def scrub_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if is_secret_key(str(key)) else scrub_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub_payload(item) for item in value]
    return value
