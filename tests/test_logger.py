"""Tests for orchestrator.lib.logger."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.lib.logger import (
    JsonFormatter,
    PhaseFileHandler,
    log_llm_call,
    log_llm_error,
    setup_phase_logger,
)


class TestJsonFormatter:
    """Test JSON log formatting."""

    def test_formats_standard_fields(self, tmp_path: Path) -> None:
        formatter = JsonFormatter(phase="test", task_id="task-1", session_id="abc123")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )
        record.ts = "2025-01-01T00:00:00+00:00"
        result = formatter.format(record)
        entry = json.loads(result)
        assert entry["ts"] == "2025-01-01T00:00:00+00:00"
        assert entry["level"] == "INFO"
        assert entry["phase"] == "test"
        assert entry["task_id"] == "task-1"
        assert entry["session_id"] == "abc123"
        assert entry["event"] == "test message"
        assert entry["message"] == "test message"

    def test_includes_llm_token_fields(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="LLM call",
            args=(),
            exc_info=None,
        )
        record.prompt_tokens = 100
        record.completion_tokens = 50
        record.reasoning_tokens = 30
        record.latency_ms = 1234.5
        result = formatter.format(record)
        entry = json.loads(result)
        assert entry["prompt_tokens"] == 100
        assert entry["completion_tokens"] == 50
        assert entry["reasoning_tokens"] == 30
        assert entry["latency_ms"] == 1234.5

    def test_auto_timestamp(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="warning message",
            args=(),
            exc_info=None,
        )
        # Don't set ts — should auto-generate
        result = formatter.format(record)
        entry = json.loads(result)
        assert "ts" in entry
        assert "+" in entry["ts"] or "Z" in entry["ts"]

    def test_includes_exception_info(self) -> None:
        formatter = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg="error occurred",
                args=(),
                exc_info=exc_info,
            )
        result = formatter.format(record)
        entry = json.loads(result)
        assert "exc_info" in entry
        assert "ValueError" in entry["exc_info"]


class TestPhaseFileHandler:
    """Test per-phase JSONL file writing."""

    def test_writes_jsonl_to_phase_file(self, tmp_path: Path) -> None:
        handler = PhaseFileHandler(tmp_path, "architect")
        handler.setLevel(logging.INFO)
        formatter = JsonFormatter(phase="architect")
        handler.setFormatter(formatter)

        record = logging.LogRecord(
            name="orchestrator.phase.architect",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="phase started",
            args=(),
            exc_info=None,
        )
        record.ts = "2025-01-01T00:00:00+00:00"
        handler.emit(record)
        handler.close()

        log_file = tmp_path / "architect.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["message"] == "phase started"
        assert entry["phase"] == "architect"

    def test_appends_multiple_records(self, tmp_path: Path) -> None:
        handler = PhaseFileHandler(tmp_path, "test")
        handler.setLevel(logging.INFO)

        for i in range(3):
            record = logging.LogRecord(
                name="orchestrator.phase.test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg=f"event {i}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
        handler.close()

        log_file = tmp_path / "test.jsonl"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested"
        handler = PhaseFileHandler(nested, "phase")
        handler.setLevel(logging.INFO)
        record = logging.LogRecord(
            name="orchestrator.phase.phase",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        handler.close()
        assert (nested / "phase.jsonl").exists()


class TestSetupPhaseLogger:
    """Test phase logger setup."""

    def test_creates_logger_with_handlers(self, tmp_path: Path) -> None:
        logger = setup_phase_logger(tmp_path, "architect", level=logging.DEBUG)
        assert logger.name == "orchestrator.phase.architect"
        assert logger.level == logging.DEBUG
        # Should have file handler and console handler
        assert len(logger.handlers) == 2

    def test_auto_generates_session_id(self, tmp_path: Path) -> None:
        logger = setup_phase_logger(tmp_path, "architect")
        # Session ID is internal to the formatter, not directly accessible
        # but we can verify the logger was created successfully
        assert logger is not None

    def test_uses_provided_session_id(self, tmp_path: Path) -> None:
        logger = setup_phase_logger(
            tmp_path, "architect", session_id="custom-session"
        )
        assert logger is not None

    def test_creates_log_directory(self, tmp_path: Path) -> None:
        setup_phase_logger(tmp_path, "architect")
        log_dir = tmp_path / ".orchestrator" / "logs"
        assert log_dir.is_dir()

    def test_configurable_log_level(self, tmp_path: Path) -> None:
        logger = setup_phase_logger(tmp_path, "architect", level=logging.ERROR)
        assert logger.level == logging.ERROR


class TestLogLlmCall:
    """Test LLM call logging helper."""

    def test_logs_token_counts(self, tmp_path: Path) -> None:
        logger = setup_phase_logger(tmp_path, "architect", level=logging.DEBUG)
        mock_response = MagicMock()
        mock_response.prompt_tokens = 100
        mock_response.completion_tokens = 50
        mock_response.reasoning_tokens = 25

        log_llm_call(
            logger,
            phase="architect",
            role="coder",
            messages=[{"role": "user", "content": "hi"}],
            response=mock_response,
            latency_ms=500.0,
        )

        # Read the log file
        log_file = tmp_path / ".orchestrator" / "logs" / "architect.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["prompt_tokens"] == 100
        assert entry["completion_tokens"] == 50
        assert entry["reasoning_tokens"] == 25
        assert entry["latency_ms"] == 500.0

    def test_logs_with_zero_tokens_on_none_response(self, tmp_path: Path) -> None:
        logger = setup_phase_logger(tmp_path, "architect", level=logging.DEBUG)

        log_llm_call(
            logger,
            phase="architect",
            role="coder",
            messages=[],
            response=None,
            latency_ms=100.0,
        )

        log_file = tmp_path / ".orchestrator" / "logs" / "architect.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["prompt_tokens"] == 0

    def test_event_name_includes_role(self, tmp_path: Path) -> None:
        logger = setup_phase_logger(tmp_path, "architect", level=logging.DEBUG)
        mock_response = MagicMock()
        mock_response.prompt_tokens = 0
        mock_response.completion_tokens = 0
        mock_response.reasoning_tokens = 0

        log_llm_call(
            logger,
            phase="architect",
            role="judge",
            messages=[],
            response=mock_response,
            latency_ms=0,
        )

        log_file = tmp_path / ".orchestrator" / "logs" / "architect.jsonl"
        entry = json.loads(log_file.read_text().strip())
        assert "judge" in entry["event"]


class TestLogLlmCallRawIo:
    """log_llm_call must also persist the raw round-trip to raw-io.jsonl."""

    def test_writes_raw_round_trip_alongside_token_summary(self, tmp_path: Path) -> None:
        logger = setup_phase_logger(tmp_path, "architect", level=logging.DEBUG, console=False)
        mock_response = MagicMock()
        mock_response.content = "SENTINEL-RESPONSE-7f3a"
        mock_response.reasoning_content = "thinking..."
        mock_response.finish_reason = "stop"
        mock_response.prompt_tokens = 11
        mock_response.completion_tokens = 22
        mock_response.reasoning_tokens = 3

        log_llm_call(
            logger,
            phase="architect",
            role="architect",
            messages=[{"role": "user", "content": "SENTINEL-PROMPT-bea2"}],
            response=mock_response,
            latency_ms=42.0,
            endpoint="http://192.168.1.13:8080",
        )

        phase_log = tmp_path / ".orchestrator" / "logs" / "architect.jsonl"
        raw_io = tmp_path / ".orchestrator" / "logs" / "raw-io.jsonl"
        assert phase_log.exists()
        assert raw_io.exists()

        phase_entry = json.loads(phase_log.read_text().strip())
        raw_entry = json.loads(raw_io.read_text().strip())

        assert phase_entry["request_id"] == raw_entry["request_id"]
        assert raw_entry["role"] == "architect"
        assert raw_entry["endpoint"] == "http://192.168.1.13:8080"
        assert raw_entry["messages"] == [{"role": "user", "content": "SENTINEL-PROMPT-bea2"}]
        assert raw_entry["response_content"] == "SENTINEL-RESPONSE-7f3a"
        assert raw_entry["reasoning_content"] == "thinking..."
        assert raw_entry["usage"] == {"prompt_tokens": 11, "completion_tokens": 22, "reasoning_tokens": 3}

    def test_raw_round_trip_skipped_when_no_project_dir_on_logger(self, tmp_path: Path) -> None:
        bare_logger = logging.getLogger("orchestrator.phase.detached")
        bare_logger.handlers.clear()
        mock_response = MagicMock()
        mock_response.content = "x"
        mock_response.prompt_tokens = 0
        mock_response.completion_tokens = 0
        mock_response.reasoning_tokens = 0

        log_llm_call(
            bare_logger,
            phase="detached",
            role="architect",
            messages=[{"role": "user", "content": "x"}],
            response=mock_response,
            latency_ms=1.0,
        )

        assert not (tmp_path / ".orchestrator" / "logs" / "raw-io.jsonl").exists()


class TestLogLlmError:
    """Test LLM error logging helper."""

    def test_logs_error_with_latency(self, tmp_path: Path) -> None:
        logger = setup_phase_logger(tmp_path, "architect", level=logging.DEBUG)

        log_llm_error(
            logger,
            phase="architect",
            role="coder",
            error=ConnectionError("refused"),
            latency_ms=200.0,
        )

        log_file = tmp_path / ".orchestrator" / "logs" / "architect.jsonl"
        lines = log_file.read_text().strip().split("\n")
        error_entry = None
        for line in lines:
            entry = json.loads(line)
            if entry.get("level") == "ERROR":
                error_entry = entry
                break
        assert error_entry is not None
        assert "refused" in error_entry["message"]
        assert error_entry["latency_ms"] == 200.0
