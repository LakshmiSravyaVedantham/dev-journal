"""
Tests for dev_journal.collectors.git_collector.

Uses unittest.mock to patch subprocess calls so no real git repo is needed.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from dev_journal.collectors.git_collector import (
    GitCollector,
    _detect_intent,
    _parse_stat_line,
)

# ------------------------------------------------------------------ #
# Unit tests for helper functions                                       #
# ------------------------------------------------------------------ #


def test_detect_intent_fix() -> None:
    assert _detect_intent("fix: resolve null pointer in auth") == "fix"
    assert _detect_intent("hotfix: patch SQL injection") == "fix"


def test_detect_intent_feature() -> None:
    assert _detect_intent("feat: add user registration") == "feature"
    assert _detect_intent("implement OAuth2 integration") == "feature"


def test_detect_intent_test() -> None:
    assert _detect_intent("test: add coverage for payment module") == "test"


def test_detect_intent_docs() -> None:
    assert _detect_intent("docs: update README with install instructions") == "docs"


def test_detect_intent_refactor() -> None:
    assert _detect_intent("refactor: extract helper functions") == "refactor"


def test_detect_intent_chore() -> None:
    assert _detect_intent("chore: bump dependencies") == "chore"


def test_detect_intent_default() -> None:
    """Unrecognized messages default to 'feature'."""
    assert _detect_intent("random commit message xyz") == "feature"


def test_parse_stat_line_full() -> None:
    line = " 3 files changed, 45 insertions(+), 12 deletions(-)"
    files, ins, dels = _parse_stat_line(line)
    assert files == 3
    assert ins == 45
    assert dels == 12


def test_parse_stat_line_insertions_only() -> None:
    line = " 1 file changed, 10 insertions(+)"
    files, ins, dels = _parse_stat_line(line)
    assert files == 1
    assert ins == 10
    assert dels == 0


def test_parse_stat_line_empty() -> None:
    files, ins, dels = _parse_stat_line("no stat here")
    assert files == 0
    assert ins == 0
    assert dels == 0


# ------------------------------------------------------------------ #
# GitCollector with mocked subprocess                                   #
# ------------------------------------------------------------------ #

# A realistic snippet of ``git log --format=... --stat`` output.
# Records are NUL-terminated; fields are separated by the record-separator
# character (0x1E). The format produces no leading separator.
_SEP = "\x1e"
_MOCK_GIT_LOG = (
    _SEP.join(
        [
            "abc1234def5678",
            "abc1234",
            "Dev User",
            "dev@example.com",
            "2026-02-20T10:30:00+00:00",
            "feat: add login endpoint",
            "",
        ]
    )
    + "\x00"
    + "\n\n src/auth.py          | 45 ++++++++++++\n"
    " tests/test_auth.py   | 20 +++++\n"
    " 2 files changed, 65 insertions(+), 0 deletions(-)\n"
    + _SEP.join(
        [
            "def5678abc1234",
            "def5678",
            "Dev User",
            "dev@example.com",
            "2026-02-19T14:00:00+00:00",
            "fix: handle empty password",
            "",
        ]
    )
    + "\x00"
    + "\n\n src/auth.py          | 5 +-\n"
    " 1 file changed, 3 insertions(+), 2 deletions(-)\n"
)


@patch("dev_journal.collectors.git_collector.subprocess.run")
def test_is_git_repo_true(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="true\n", stderr="")
    collector = GitCollector("/some/repo")
    assert collector.is_git_repo() is True


@patch("dev_journal.collectors.git_collector.subprocess.run")
def test_is_git_repo_false(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="not a git repo")
    collector = GitCollector("/not/a/repo")
    assert collector.is_git_repo() is False


@patch("dev_journal.collectors.git_collector.subprocess.run")
def test_collect_returns_activities(mock_run: MagicMock) -> None:
    """collect() parses git log output into Activity objects."""
    # First call: is_git_repo check
    # Second call: repo_name
    # Third call: actual log
    # Call order: is_git_repo, git log, repo_name (show-toplevel)
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="true\n", stderr=""),
        MagicMock(returncode=0, stdout=_MOCK_GIT_LOG, stderr=""),
        MagicMock(returncode=0, stdout="/projects/my-repo\n", stderr=""),
    ]

    collector = GitCollector("/projects/my-repo")
    since = datetime(2026, 2, 18)
    activities = collector.collect(since=since)

    assert len(activities) == 2
    assert activities[0].type == "git_commit"
    assert activities[0].details["subject"] == "feat: add login endpoint"
    assert activities[0].details["intent"] == "feature"
    assert activities[1].details["subject"] == "fix: handle empty password"
    assert activities[1].details["intent"] == "fix"


@patch("dev_journal.collectors.git_collector.subprocess.run")
def test_collect_non_git_repo_returns_empty(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="fatal: not a git repository")
    collector = GitCollector("/not/a/repo")
    activities = collector.collect(since=datetime(2026, 1, 1))
    assert activities == []


@patch("dev_journal.collectors.git_collector.subprocess.run")
def test_get_current_branch(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="feature/my-feature\n", stderr="")
    collector = GitCollector("/repo")
    assert collector.get_current_branch() == "feature/my-feature"


@patch("dev_journal.collectors.git_collector.subprocess.run")
def test_get_open_branches(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="main\nfeature/login\nbugfix/auth-null\n",
        stderr="",
    )
    collector = GitCollector("/repo")
    branches = collector.get_open_branches()
    assert "feature/login" in branches
    assert "bugfix/auth-null" in branches
    assert "main" not in branches
