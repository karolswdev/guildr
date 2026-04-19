"""Tests for QuizEngine seed + adaptive loop."""

from unittest.mock import MagicMock, patch

import pytest

from orchestrator.ingestion.quiz import QuizEngine, SynthesisError


def _make_llm(dones_at: int | None = None, adaptive_responses: list[str] | None = None):
    """Create a mock LLMClient for quiz testing."""
    llm = MagicMock()
    responses = []

    if adaptive_responses:
        for text in adaptive_responses:
            r = MagicMock()
            r.content = text
            responses.append(r)

    # If dones_at is set, the LLM returns adaptive questions until turn dones_at
    # then returns "DONE"
    if dones_at is not None and not adaptive_responses:
        for i in range(20):
            r = MagicMock()
            if i < dones_at:
                r.content = f"Adaptive question {i + 1}"
            else:
                r.content = "DONE"
            responses.append(r)

    if not responses:
        r = MagicMock()
        r.content = "DONE"
        responses.append(r)

    llm.chat.return_value = responses[0]
    llm.chat.side_effect = responses

    return llm


def _make_config(max_turns=10):
    """Create a minimal Config mock."""
    config = MagicMock()
    config.quiz_max_turns = max_turns
    return config


class TestSeedQuestions:
    """Seed questions are returned in order for the first 3 turns."""

    def test_returns_three_seed_questions(self, tmp_path):
        llm = _make_llm()
        config = _make_config()
        engine = QuizEngine(llm, config)

        questions = engine.seed_questions()
        assert len(questions) == 3

    def test_first_question(self, tmp_path):
        llm = _make_llm()
        config = _make_config()
        engine = QuizEngine(llm, config)

        assert engine.next_question() == (
            "What are you trying to build? Describe it in your own words."
        )

    def test_second_question(self, tmp_path):
        llm = _make_llm()
        config = _make_config()
        engine = QuizEngine(llm, config)

        engine.next_question()  # first
        engine.record_answer("some answer")

        assert engine.next_question() == (
            "Who is this for? What problem does it solve?"
        )

    def test_third_question(self, tmp_path):
        llm = _make_llm()
        config = _make_config()
        engine = QuizEngine(llm, config)

        engine.next_question()
        engine.record_answer("a1")
        engine.next_question()
        engine.record_answer("a2")

        assert engine.next_question() == (
            "What are the top 3 features that MUST work for this to succeed?"
        )


class TestAdaptiveLoop:
    """Adaptive questions from turn 4, stops on DONE or max turns."""

    def test_stops_on_done(self, tmp_path):
        """Mock LLM returning DONE after 5 turns → quiz stops at turn 5."""
        llm = _make_llm(dones_at=2)  # adaptive Q1, adaptive Q2, then DONE
        config = _make_config(max_turns=10)
        engine = QuizEngine(llm, config)

        # Turns 1-3: seed questions
        for i in range(3):
            q = engine.next_question()
            assert q is not None, f"Expected question at turn {i + 1}"
            engine.record_answer(f"answer {i + 1}")

        # Turn 4: first adaptive question
        q = engine.next_question()
        assert q is not None
        assert "Adaptive question 1" in q
        engine.record_answer("adaptive answer 1")

        # Turn 5: second adaptive question
        q = engine.next_question()
        assert q is not None
        assert "Adaptive question 2" in q
        engine.record_answer("adaptive answer 2")

        # Turn 6: DONE → None
        assert engine.next_question() is None

    def test_stops_at_max_turns(self, tmp_path):
        """Quiz stops when quiz_max_turns is reached."""
        llm = _make_llm(dones_at=3)  # 3 adaptive questions then DONE
        config = _make_config(max_turns=5)
        engine = QuizEngine(llm, config)

        # Turns 1-3: seed (3 turns)
        for i in range(3):
            q = engine.next_question()
            assert q is not None
            engine.record_answer(f"answer {i + 1}")

        # Turn 4: adaptive (qa=3, 3<5 → adaptive)
        q = engine.next_question()
        assert q is not None
        engine.record_answer("adaptive answer 1")

        # Turn 5: adaptive (qa=4, 4<5 → adaptive)
        q = engine.next_question()
        assert q is not None
        engine.record_answer("adaptive answer 2")

        # Turn 6: qa=5, 5>=5 → None
        assert engine.next_question() is None

    def test_adaptive_calls_llm(self, tmp_path):
        """LLM is called for adaptive questions from turn 4 onward."""
        llm = _make_llm(adaptive_responses=["What about budget?", "What about timeline?", "DONE"])
        config = _make_config(max_turns=10)
        engine = QuizEngine(llm, config)

        # Seed questions don't call LLM
        for i in range(3):
            engine.next_question()
            engine.record_answer(f"answer {i + 1}")

        # Turn 4: adaptive → calls LLM
        q = engine.next_question()
        assert q == "What about budget?"

        # Turn 5: adaptive → calls LLM
        engine.record_answer("budget answer")
        q = engine.next_question()
        assert q == "What about timeline?"

        # Turn 6: DONE
        engine.record_answer("timeline answer")
        q = engine.next_question()
        assert q is None


class TestAnswerHistory:
    """Answer history is preserved in order."""

    def test_preserves_all_answers_in_order(self, tmp_path):
        llm = _make_llm(dones_at=1)
        config = _make_config(max_turns=10)
        engine = QuizEngine(llm, config)

        answers = [
            "I want to build a todo app",
            "Small teams who need task management",
            "Add tasks, mark complete, due dates",
            "What about file attachments?",
        ]

        for expected_answer in answers:
            q = engine.next_question()
            assert q is not None, f"Quiz ended early at turn {len(engine.qa) + 1}"
            engine.record_answer(expected_answer)

        assert len(engine.qa) == 4
        for i, (pair, expected) in enumerate(zip(engine.qa, answers)):
            assert pair.answer == expected

    def test_qa_log_format(self, tmp_path):
        llm = _make_llm(dones_at=1)
        config = _make_config(max_turns=10)
        engine = QuizEngine(llm, config)

        engine.next_question()
        engine.record_answer("answer 1")
        engine.next_question()
        engine.record_answer("answer 2")

        log = engine.qa_log
        assert "1. Q:" in log
        assert "A: answer 1" in log
        assert "2. Q:" in log
        assert "A: answer 2" in log

    def test_is_complete_becomes_true(self, tmp_path):
        llm = _make_llm(dones_at=0)  # DONE immediately after seeds
        config = _make_config(max_turns=10)
        engine = QuizEngine(llm, config)

        # After 3 seed questions, adaptive returns DONE
        for i in range(3):
            q = engine.next_question()
            assert q is not None
            engine.record_answer(f"answer {i + 1}")

        assert engine.is_complete is True

    def test_is_complete_false_during_quiz(self, tmp_path):
        llm = _make_llm(dones_at=3)  # 3 adaptive questions before DONE
        config = _make_config(max_turns=10)
        engine = QuizEngine(llm, config)

        # During seed questions
        for i in range(3):
            q = engine.next_question()
            assert q is not None
            engine.record_answer(f"answer {i + 1}")

        assert engine.is_complete is False

        # After first adaptive
        engine.next_question()
        engine.record_answer("adaptive 1")
        assert engine.is_complete is False
