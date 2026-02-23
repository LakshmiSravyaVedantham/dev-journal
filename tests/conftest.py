"""
pytest configuration and shared fixtures for dev-journal tests.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator

import pytest

from dev_journal.config import Config
from dev_journal.storage import Activity, ActivityStorage

# ------------------------------------------------------------------ #
# Temporary directory fixture                                           #
# ------------------------------------------------------------------ #


@pytest.fixture()
def tmp_dir() -> Generator[Path, None, None]:
    """Provide a fresh temporary directory for each test."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


# ------------------------------------------------------------------ #
# Storage fixture                                                       #
# ------------------------------------------------------------------ #


@pytest.fixture()
def storage(tmp_dir: Path) -> ActivityStorage:
    """In-memory SQLite storage backed by a temp file."""
    return ActivityStorage(db_path=tmp_dir / "test_journal.db")


# ------------------------------------------------------------------ #
# Config fixture                                                        #
# ------------------------------------------------------------------ #


@pytest.fixture()
def config(tmp_dir: Path) -> Config:
    """Config pointing to a temporary directory."""
    return Config(config_dir=tmp_dir / ".dev-journal")


# ------------------------------------------------------------------ #
# Sample activities                                                     #
# ------------------------------------------------------------------ #


def make_commit(
    repo: str = "my-repo",
    subject: str = "feat: add login",
    intent: str = "feature",
    days_ago: int = 0,
    hours_ago: int = 2,
    insertions: int = 45,
    deletions: int = 12,
    files_changed: int = 3,
) -> Activity:
    ts = datetime.now() - timedelta(days=days_ago, hours=hours_ago)
    return Activity(
        timestamp=ts,
        type="git_commit",
        source="git",
        repo=repo,
        summary=f"[{repo}] {subject}",
        details={
            "hash": "abc1234def5678",
            "short_hash": "abc1234",
            "author_name": "Dev User",
            "author_email": "dev@example.com",
            "subject": subject,
            "body": "",
            "intent": intent,
            "files_changed": files_changed,
            "insertions": insertions,
            "deletions": deletions,
            "changed_files": ["src/auth.py", "tests/test_auth.py", "README.md"],
        },
    )


def make_file_change(
    repo: str = "my-repo",
    path: str = "src/main.py",
    language: str = "Python",
    days_ago: int = 0,
    hours_ago: int = 1,
) -> Activity:
    ts = datetime.now() - timedelta(days=days_ago, hours=hours_ago)
    return Activity(
        timestamp=ts,
        type="file_change",
        source="file_watcher",
        repo=repo,
        summary=f"Modified {path}",
        details={
            "path": path,
            "abs_path": f"/home/user/projects/{repo}/{path}",
            "extension": "." + path.rsplit(".", 1)[-1],
            "language": language,
            "size_bytes": 2048,
            "directory": str(Path(path).parent),
        },
    )


def make_shell_cmd(
    command: str = "git status",
    days_ago: int = 0,
    hours_ago: int = 0,
) -> Activity:
    ts = datetime.now() - timedelta(days=days_ago, hours=hours_ago)
    return Activity(
        timestamp=ts,
        type="shell_command",
        source="shell_history",
        repo="",
        summary=command,
        details={"command": command, "shell": "zsh"},
    )


@pytest.fixture()
def sample_activities() -> list:
    """A mixed set of activities from the last couple of days."""
    return [
        make_commit(
            subject="feat: add user registration", intent="feature", days_ago=1, insertions=89, files_changed=5
        ),
        make_commit(subject="fix: correct validation error", intent="fix", days_ago=1, insertions=12, deletions=8),
        make_commit(subject="test: add auth test coverage", intent="test", days_ago=1, insertions=55),
        make_commit(subject="feat: implement dashboard widget", intent="feature", days_ago=0, insertions=120),
        make_file_change(path="src/auth.py", days_ago=1),
        make_file_change(path="src/dashboard.py", days_ago=0),
        make_shell_cmd("pytest -v", days_ago=1),
        make_shell_cmd("git push origin main", days_ago=0),
    ]
