"""Quiz engine for requirements gathering via interactive Q&A."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from orchestrator.lib.config import Config
from orchestrator.lib.llm import LLMClient

logger = logging.getLogger(__name__)

REQUIRED_HEADERS = [
    "# Project:",
    "## Description",
    "## Target Users",
    "## Core Requirements",
    "## Constraints",
    "## Out of Scope",
]

_SEED_QUESTIONS = [
    "What are you trying to build? Describe it in your own words.",
    "Who is this for? What problem does it solve?",
    "What are the top 3 features that MUST work for this to succeed?",
]

_ADAPTIVE_PROMPT = (
    "You are helping gather software requirements. Below is the Q&A collected "
    "so far. Based on it, either:\n\n"
    "(a) Output EXACTLY the next question to ask the user, on one line, with "
    "no preamble, no quotes, no explanation. The question should probe "
    "the weakest area (most ambiguity, biggest unknown).\n\n"
    "(b) If the answers are sufficient to write a clear requirements document "
    "covering description, users, core requirements, constraints, and "
    "out-of-scope, output EXACTLY: DONE\n\n"
    "Q&A so far:\n"
    "{qa_log}"
)

_SYNTHESIZE_PROMPT = (
    "You are a requirements analyst. Produce a clean qwendea.md from the "
    "following Q&A.\n\n"
    "{qa_log}\n\n"
    "Produce ONLY the markdown file content, with this EXACT structure:\n\n"
    "# Project: <Name>\n\n"
    "## Description\n"
    "...\n\n"
    "## Target Users\n"
    "...\n\n"
    "## Core Requirements\n"
    "1. ...\n\n"
    "## Constraints\n"
    "- ...\n\n"
    "## Out of Scope\n"
    "- ...\n\n"
    "Rules:\n"
    "- Every core requirement must be specific and testable\n"
    '- Avoid vague language ("user-friendly", "fast", "robust") — if you use '
    "it, give a measurable threshold\n"
    "- If information is missing for a section, write \"TBD\" — do NOT invent"
)

_SYNTHESIZE_RETRY_PROMPT = (
    "Your previous output was missing required section headers. "
    "The following headers MUST appear in your output:\n\n"
    "{missing}\n\n"
    "Here is the Q&A again:\n\n"
    "{qa_log}\n\n"
    "Produce ONLY the markdown file content with ALL the above headers present."
)


@dataclass
class QAPair:
    question: str
    answer: str


class QuizEngine:
    """Drives an interactive Q&A quiz to gather requirements.

    Uses seed questions for the first three turns, then calls the LLM
    for adaptive follow-ups. Synthesises the Q&A log into a qwendea.md.
    """

    def __init__(self, llm: LLMClient, config: Config) -> None:
        self.llm = llm
        self.config = config
        self.qa: list[QAPair] = []
        self._qwendea: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def seed_questions(self) -> list[str]:
        """Return the static seed questions (always asked first)."""
        return list(_SEED_QUESTIONS)

    def next_question(self) -> str | None:
        """Return the next question to ask, or None if the quiz is done."""
        # Seed questions first
        if len(self.qa) < len(_SEED_QUESTIONS):
            return _SEED_QUESTIONS[len(self.qa)]

        # Hard cap on turns
        if len(self.qa) >= self.config.quiz_max_turns:
            return None

        return self._adaptive_next()

    def record_answer(self, answer: str) -> None:
        """Record the user's answer to the most recently asked question."""
        question_idx = len(self.qa)
        if question_idx < len(_SEED_QUESTIONS):
            question = _SEED_QUESTIONS[question_idx]
        else:
            # The question was returned by _adaptive_next but not stored;
            # we need to have asked it. In practice the caller (PWA) knows
            # what was displayed. For the adaptive case we store a placeholder
            # since the adaptive question text is ephemeral.
            question = f"Adaptive question (turn {question_idx + 1})"

        self.qa.append(QAPair(question=question, answer=answer))

    @property
    def qa_log(self) -> str:
        """Numbered Q&A log suitable for LLM prompts."""
        lines: list[str] = []
        for i, pair in enumerate(self.qa, start=1):
            lines.append(f"{i}. Q: {pair.question}")
            lines.append(f"   A: {pair.answer}")
        return "\n".join(lines)

    @property
    def is_complete(self) -> bool:
        """True when the quiz has ended (no more questions)."""
        return self.next_question() is None

    def synthesize(self) -> str:
        """Call the LLM to produce qwendea.md from the Q&A log.

        Strips code fences, validates required headers, and retries once
        on failure. Raises SynthesisError on second failure.
        """
        qa_log = self.qa_log
        content = self._call_llm_synthesize(qa_log)
        return self._validate_and_fix(content, qa_log)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _adaptive_next(self) -> str | None:
        """Ask LLM for the next question OR return 'DONE' sentinel."""
        qa_log = self.qa_log
        prompt = _ADAPTIVE_PROMPT.format(qa_log=qa_log)
        messages = [{"role": "user", "content": prompt}]

        try:
            resp = self.llm.chat(messages, max_tokens=512, temperature=0.7)
        except Exception as exc:
            logger.error("Adaptive question failed: %s", exc)
            return None

        answer = resp.content.strip()
        if answer == "DONE":
            return None

        return answer

    def _call_llm_synthesize(self, qa_log: str) -> str:
        """Send the synthesis prompt to the LLM."""
        prompt = _SYNTHESIZE_PROMPT.format(qa_log=qa_log)
        messages = [{"role": "user", "content": prompt}]
        resp = self.llm.chat(messages, max_tokens=8192, temperature=0.3)
        return resp.content

    def _validate_and_fix(self, content: str, qa_log: str) -> str:
        """Strip code fences, validate headers, retry once on failure."""
        content = self._strip_code_fences(content)

        missing = self._check_missing_headers(content)
        if not missing:
            return content

        logger.warning(
            "Synthesis missing headers %s, retrying once", missing
        )
        retry_prompt = _SYNTHESIZE_RETRY_PROMPT.format(
            missing="\n".join(f"- {h}" for h in missing),
            qa_log=qa_log,
        )
        messages = [{"role": "user", "content": retry_prompt}]
        try:
            resp = self.llm.chat(messages, max_tokens=8192, temperature=0.3)
        except Exception as exc:
            logger.error("Synthesis retry failed: %s", exc)
            raise SynthesisError(
                "Synthesis failed after retry: LLM error", content
            ) from exc

        content = self._strip_code_fences(resp.content)
        missing = self._check_missing_headers(content)
        if missing:
            raise SynthesisError(
                f"Synthesis still missing headers after retry: {missing}",
                content,
            )
        return content

    @staticmethod
    def _strip_code_fences(content: str) -> str:
        """Remove markdown code fences wrapping the output."""
        content = content.strip()
        # Match optional language tag: ```markdown or ```
        fence = re.match(r"^```(\w*)\s*\n(.*?)\n```?\s*$", content, re.DOTALL)
        if fence:
            return fence.group(2).strip()
        return content

    @staticmethod
    def _check_missing_headers(content: str) -> list[str]:
        """Return list of required headers not found in content."""
        return [h for h in REQUIRED_HEADERS if h not in content]


class SynthesisError(Exception):
    """Raised when qwendea.md synthesis fails."""

    def __init__(self, message: str, bad_output: str) -> None:
        self.bad_output = bad_output
        super().__init__(message)
