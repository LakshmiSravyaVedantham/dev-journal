"""
Configuration management for dev-journal.

Reads and writes TOML config at ~/.dev-journal/config.toml.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import toml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: Dict[str, Any] = {
    "general": {
        "default_format": "markdown",
        "editor": os.environ.get("EDITOR", "vim"),
        "timezone": "local",
    },
    "tracking": {
        "repos": [],
        "shell_history_enabled": False,
        "shell_history_path": "",
        "file_watching_enabled": True,
        "ignored_extensions": [
            ".pyc",
            ".pyo",
            ".pyd",
            ".so",
            ".dll",
            ".class",
            ".jar",
            ".egg",
            ".egg-info",
            ".DS_Store",
            ".git",
        ],
        "ignored_directories": [
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            ".env",
            "dist",
            "build",
            ".tox",
            ".pytest_cache",
        ],
    },
    "privacy": {
        "opt_in_shell_history": False,
        "redact_sensitive_commands": True,
        "sensitive_patterns": [
            "password",
            "passwd",
            "secret",
            "token",
            "api_key",
            "apikey",
            "auth",
            "credential",
            "private_key",
        ],
    },
    "blog": {
        "default_tags": ["programming", "productivity", "developer-tools"],
        "devto_api_key": "",
        "author_name": "",
        "author_twitter": "",
    },
    "display": {
        "color_theme": "default",
        "show_file_details": True,
        "max_commits_in_standup": 10,
        "max_files_in_standup": 15,
    },
}


class Config:
    """Manages dev-journal configuration stored in ~/.dev-journal/config.toml."""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            self.config_dir = Path.home() / ".dev-journal"
        else:
            self.config_dir = Path(config_dir)

        self.config_file = self.config_dir / "config.toml"
        self.db_path = self.config_dir / "journal.db"
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load config from disk, merging with defaults."""
        self._data = _deep_merge(DEFAULT_CONFIG, {})
        if self.config_file.exists():
            try:
                on_disk = toml.load(str(self.config_file))
                self._data = _deep_merge(DEFAULT_CONFIG, on_disk)
            except Exception as exc:
                logger.warning("Could not parse config file %s: %s", self.config_file, exc)

    def save(self) -> None:
        """Persist current configuration to disk."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as fh:
            toml.dump(self._data, fh)

    def initialize(self) -> None:
        """Create config directory and write default config if it does not exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_file.exists():
            self.save()
            logger.info("Initialized config at %s", self.config_file)
        else:
            logger.info("Config already exists at %s", self.config_file)

    # ------------------------------------------------------------------ #
    # Typed accessors                                                       #
    # ------------------------------------------------------------------ #

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Return a config value by section and key."""
        return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        """Set a config value and persist to disk."""
        if section not in self._data:
            self._data[section] = {}
        self._data[section][key] = value
        self.save()

    @property
    def default_format(self) -> str:
        return str(self.get("general", "default_format", "markdown"))

    @property
    def shell_history_enabled(self) -> bool:
        return bool(self.get("privacy", "opt_in_shell_history", False))

    @property
    def shell_history_path(self) -> str:
        path = str(self.get("tracking", "shell_history_path", ""))
        if path:
            return path
        # Auto-detect
        zsh_history = Path.home() / ".zsh_history"
        bash_history = Path.home() / ".bash_history"
        if zsh_history.exists():
            return str(zsh_history)
        if bash_history.exists():
            return str(bash_history)
        return str(zsh_history)

    @property
    def tracked_repos(self) -> List[str]:
        return list(self.get("tracking", "repos", []))

    @property
    def ignored_extensions(self) -> List[str]:
        return list(self.get("tracking", "ignored_extensions", []))

    @property
    def ignored_directories(self) -> List[str]:
        return list(self.get("tracking", "ignored_directories", []))

    @property
    def sensitive_patterns(self) -> List[str]:
        return list(self.get("privacy", "sensitive_patterns", []))

    @property
    def blog_tags(self) -> List[str]:
        return list(self.get("blog", "default_tags", []))

    @property
    def author_name(self) -> str:
        return str(self.get("blog", "author_name", ""))

    def add_repo(self, repo_path: str) -> None:
        """Add a repo path to the tracked repos list."""
        repos = self.tracked_repos
        if repo_path not in repos:
            repos.append(repo_path)
            self.set("tracking", "repos", repos)

    def enable_shell_history(self, history_path: Optional[str] = None) -> None:
        """Opt-in to shell history collection."""
        self.set("privacy", "opt_in_shell_history", True)
        self.set("tracking", "shell_history_enabled", True)
        if history_path:
            self.set("tracking", "shell_history_path", history_path)
        self.save()

    def as_dict(self) -> Dict[str, Any]:
        """Return the full config as a plain dictionary."""
        return dict(self._data)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge *override* into *base*, returning a new dict."""
    result: Dict[str, Any] = {}
    for key, base_val in base.items():
        if key in override:
            if isinstance(base_val, dict) and isinstance(override[key], dict):
                result[key] = _deep_merge(base_val, override[key])
            else:
                result[key] = override[key]
        else:
            result[key] = base_val
    # Keys only in override
    for key, val in override.items():
        if key not in base:
            result[key] = val
    return result
