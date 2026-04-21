"""Shared validation for durable run events."""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone
from typing import Any


CURRENT_SCHEMA_VERSION = 1

_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class EventValidationError(ValueError):
    """Raised when an event cannot be accepted into the replay ledger."""


class FutureSchemaVersionError(EventValidationError):
    """Raised when an event uses a schema version this code cannot read."""


def now_iso() -> str:
    """Return a UTC timestamp suitable for event records."""
    return datetime.now(timezone.utc).isoformat()


def new_event_id() -> str:
    """Generate a ULID-style, time-sortable event id."""
    timestamp_ms = int(time.time() * 1000)
    random_bits = secrets.randbits(80)
    value = (timestamp_ms << 80) | random_bits
    chars: list[str] = []
    for index in range(25, -1, -1):
        chars.append(_CROCKFORD32[(value >> (index * 5)) & 0x1F])
    return "".join(chars)


def normalize_event_for_write(
    event_type: str,
    fields: dict[str, Any] | None = None,
    *,
    default_run_id: str | None = None,
    require_run_id: bool = True,
) -> dict[str, Any]:
    """Return a complete, schema-valid event ready to persist or stream.

    The write path is allowed to fill in event identity fields. Existing
    identity fields are preserved so callers can retry idempotently.
    """
    payload = dict(fields or {})
    payload["type"] = event_type
    if "event_id" not in payload:
        payload["event_id"] = new_event_id()
    if "schema_version" not in payload:
        payload["schema_version"] = CURRENT_SCHEMA_VERSION
    if "ts" not in payload:
        payload["ts"] = now_iso()
    if default_run_id:
        payload.setdefault("run_id", default_run_id)
    return validate_event(payload, require_run_id=require_run_id)


def validate_event(event: dict[str, Any], *, require_run_id: bool = True) -> dict[str, Any]:
    """Validate a durable event at a read/fold boundary."""
    if not isinstance(event, dict):
        raise EventValidationError("event must be an object")

    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id.strip():
        raise EventValidationError("event_id is required")

    schema_version = event.get("schema_version")
    if not isinstance(schema_version, int):
        raise EventValidationError("schema_version is required")
    if schema_version > CURRENT_SCHEMA_VERSION:
        raise FutureSchemaVersionError(
            f"event schema_version {schema_version} is newer than supported {CURRENT_SCHEMA_VERSION}"
        )
    if schema_version < 1:
        raise EventValidationError("schema_version must be positive")

    event_type = event.get("type")
    if not isinstance(event_type, str) or not event_type.strip():
        raise EventValidationError("type is required")

    timestamp = event.get("ts")
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise EventValidationError("ts is required")

    if require_run_id:
        run_id = event.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise EventValidationError("run_id is required")

    return event
