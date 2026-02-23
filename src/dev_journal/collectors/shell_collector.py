"""
Shell history collector (opt-in only).

Parses ~/.bash_history or ~/.zsh_history and returns developer-relevant
commands as Activity objects. Sensitive commands are filtered out before
any storage or display.

PRIVACY: This collector is disabled by default. It must be explicitly
enabled by the user with ``dev-journal init --enable-shell-history``.
"""

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Set

from dev_journal.storage import Activity

logger = logging.getLogger(__name__)

# Commands worth tracking (developer workflow related)
_RELEVANT_PREFIXES: tuple = (
    "git ",
    "npm ",
    "yarn ",
    "pnpm ",
    "pip ",
    "pip3 ",
    "poetry ",
    "docker ",
    "docker-compose ",
    "kubectl ",
    "helm ",
    "terraform ",
    "make ",
    "pytest ",
    "python ",
    "python3 ",
    "uvicorn ",
    "gunicorn ",
    "flask ",
    "django-admin ",
    "manage.py ",
    "cargo ",
    "rustup ",
    "go ",
    "node ",
    "deno ",
    "bun ",
    "brew ",
    "apt ",
    "apt-get ",
    "ssh ",
    "scp ",
    "rsync ",
    "curl ",
    "wget ",
    "psql ",
    "mysql ",
    "redis-cli ",
)

# Regex patterns that indicate a command might contain a secret/credential
_SENSITIVE_PATTERNS: List[re.Pattern] = [
    re.compile(r"(password|passwd|--password|-p\s+\S+)", re.IGNORECASE),
    re.compile(r"(secret|token|api.?key|apikey)", re.IGNORECASE),
    re.compile(r"(auth|credential|private.?key)", re.IGNORECASE),
    re.compile(r"(bearer|authorization:)", re.IGNORECASE),
    re.compile(r"(-e\s+[A-Z_]+=\S+)", re.IGNORECASE),  # env var assignments
    re.compile(r"(export\s+\w+=\S+)", re.IGNORECASE),  # export FOO=bar
    re.compile(
        r"(\b[A-Z][A-Z0-9_]{5,}=[^\s]+)",
    ),  # FOO_BAR=value pattern
]


def _is_sensitive(command: str, extra_patterns: Optional[List[str]] = None) -> bool:
    """Return True if the command looks like it might contain a credential."""
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(command):
            return True
    if extra_patterns:
        for pat in extra_patterns:
            if re.search(pat, command, re.IGNORECASE):
                return True
    return False


def _is_relevant(command: str) -> bool:
    """Return True if the command is developer-workflow relevant."""
    stripped = command.strip()
    return any(stripped.startswith(prefix) for prefix in _RELEVANT_PREFIXES)


def _parse_zsh_history(raw: str) -> List[tuple]:
    """
    Parse extended zsh history format.

    Lines look like:
        : 1706000000:0;git commit -m "message"
    Returns list of (timestamp: datetime | None, command: str).
    """
    results: List[tuple] = []
    extended_re = re.compile(r"^: (\d+):\d+;(.+)$")
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = extended_re.match(line)
        if m:
            try:
                ts = datetime.fromtimestamp(int(m.group(1)))
            except (ValueError, OSError):
                ts = None
            results.append((ts, m.group(2).strip()))
        elif not line.startswith(":"):
            results.append((None, line))
    return results


def _parse_bash_history(raw: str) -> List[tuple]:
    """
    Parse bash history.

    Lines may have optional timestamp comments:
        #1706000000
        git commit -m "message"
    Returns list of (timestamp: datetime | None, command: str).
    """
    results: List[tuple] = []
    timestamp: Optional[datetime] = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            try:
                ts_int = int(line[1:])
                timestamp = datetime.fromtimestamp(ts_int)
            except ValueError:
                pass
            continue
        results.append((timestamp, line))
        timestamp = None
    return results


class ShellCollector:
    """
    Collect developer-relevant shell commands (opt-in only).

    Parameters
    ----------
    history_path:        Path to shell history file. Auto-detected if None.
    sensitive_patterns:  Additional regex patterns to treat as sensitive.
    """

    SOURCE = "shell_history"

    def __init__(
        self,
        history_path: Optional[str] = None,
        sensitive_patterns: Optional[List[str]] = None,
    ):
        if history_path:
            self.history_path = Path(history_path)
        else:
            self.history_path = self._detect_history_path()

        self.sensitive_patterns = sensitive_patterns or []
        self._seen_commands: Set[str] = set()  # dedup within a session

    @staticmethod
    def _detect_history_path() -> Path:
        zsh = Path.home() / ".zsh_history"
        bash = Path.home() / ".bash_history"
        if zsh.exists():
            return zsh
        if bash.exists():
            return bash
        return zsh  # default even if not present yet

    def collect(
        self,
        since: Optional[datetime] = None,
        max_commands: int = 300,
    ) -> List[Activity]:
        """
        Return Activity objects for relevant shell commands since *since*.

        Parameters
        ----------
        since:        lower bound (default: 24 hours ago)
        max_commands: hard cap on returned entries
        """
        if since is None:
            since = datetime.now() - timedelta(hours=24)

        if not self.history_path.exists():
            logger.debug("Shell history file not found: %s", self.history_path)
            return []

        try:
            raw = self.history_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Could not read shell history: %s", exc)
            return []

        # Detect format
        is_zsh = "zsh" in str(self.history_path) or any(line.strip().startswith(": ") for line in raw.splitlines()[:10])
        if is_zsh:
            entries = _parse_zsh_history(raw)
        else:
            entries = _parse_bash_history(raw)

        activities: List[Activity] = []
        since_ts = since.timestamp()

        for ts, cmd in reversed(entries):  # newest first
            if len(activities) >= max_commands:
                break
            if not cmd:
                continue
            if ts is not None and ts.timestamp() < since_ts:
                break

            if not _is_relevant(cmd):
                continue
            if _is_sensitive(cmd, self.sensitive_patterns):
                logger.debug("Skipping sensitive command")
                continue

            # Deduplicate identical consecutive commands
            if cmd in self._seen_commands:
                continue
            self._seen_commands.add(cmd)

            effective_ts = ts if ts is not None else datetime.now()

            activities.append(
                Activity(
                    timestamp=effective_ts,
                    type="shell_command",
                    source=self.SOURCE,
                    repo="",
                    summary=cmd[:200],
                    details={
                        "command": cmd,
                        "shell": "zsh" if is_zsh else "bash",
                    },
                )
            )

        return activities
