"""Entry point for ensuring qwendea.md exists for a project."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from orchestrator.ingestion.quiz import (
    QuizEngine,
    REQUIRED_HEADERS,
    SynthesisError,
)
from orchestrator.lib.config import Config
from orchestrator.lib.llm import LLMClient

logger = logging.getLogger(__name__)


class InvalidQwendea(Exception):
    """Raised when an existing qwendea.md is missing required headers."""

    def __init__(self, message: str, missing_headers: list[str]) -> None:
        self.missing_headers = missing_headers
        super().__init__(message)


@dataclass
class QuizSession:
    """A session for driving the quiz from the PWA.

    The PWA can:
    - Get the next question via ``next_question``
    - Submit answers via ``submit_answer``
    - Check if the quiz is complete via ``is_complete``
    - Trigger synthesis via ``synthesize``
    """

    engine: QuizEngine

    @property
    def next_question(self) -> str | None:
        """Return the next question to ask, or None if the quiz is done."""
        return self.engine.next_question()

    def submit_answer(self, answer: str) -> None:
        """Record the user's answer to the current question."""
        self.engine.record_answer(answer)

    @property
    def is_complete(self) -> bool:
        """True when the quiz has ended (no more questions)."""
        return self.engine.is_complete

    def synthesize(self) -> str:
        """Call the LLM to produce qwendea.md from the Q&A log."""
        return self.engine.synthesize()

    @property
    def qa_log(self) -> str:
        """Numbered Q&A log suitable for display."""
        return self.engine.qa_log


def _ensure_qwendea(
    project_dir: Path, llm: LLMClient, config: Config
) -> str | QuizSession:
    """Ensure qwendea.md exists for the given project directory.

    If ``qwendea.md`` already exists, validate its structure and return
    its content.  If it does not exist, return a :class:`QuizSession`
    that the PWA can drive to collect requirements.

    Returns:
        ``str`` if qwendea.md exists and is valid, or
        :class:`QuizSession` if qwendea.md needs to be created.

    Raises:
        InvalidQwendea: if existing qwendea.md is missing required headers.
    """
    qwendea_path = project_dir / "qwendea.md"

    if qwendea_path.exists():
        content = qwendea_path.read_text(encoding="utf-8")
        missing = _check_missing_headers(content)
        if missing:
            raise InvalidQwendea(
                f"qwendea.md is missing required headers: {missing}",
                missing,
            )
        return content

    engine = QuizEngine(llm, config)
    return QuizSession(engine)


def complete_quiz(session: QuizSession, project_dir: Path) -> str:
    """Complete a quiz session and write qwendea.md to *project_dir*.

    Calls ``session.synthesize()`` to produce the qwendea.md content,
    then writes it to ``project_dir/qwendea.md``.

    Returns:
        The synthesized qwendea.md content.

    Raises:
        SynthesisError: if synthesis fails.
    """
    content = session.synthesize()
    qwendea_path = project_dir / "qwendea.md"
    qwendea_path.write_text(content, encoding="utf-8")
    return content


def _check_missing_headers(content: str) -> list[str]:
    """Return list of required headers not found in *content*."""
    return [h for h in REQUIRED_HEADERS if h not in content]
