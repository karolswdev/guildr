"""Secret-key scrubbing for structured payloads.

Shared by the orchestrator (raw LLM I/O logging) and the web backend
(operator intent persistence) so both surfaces honour the same redaction
rules. One definition, one set of markers.
"""

from __future__ import annotations

import re
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
    if isinstance(value, str):
        return scrub_text(value)
    return value


def scrub_text(value: str) -> str:
    """Redact common inline secret shapes from free-form strings."""
    prefix_patterns = (
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+",
        r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+",
    )
    scrubbed = value
    for pattern in prefix_patterns:
        scrubbed = re.sub(pattern, r"\1[redacted]", scrubbed)
    scrubbed = re.sub(r"\bsk-[A-Za-z0-9_\-]{8,}\b", "[redacted]", scrubbed)
    return scrubbed
