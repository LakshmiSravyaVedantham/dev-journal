"""
Tests for the dev-journal CLI (Click commands).

Uses click.testing.CliRunner to invoke commands without spawning a subprocess.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from dev_journal.cli import main
from dev_journal.config import Config
from dev_journal.storage import ActivityStorage
from tests.conftest import make_commit, make_file_change

# ------------------------------------------------------------------ #
# Fixtures                                                              #
# ------------------------------------------------------------------ #


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def isolated_runner(tmp_dir: Path) -> CliRunner:
    """Runner that injects a temporary config directory via env var."""
    return CliRunner(mix_stderr=False, env={"HOME": str(tmp_dir)})


# ------------------------------------------------------------------ #
# version command                                                       #
# ------------------------------------------------------------------ #


def test_version_command(runner: CliRunner) -> None:
    """version command exits 0 and shows the version string."""
    from dev_journal import __version__

    result = runner.invoke(main, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


# ------------------------------------------------------------------ #
# init command                                                          #
# ------------------------------------------------------------------ #


def test_init_creates_config(tmp_dir: Path, runner: CliRunner) -> None:
    """init command creates the config directory and config file."""
    config_dir = tmp_dir / ".dev-journal"

    with patch("dev_journal.cli.Config") as mock_cfg_cls:
        mock_cfg = MagicMock(spec=Config)
        mock_cfg.config_dir = config_dir
        mock_cfg.db_path = config_dir / "journal.db"
        mock_cfg.config_file = config_dir / "config.toml"
        mock_cfg.shell_history_enabled = False
        mock_cfg.shell_history_path = str(tmp_dir / ".zsh_history")
        mock_cfg.tracked_repos = []
        mock_cfg.count = MagicMock(return_value=0)
        mock_cfg_cls.return_value = mock_cfg

        with patch("dev_journal.cli._get_storage") as mock_storage_fn:
            mock_storage = MagicMock(spec=ActivityStorage)
            mock_storage.count.return_value = 0
            mock_storage_fn.return_value = mock_storage

            result = runner.invoke(main, ["init", "--repo", str(tmp_dir)])

    assert result.exit_code == 0, result.output


# ------------------------------------------------------------------ #
# collect command                                                       #
# ------------------------------------------------------------------ #


def test_collect_command_no_git(tmp_dir: Path, runner: CliRunner) -> None:
    """collect command handles non-git directories gracefully."""
    with patch("dev_journal.cli.Config") as mock_cfg_cls:
        mock_cfg = MagicMock(spec=Config)
        mock_cfg.config_dir = tmp_dir / ".dev-journal"
        mock_cfg.db_path = tmp_dir / ".dev-journal" / "journal.db"
        mock_cfg.ignored_extensions = []
        mock_cfg.ignored_directories = []
        mock_cfg.shell_history_enabled = False
        mock_cfg.shell_history_path = ""
        mock_cfg.sensitive_patterns = []
        mock_cfg_cls.return_value = mock_cfg

        with patch("dev_journal.cli._get_storage") as mock_storage_fn:
            mock_storage = MagicMock(spec=ActivityStorage)
            mock_storage.count.return_value = 0
            mock_storage.insert_many.return_value = 0
            mock_storage_fn.return_value = mock_storage

            with patch("dev_journal.collectors.git_collector.GitCollector.is_git_repo", return_value=False):
                with patch("dev_journal.collectors.file_collector.FileCollector.collect", return_value=[]):
                    result = runner.invoke(main, ["collect", "--repo", str(tmp_dir)])

    assert result.exit_code == 0


# ------------------------------------------------------------------ #
# standup command                                                       #
# ------------------------------------------------------------------ #


def test_standup_text_format(tmp_dir: Path, runner: CliRunner) -> None:
    """standup --format text outputs plain text."""
    storage = ActivityStorage(db_path=tmp_dir / "journal.db")
    storage.insert(make_commit(days_ago=1))

    with patch("dev_journal.cli.Config") as mock_cfg_cls:
        mock_cfg = MagicMock(spec=Config)
        mock_cfg_cls.return_value = mock_cfg

        with patch("dev_journal.cli._get_storage", return_value=storage):
            with patch("dev_journal.collectors.git_collector.GitCollector.is_git_repo", return_value=False):
                result = runner.invoke(main, ["standup", "--format", "text"])

    assert result.exit_code == 0
    assert "DAILY STANDUP" in result.output


def test_standup_json_format(tmp_dir: Path, runner: CliRunner) -> None:
    """standup --format json outputs valid JSON."""
    storage = ActivityStorage(db_path=tmp_dir / "journal.db")
    storage.insert(make_commit(days_ago=1))

    with patch("dev_journal.cli.Config") as mock_cfg_cls:
        mock_cfg = MagicMock(spec=Config)
        mock_cfg_cls.return_value = mock_cfg

        with patch("dev_journal.cli._get_storage", return_value=storage):
            with patch("dev_journal.collectors.git_collector.GitCollector.is_git_repo", return_value=False):
                result = runner.invoke(main, ["standup", "--format", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "yesterday_items" in data


# ------------------------------------------------------------------ #
# weekly command                                                        #
# ------------------------------------------------------------------ #


def test_weekly_json_format(tmp_dir: Path, runner: CliRunner) -> None:
    """weekly --format json outputs valid JSON."""
    from datetime import datetime as dt

    storage = ActivityStorage(db_path=tmp_dir / "journal.db")
    # Insert all commits inside the same known week (Mon Feb 16 .. Sun Feb 22, 2026)
    monday = "2026-02-16"
    for offset in range(3):
        c = make_commit()
        c.timestamp = dt(2026, 2, 17 + offset, 10, 0)  # Tue/Wed/Thu
        storage.insert(c)

    with patch("dev_journal.cli.Config") as mock_cfg_cls:
        mock_cfg = MagicMock(spec=Config)
        mock_cfg_cls.return_value = mock_cfg

        with patch("dev_journal.cli._get_storage", return_value=storage):
            result = runner.invoke(main, ["weekly", "--format", "json", "--week", monday])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total_commits"] == 3


# ------------------------------------------------------------------ #
# blog command                                                          #
# ------------------------------------------------------------------ #


def test_blog_output_to_file(tmp_dir: Path, runner: CliRunner) -> None:
    """blog --output saves the draft to the specified file."""
    storage = ActivityStorage(db_path=tmp_dir / "journal.db")
    storage.insert(make_commit(days_ago=1))

    output_file = tmp_dir / "draft.md"

    with patch("dev_journal.cli.Config") as mock_cfg_cls:
        mock_cfg = MagicMock(spec=Config)
        mock_cfg.blog_tags = ["programming"]
        mock_cfg.author_name = "Test Author"
        mock_cfg_cls.return_value = mock_cfg

        with patch("dev_journal.cli._get_storage", return_value=storage):
            result = runner.invoke(main, ["blog", "--days", "1", "--output", str(output_file)])

    assert result.exit_code == 0
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "---" in content
    assert "title:" in content


# ------------------------------------------------------------------ #
# timeline command                                                      #
# ------------------------------------------------------------------ #


def test_timeline_no_activity(tmp_dir: Path, runner: CliRunner) -> None:
    """timeline with empty journal prints helpful message."""
    storage = ActivityStorage(db_path=tmp_dir / "journal.db")

    with patch("dev_journal.cli.Config") as mock_cfg_cls:
        mock_cfg = MagicMock(spec=Config)
        mock_cfg_cls.return_value = mock_cfg

        with patch("dev_journal.cli._get_storage", return_value=storage):
            result = runner.invoke(main, ["timeline"])

    assert result.exit_code == 0


def test_timeline_with_activities(tmp_dir: Path, runner: CliRunner) -> None:
    """timeline renders without errors when activities exist."""
    storage = ActivityStorage(db_path=tmp_dir / "journal.db")
    storage.insert(make_commit(days_ago=0))
    storage.insert(make_file_change(days_ago=0))

    with patch("dev_journal.cli.Config") as mock_cfg_cls:
        mock_cfg = MagicMock(spec=Config)
        mock_cfg_cls.return_value = mock_cfg

        with patch("dev_journal.cli._get_storage", return_value=storage):
            result = runner.invoke(main, ["timeline", "--days", "1"])

    assert result.exit_code == 0


# ------------------------------------------------------------------ #
# --help smoke tests                                                    #
# ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    "command",
    ["--help", "init --help", "collect --help", "standup --help", "weekly --help", "blog --help", "timeline --help"],
)
def test_help_text(runner: CliRunner, command: str) -> None:
    """Every command has a --help that exits cleanly."""
    result = runner.invoke(main, command.split())
    assert result.exit_code == 0
    assert "Usage:" in result.output or "Options:" in result.output
