"""Tests for _ensure_qwendea() entry point and QuizSession."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.ingestion.ensure import (
    InvalidQwendea,
    QuizSession,
    _check_missing_headers,
    _ensure_qwendea,
    complete_quiz,
)
from orchestrator.ingestion.quiz import REQUIRED_HEADERS, SynthesisError


def _make_engine(**kwargs):
    """Create a QuizEngine with a mocked LLM."""
    from orchestrator.ingestion.quiz import QuizEngine

    llm = MagicMock()
    valid_qwendea = (
        "# Project: Test\n\n"
        "## Description\ntest\n\n"
        "## Target Users\nusers\n\n"
        "## Core Requirements\n1. req\n\n"
        "## Constraints\n- c\n\n"
        "## Out of Scope\n- o\n"
    )
    r = MagicMock()
    r.content = valid_qwendea
    llm.chat.return_value = r

    config = MagicMock()
    config.quiz_max_turns = 10

    engine = QuizEngine(llm, config)
    # Pre-set qa pairs if provided
    for qa in kwargs.get("qa_pairs", []):
        engine.qa.append(qa)
    return engine, llm, config


def _make_valid_qwendea() -> str:
    return (
        "# Project: Test\n\n"
        "## Description\ntest\n\n"
        "## Target Users\nusers\n\n"
        "## Core Requirements\n1. req\n\n"
        "## Constraints\n- c\n\n"
        "## Out of Scope\n- o\n"
    )


class TestEnsureQwendeaExists:
    """If qwendea.md exists: read, validate structure, return content."""

    def test_returns_content_when_valid(self, tmp_path: Path):
        qwendea_path = tmp_path / "qwendea.md"
        qwendea_path.write_text(_make_valid_qwendea(), encoding="utf-8")

        llm = MagicMock()
        config = MagicMock()
        config.quiz_max_turns = 10

        result = _ensure_qwendea(tmp_path, llm, config)

        assert result == _make_valid_qwendea()
        # LLM should NOT be called
        llm.chat.assert_not_called()

    def test_returns_content_with_extra_content(self, tmp_path: Path):
        """Existing qwendea.md with extra content beyond required headers."""
        content = (
            "# Project: My App\n\n"
            "## Description\nA test app.\n\n"
            "## Target Users\nDevelopers.\n\n"
            "## Core Requirements\n1. Must work\n\n"
            "## Constraints\n- Python 3.12\n\n"
            "## Out of Scope\n- Mobile\n\n"
            "# Notes\nExtra content is fine.\n"
        )
        qwendea_path = tmp_path / "qwendea.md"
        qwendea_path.write_text(content, encoding="utf-8")

        llm = MagicMock()
        config = MagicMock()
        config.quiz_max_turns = 10

        result = _ensure_qwendea(tmp_path, llm, config)

        assert result == content


class TestEnsureQwendeaMissing:
    """If missing: expose a QuizSession object the PWA can drive."""

    def test_returns_quiz_session_when_missing(self, tmp_path: Path):
        llm = MagicMock()
        config = MagicMock()
        config.quiz_max_turns = 10

        result = _ensure_qwendea(tmp_path, llm, config)

        assert isinstance(result, QuizSession)
        from orchestrator.ingestion.quiz import QuizEngine

        assert isinstance(result.engine, QuizEngine)

    def test_quiz_session_has_required_attributes(self, tmp_path: Path):
        llm = MagicMock()
        config = MagicMock()
        config.quiz_max_turns = 10

        session = _ensure_qwendea(tmp_path, llm, config)

        assert hasattr(session, "next_question")
        assert hasattr(session, "submit_answer")
        assert hasattr(session, "is_complete")
        assert hasattr(session, "synthesize")
        assert hasattr(session, "qa_log")


class TestEnsureQwendeaInvalid:
    """Existing qwendea.md with missing headers → raise InvalidQwendea."""

    def test_raises_with_missing_headers(self, tmp_path: Path):
        content = (
            "# Project: Test\n\n"
            "## Description\ntest\n\n"
            "## Core Requirements\n1. req\n\n"
            "## Constraints\n- c\n\n"
            "## Out of Scope\n- o\n"
        )
        # Missing: ## Target Users
        qwendea_path = tmp_path / "qwendea.md"
        qwendea_path.write_text(content, encoding="utf-8")

        llm = MagicMock()
        config = MagicMock()
        config.quiz_max_turns = 10

        with pytest.raises(InvalidQwendea) as exc_info:
            _ensure_qwendea(tmp_path, llm, config)

        assert exc_info.value.missing_headers == ["## Target Users"]
        assert "## Target Users" in str(exc_info.value)

    def test_raises_with_multiple_missing_headers(self, tmp_path: Path):
        content = "# Project: Test\n\n## Description\ntest\n"
        qwendea_path = tmp_path / "qwendea.md"
        qwendea_path.write_text(content, encoding="utf-8")

        llm = MagicMock()
        config = MagicMock()
        config.quiz_max_turns = 10

        with pytest.raises(InvalidQwendea) as exc_info:
            _ensure_qwendea(tmp_path, llm, config)

        missing = exc_info.value.missing_headers
        assert "## Target Users" in missing
        assert "## Core Requirements" in missing
        assert "## Constraints" in missing
        assert "## Out of Scope" in missing

    def test_error_message_lists_missing_headers(self, tmp_path: Path):
        content = "# Project: Test\n\n"
        qwendea_path = tmp_path / "qwendea.md"
        qwendea_path.write_text(content, encoding="utf-8")

        llm = MagicMock()
        config = MagicMock()
        config.quiz_max_turns = 10

        with pytest.raises(InvalidQwendea) as exc_info:
            _ensure_qwendea(tmp_path, llm, config)

        for header in REQUIRED_HEADERS:
            if header != "# Project:":
                assert header in str(exc_info.value)


class TestCompleteQuiz:
    """On PWA session completion, write qwendea.md to project_dir."""

    def test_writes_qwendea_to_project_dir(self, tmp_path: Path):
        engine, llm, config = _make_engine()
        session = QuizSession(engine)

        result = complete_quiz(session, tmp_path)

        qwendea_path = tmp_path / "qwendea.md"
        assert qwendea_path.exists()
        assert qwendea_path.read_text(encoding="utf-8") == result

    def test_returns_synthesized_content(self, tmp_path: Path):
        expected = (
            "# Project: Test\n\n"
            "## Description\ntest\n\n"
            "## Target Users\nusers\n\n"
            "## Core Requirements\n1. req\n\n"
            "## Constraints\n- c\n\n"
            "## Out of Scope\n- o\n"
        )
        llm = MagicMock()
        r = MagicMock()
        r.content = expected
        llm.chat.return_value = r
        config = MagicMock()
        config.quiz_max_turns = 10

        engine, _, _ = _make_engine()
        engine.llm = llm
        session = QuizSession(engine)

        result = complete_quiz(session, tmp_path)

        assert result.strip() == expected.strip()

    def test_raises_synthesis_error_on_failure(self, tmp_path: Path):
        engine, llm, config = _make_engine()
        # Make synthesize raise
        engine.synthesize = MagicMock(side_effect=SynthesisError("fail", ""))
        session = QuizSession(engine)

        with pytest.raises(SynthesisError):
            complete_quiz(session, tmp_path)


class TestQuizSessionAPI:
    """QuizSession correctly delegates to the underlying engine."""

    def test_next_question_delegates(self):
        engine, _, _ = _make_engine()
        engine.qa = []  # ensure no qa pairs
        session = QuizSession(engine)

        # First call should return a seed question
        q = session.next_question
        assert q is not None
        assert "build" in q.lower() or "What" in q

    def test_submit_answer_records(self):
        engine, _, _ = _make_engine()
        engine.qa = []
        session = QuizSession(engine)

        session.next_question  # advance past empty
        session.submit_answer("my answer")

        assert len(engine.qa) == 1
        assert engine.qa[0].answer == "my answer"

    def test_is_complete_delegates(self):
        engine, _, config = _make_engine()
        config.quiz_max_turns = 3  # only seed questions
        session = QuizSession(engine)

        # After 3 seed questions, should be complete
        for _ in range(3):
            session.next_question
            session.submit_answer("answer")

        assert session.is_complete is True


class TestCheckMissingHeaders:
    """_check_missing_headers returns correct list."""

    def test_no_missing_headers(self):
        content = "\n".join(REQUIRED_HEADERS) + "\n"
        assert _check_missing_headers(content) == []

    def test_all_missing(self):
        assert _check_missing_headers("") == REQUIRED_HEADERS

    def test_one_missing(self):
        # Content that has all headers except "# Project:"
        content = "\n".join(REQUIRED_HEADERS[1:]) + "\n"
        missing = _check_missing_headers(content)
        assert missing == ["# Project:"]

    def test_case_sensitive(self):
        """Header matching is case-sensitive."""
        content = "# project: test\n\n" + "\n".join(REQUIRED_HEADERS[1:]) + "\n"
        missing = _check_missing_headers(content)
        assert "# Project:" in missing


class TestEndToEnd:
    """End-to-end test with a scripted answer sequence."""

    def test_full_quiz_flow(self, tmp_path: Path):
        """Scripted answers → synthesis → qwendea.md written."""
        from orchestrator.ingestion.quiz import QuizEngine

        valid_qwendea = (
            "# Project: Todo App\n\n"
            "## Description\nA simple todo application.\n\n"
            "## Target Users\nIndividual users.\n\n"
            "## Core Requirements\n"
            "1. Users can add tasks\n"
            "2. Users can mark tasks complete\n"
            "3. Users can delete tasks\n\n"
            "## Constraints\n"
            "- Python 3.12+\n"
            "- SQLite backend\n\n"
            "## Out of Scope\n"
            "- Mobile app\n"
            "- Cloud sync\n"
        )

        llm = MagicMock()
        # Turn 1: adaptive question after 3 seed questions
        adaptive_q = MagicMock()
        adaptive_q.content = "What about deployment?"
        # Turn 2: DONE (max turns reached at 5)
        done = MagicMock()
        done.content = "DONE"
        # Turn 3: synthesis
        synth = MagicMock()
        synth.content = valid_qwendea

        llm.chat.side_effect = [adaptive_q, done, synth]

        config = MagicMock()
        config.quiz_max_turns = 5

        engine = QuizEngine(llm, config)
        session = QuizSession(engine)

        # Seed questions (turns 1-3)
        q1 = session.next_question
        assert q1 is not None
        session.submit_answer("I want to build a todo app")

        q2 = session.next_question
        assert q2 is not None
        session.submit_answer("Individual users who need task management")

        q3 = session.next_question
        assert q3 is not None
        session.submit_answer("Add tasks, mark complete, delete tasks")

        # Adaptive question (turn 4) - LLM returns "What about deployment?"
        q4 = session.next_question
        assert q4 is not None
        assert "deployment" in q4.lower()
        session.submit_answer("Budget: minimal, just SQLite")

        # Turn 5: qa=4, 4<5 → adaptive, LLM returns "DONE" → None
        assert session.next_question is None

        # Synthesize and write (3rd LLM call)
        result = complete_quiz(session, tmp_path)

        assert result.strip() == valid_qwendea.strip()
        assert (tmp_path / "qwendea.md").exists()
        assert (tmp_path / "qwendea.md").read_text(encoding="utf-8").strip() == valid_qwendea.strip()
