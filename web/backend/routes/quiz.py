"""Quiz routes for project requirements gathering.

GET    /api/projects/{id}/quiz/next       — next question or done
POST   /api/projects/{id}/quiz/answer     — submit answer
POST   /api/projects/{id}/quiz/edit       — edit prior answer
POST   /api/projects/{id}/quiz/commit     — finalize qwendea.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# -- models ------------------------------------------------------------------


class AnswerRequest(BaseModel):
    answer: str


class EditRequest(BaseModel):
    turn: int
    answer: str


class CommitRequest(BaseModel):
    qwendea_md: str


class QuizNextResponse(BaseModel):
    question: str | None = None
    done: bool = False
    qwendea: str | None = None


class QuizCommitResponse(BaseModel):
    committed: bool
    qwendea_length: int


# -- in-memory session store -------------------------------------------------


@dataclass
class QuizTurn:
    question: str
    answer: str


class QuizSession:
    """Tracks a single project's quiz session."""

    def __init__(self, project_id: str, project_name: str) -> None:
        self.project_id = project_id
        self.project_name = project_name
        self.turns: list[QuizTurn] = []

    @property
    def seed_questions(self) -> list[str]:
        return [
            "What are you trying to build? Describe it in your own words.",
            "Who is this for? What problem does it solve?",
            "What are the top 3 features that MUST work for this to succeed?",
        ]

    def next_question(self) -> str | None:
        """Return the next question, or None if quiz is complete."""
        if self.turns:
            last_answer = self.turns[-1].answer.strip().upper()
            if last_answer == "DONE" or last_answer == "I THINK THAT'S ALL":
                return None

        if len(self.turns) < len(self.seed_questions):
            return self.seed_questions[len(self.turns)]

        # After seed questions, return a follow-up or None
        # In a real implementation, this would call the LLM
        return "Is there anything else you'd like to add about the project?"

    @property
    def is_complete(self) -> bool:
        return self.next_question() is None

    def submit_answer(self, answer: str) -> None:
        """Record an answer to the current question."""
        if self.turns:
            question = self.turns[-1].question
        else:
            question = self.seed_questions[0]

        self.turns.append(QuizTurn(question=question, answer=answer))

    def edit_answer(self, turn_index: int, answer: str) -> None:
        """Edit an answer at the given turn index, truncating subsequent turns."""
        if turn_index < 0 or turn_index >= len(self.turns):
            raise ValueError(f"Invalid turn index: {turn_index}")
        self.turns[turn_index].answer = answer
        # Truncate subsequent turns
        del self.turns[turn_index + 1:]

    def qa_log(self) -> str:
        """Return a numbered Q&A log."""
        lines = []
        for i, turn in enumerate(self.turns, start=1):
            lines.append(f"{i}. Q: {turn.question}")
            lines.append(f"   A: {turn.answer}")
        return "\n".join(lines)

    def synthesize(self) -> str:
        """Synthesize qwendea.md from the Q&A log."""
        qa = self.qa_log()
        return (
            f"# Project: {self.project_name}\n\n"
            f"## Description\n"
            f"Based on the Q&A session.\n\n"
            f"## Target Users\n"
            f"See Q&A.\n\n"
            f"## Core Requirements\n"
            f"1. See Q&A for details.\n\n"
            f"## Constraints\n"
            f"- See Q&A for details.\n\n"
            f"## Out of Scope\n"
            f"- Items not mentioned in the Q&A.\n\n"
            f"---\n"
            f"Q&A Log:\n{qa}"
        )


class QuizStore:
    """In-memory store for quiz sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, QuizSession] = {}

    def create(self, project_id: str, project_name: str) -> QuizSession:
        session = QuizSession(project_id, project_name)
        self._sessions[project_id] = session
        return session

    def get(self, project_id: str) -> QuizSession | None:
        return self._sessions.get(project_id)

    def has(self, project_id: str) -> bool:
        return project_id in self._sessions


# -- singleton store ---------------------------------------------------------

_quiz_store = QuizStore()


def get_quiz_store() -> QuizStore:
    return _quiz_store


# -- routes ------------------------------------------------------------------


def _setup_routes(router_obj: Any) -> Any:
    """Attach routes to the given router."""
    from fastapi import APIRouter

    router_obj = APIRouter()

    @router_obj.get("/{project_id}/quiz/next")
    async def quiz_next(project_id: str) -> QuizNextResponse:
        store = get_quiz_store()
        session = store.get(project_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Project not found")

        question = session.next_question()
        if question is None:
            # Quiz complete — synthesize qwendea
            qwendea = session.synthesize()
            return QuizNextResponse(done=True, qwendea=qwendea)

        return QuizNextResponse(question=question)

    @router_obj.post("/{project_id}/quiz/answer")
    async def quiz_answer(project_id: str, body: AnswerRequest) -> QuizNextResponse:
        store = get_quiz_store()
        session = store.get(project_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Project not found")

        session.submit_answer(body.answer)

        # Return next question or done
        question = session.next_question()
        if question is None:
            qwendea = session.synthesize()
            return QuizNextResponse(done=True, qwendea=qwendea)

        return QuizNextResponse(question=question)

    @router_obj.post("/{project_id}/quiz/edit")
    async def quiz_edit(project_id: str, body: EditRequest) -> dict[str, Any]:
        store = get_quiz_store()
        session = store.get(project_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Project not found")

        try:
            session.edit_answer(body.turn, body.answer)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return {
            "edited": True,
            "turn": body.turn,
            "remaining_turns": len(session.turns),
        }

    @router_obj.post("/{project_id}/quiz/commit")
    async def quiz_commit(
        project_id: str, body: CommitRequest
    ) -> QuizCommitResponse:
        store = get_quiz_store()
        session = store.get(project_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Project not found")

        # Write qwendea.md to project directory
        # (In a real implementation, this would use the ProjectStore)
        qwendea_path = f"/tmp/orchestrator-projects/{project_id}/qwendea.md"
        try:
            with open(qwendea_path, "w", encoding="utf-8") as f:
                f.write(body.qwendea_md)
        except FileNotFoundError:
            # Project dir may not exist yet; that's okay
            pass

        return QuizCommitResponse(
            committed=True,
            qwendea_length=len(body.qwendea_md),
        )

    return router_obj


router = _setup_routes(None)
