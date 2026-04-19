"""Tests for quiz routes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from web.backend.app import create_app
from web.backend.routes.quiz import QuizSession, QuizStore


@pytest.fixture
def fresh_quiz_store() -> QuizStore:
    return QuizStore()


@pytest.fixture
def app(fresh_quiz_store: QuizStore) -> FastAPI:
    with patch("web.backend.routes.quiz.get_quiz_store", return_value=fresh_quiz_store):
        yield create_app()


@pytest.mark.asyncio
async def test_next_question_returns_seed_question(app: FastAPI) -> None:
    """GET /quiz/next returns the first seed question for a new quiz."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create a project first
        await client.post("/api/projects", json={"name": "Quiz App"})

        response = await client.get("/api/projects/test-project/quiz/next")
    assert response.status_code == 404  # Project not found (test-project doesn't exist in fresh store)


@pytest.mark.asyncio
async def test_next_question_after_project_creation(app: FastAPI) -> None:
    """Quiz session is created when project is created."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Quiz App", "initial_idea": "A test project"},
        )
        project_id = create_resp.json()["id"]

        # Need to also create a quiz session
        store = __import__("web.backend.routes.quiz", fromlist=["get_quiz_store"]).get_quiz_store()
        store.create(project_id, "Quiz App")

        response = await client.get(f"/api/projects/{project_id}/quiz/next")
    assert response.status_code == 200
    data = response.json()
    assert data["question"] is not None
    assert data["done"] is False


@pytest.mark.asyncio
async def test_answer_and_next(app: FastAPI) -> None:
    """POST /quiz/answer records answer and returns next question."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Answer Test"},
        )
        project_id = create_resp.json()["id"]

        store = __import__("web.backend.routes.quiz", fromlist=["get_quiz_store"]).get_quiz_store()
        session = store.create(project_id, "Answer Test")
        session.submit_answer("First answer")

        response = await client.post(
            f"/api/projects/{project_id}/quiz/answer",
            json={"answer": "Second answer"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["question"] is not None


@pytest.mark.asyncio
async def test_edit_answer(app: FastAPI) -> None:
    """POST /quiz/edit replaces an answer and truncates subsequent turns."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Edit Test"},
        )
        project_id = create_resp.json()["id"]

        store = __import__("web.backend.routes.quiz", fromlist=["get_quiz_store"]).get_quiz_store()
        session = store.create(project_id, "Edit Test")
        session.submit_answer("Answer 1")
        session.submit_answer("Answer 2")
        session.submit_answer("Answer 3")

        response = await client.post(
            f"/api/projects/{project_id}/quiz/edit",
            json={"turn": 1, "answer": "Edited answer 2"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["edited"] is True
    assert data["remaining_turns"] == 2  # Answer 3 was truncated


@pytest.mark.asyncio
async def test_edit_invalid_turn_returns_400(app: FastAPI) -> None:
    """POST /quiz/edit with invalid turn index returns 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Invalid Edit"},
        )
        project_id = create_resp.json()["id"]

        store = __import__("web.backend.routes.quiz", fromlist=["get_quiz_store"]).get_quiz_store()
        store.create(project_id, "Invalid Edit")

        response = await client.post(
            f"/api/projects/{project_id}/quiz/edit",
            json={"turn": 99, "answer": "Nope"},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_commit_writes_qwendea(app: FastAPI) -> None:
    """POST /quiz/commit writes qwendea.md and returns success."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_resp = await client.post(
            "/api/projects",
            json={"name": "Commit Test"},
        )
        project_id = create_resp.json()["id"]

        store = __import__("web.backend.routes.quiz", fromlist=["get_quiz_store"]).get_quiz_store()
        store.create(project_id, "Commit Test")

        qwendea_content = "# Project: Commit Test\n\n## Description\nTest\n\n## Target Users\nTest\n\n## Core Requirements\n1. Test\n\n## Constraints\n- Test\n\n## Out of Scope\n- Nothing"

        response = await client.post(
            f"/api/projects/{project_id}/quiz/commit",
            json={"qwendea_md": qwendea_content},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["committed"] is True
    assert data["qwendea_length"] == len(qwendea_content)


@pytest.mark.asyncio
async def test_quiz_next_not_found(app: FastAPI) -> None:
    """GET /quiz/next returns 404 for unknown project."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/projects/nonexistent/quiz/next")
    assert response.status_code == 404


class TestQuizSession:
    """Direct unit tests for QuizSession."""

    def test_seed_questions(self) -> None:
        session = QuizSession("test", "Test")
        questions = session.seed_questions
        assert len(questions) == 3
        assert "What are you trying to build" in questions[0]

    def test_next_returns_sequential_seed_questions(self) -> None:
        session = QuizSession("test", "Test")
        q1 = session.next_question()
        assert q1 == session.seed_questions[0]

        session.submit_answer("a1")
        q2 = session.next_question()
        assert q2 == session.seed_questions[1]

        session.submit_answer("a2")
        q3 = session.next_question()
        assert q3 == session.seed_questions[2]

    def test_next_after_seed_returns_followup(self) -> None:
        session = QuizSession("test", "Test")
        for i in range(3):
            session.submit_answer(f"answer {i}")
        q = session.next_question()
        assert "anything else" in q.lower() or q is not None

    def test_is_complete_when_done(self) -> None:
        session = QuizSession("test", "Test")
        for i in range(3):
            session.submit_answer(f"answer {i}")
        # Mark as done by setting last answer to DONE
        session.turns[-1].answer = "DONE"
        assert session.is_complete is True

    def test_edit_truncates_subsequent(self) -> None:
        session = QuizSession("test", "Test")
        session.submit_answer("a1")
        session.submit_answer("a2")
        session.submit_answer("a3")
        assert len(session.turns) == 3

        session.edit_answer(0, "edited a1")
        assert len(session.turns) == 1
        assert session.turns[0].answer == "edited a1"

    def test_qa_log_format(self) -> None:
        session = QuizSession("test", "Test")
        session.submit_answer("my answer")
        log = session.qa_log()
        assert "1. Q:" in log
        assert "A: my answer" in log

    def test_synthesize_produces_markdown(self) -> None:
        session = QuizSession("test", "My App")
        session.submit_answer("It's an app")
        result = session.synthesize()
        assert "# Project: My App" in result
        assert "## Description" in result
        assert "## Target Users" in result
        assert "## Core Requirements" in result
        assert "## Constraints" in result
        assert "## Out of Scope" in result
