"""Tests for orchestrator.lib.git."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.lib.git import GitOps, UncleanWorkingTree


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    return tmp_path


@pytest.fixture
def git_ops(tmp_project: Path):
    """Create a GitOps instance."""
    return GitOps(tmp_project)


class TestGitOps:
    """Test GitOps operations."""

    def test_ensure_repo_creates_git_dir(self, tmp_project, git_ops):
        """ensure_repo() creates .git directory."""
        git_ops.ensure_repo(tmp_project)
        assert (tmp_project / ".git").exists()

    def test_assert_clean_raises_with_uncommitted(self, tmp_project, git_ops):
        """assert_clean() raises UncleanWorkingTree with uncommitted changes."""
        git_ops.ensure_repo(tmp_project)
        import subprocess
        (tmp_project / "new_file.txt").write_text("hello", encoding="utf-8")
        subprocess.run(["git", "add", "new_file.txt"], cwd=tmp_project, check=True, capture_output=True)
        with pytest.raises(UncleanWorkingTree):
            git_ops.assert_clean()

    def test_commit_task_creates_commit(self, tmp_project, git_ops):
        """commit_task() creates a git commit and returns short SHA."""
        git_ops.ensure_repo(tmp_project)
        # Need to configure git user for commits
        import subprocess
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_project, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_project, check=True, capture_output=True,
        )
        (tmp_project / "new_file.txt").write_text("hello", encoding="utf-8")
        short_sha = git_ops.commit_task("architect", 1, "Setup", "0000000")
        assert isinstance(short_sha, str)
        assert len(short_sha) == 7

    def test_tag_phase_creates_tag(self, tmp_project, git_ops):
        """tag_phase() creates an annotated tag."""
        git_ops.ensure_repo(tmp_project)
        import subprocess
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_project, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_project, check=True, capture_output=True,
        )
        (tmp_project / "new_file.txt").write_text("hello", encoding="utf-8")
        git_ops.commit_task("architect", 1, "Setup", "0000000")
        git_ops.tag_phase(1)  # should not raise

    def test_tag_phase_creates_annotated_tag(self, tmp_project, git_ops):
        """tag_phase() creates an annotated tag (not lightweight)."""
        git_ops.ensure_repo(tmp_project)
        import subprocess
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_project, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_project, check=True, capture_output=True,
        )
        (tmp_project / "new_file.txt").write_text("hello", encoding="utf-8")
        git_ops.commit_task("architect", 1, "Setup", "0000000")
        git_ops.tag_phase(1)
        result = subprocess.run(
            ["git", "tag", "-l", "phase-1-done", "--format=%(objecttype)"],
            cwd=tmp_project, check=True, capture_output=True, text=True,
        )
        assert "tag" in result.stdout.strip()

    def test_rollback_to_resets_hard(self, tmp_project, git_ops):
        """rollback_to() performs git reset --hard."""
        git_ops.ensure_repo(tmp_project)
        import subprocess
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_project, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_project, check=True, capture_output=True,
        )
        (tmp_project / "file1.txt").write_text("v1", encoding="utf-8")
        git_ops.commit_task("architect", 1, "Setup", "0000000")
        head_before = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_project, check=True, capture_output=True, text=True,
        ).stdout.strip()
        (tmp_project / "file1.txt").write_text("v2", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_project, check=True, capture_output=True)
        git_ops.rollback_to(head_before)
        content = (tmp_project / "file1.txt").read_text()
        assert content == "v1"
