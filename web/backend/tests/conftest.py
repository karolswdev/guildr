"""Shared isolation for backend web tests."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


_TEST_PROJECTS_DIR = Path(tempfile.mkdtemp(prefix="guildr-web-tests-"))
os.environ["ORCHESTRATOR_PROJECTS_DIR"] = str(_TEST_PROJECTS_DIR)


def pytest_sessionfinish(session, exitstatus):  # noqa: ANN001
    """Remove the project root used by module-level route singletons."""
    shutil.rmtree(_TEST_PROJECTS_DIR, ignore_errors=True)
