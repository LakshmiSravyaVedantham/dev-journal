"""
Git activity collector.

Uses ``subprocess`` to run ``git log`` and parse commits into Activity objects.
Groups commits by day and detects high-level intent (feature, fix, refactor, docs, test).
"""

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dev_journal.storage import Activity

logger = logging.getLogger(__name__)

# Regex patterns to classify commit intent from the message
_INTENT_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("fix", re.compile(r"\b(fix|bug|patch|hotfix|resolve|revert)\b", re.IGNORECASE)),
    ("test", re.compile(r"\b(test|spec|coverage|assert)\b", re.IGNORECASE)),
    ("docs", re.compile(r"\b(doc|readme|changelog|comment|typo)\b", re.IGNORECASE)),
    ("refactor", re.compile(r"\b(refactor|cleanup|clean up|reorganize|restructure|rename|move)\b", re.IGNORECASE)),
    ("chore", re.compile(r"\b(chore|deps|dependency|dependencies|bump|upgrade|ci|cd|lint)\b", re.IGNORECASE)),
    ("feature", re.compile(r"\b(feat|feature|add|implement|introduce|new|support)\b", re.IGNORECASE)),
]

# git log format: each commit is separated by a record-separator character
_GIT_LOG_SEP = "\x1e"
_GIT_LOG_FORMAT = _GIT_LOG_SEP.join(
    [
        "%H",  # full hash
        "%h",  # abbreviated hash
        "%an",  # author name
        "%ae",  # author email
        "%aI",  # author date ISO 8601
        "%s",  # subject
        "%b",  # body
    ]
)
_FULL_FORMAT = f"--format={_GIT_LOG_FORMAT}%x00"  # NUL-terminated records


def _run_git(args: List[str], cwd: str) -> str:
    """Run a git command and return stdout. Raises RuntimeError on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout
    except FileNotFoundError as exc:
        raise RuntimeError("git executable not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("git command timed out") from exc


def _detect_intent(message: str) -> str:
    """Return a high-level intent label for a commit message."""
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(message):
            return intent
    return "feature"


def _parse_stat_line(line: str) -> Tuple[int, int, int]:
    """
    Parse the final summary line from ``git log --stat``, e.g.
    ' 3 files changed, 45 insertions(+), 12 deletions(-)'
    Returns (files_changed, insertions, deletions).
    """
    files = insertions = deletions = 0
    m = re.search(r"(\d+) files? changed", line)
    if m:
        files = int(m.group(1))
    m = re.search(r"(\d+) insertions?", line)
    if m:
        insertions = int(m.group(1))
    m = re.search(r"(\d+) deletions?", line)
    if m:
        deletions = int(m.group(1))
    return files, insertions, deletions


class GitCollector:
    """Collect git commit activity from a local repository."""

    SOURCE = "git"

    def __init__(self, repo_path: Optional[str] = None):
        self.repo_path = str(Path(repo_path).resolve()) if repo_path else str(Path.cwd())

    def is_git_repo(self) -> bool:
        """Return True if repo_path contains a git repository."""
        try:
            _run_git(["rev-parse", "--is-inside-work-tree"], self.repo_path)
            return True
        except RuntimeError:
            return False

    def repo_name(self) -> str:
        """Return the basename of the git root directory."""
        try:
            root = _run_git(["rev-parse", "--show-toplevel"], self.repo_path).strip()
            return Path(root).name
        except RuntimeError:
            return Path(self.repo_path).name

    def collect(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        author: Optional[str] = None,
        max_commits: int = 200,
    ) -> List[Activity]:
        """
        Collect git commits as Activity objects.

        Parameters
        ----------
        since:       include commits after this datetime (default: 7 days ago)
        until:       include commits before this datetime (default: now)
        author:      filter by author email or name pattern
        max_commits: hard cap on the number of commits returned
        """
        if not self.is_git_repo():
            logger.warning("%s is not a git repository", self.repo_path)
            return []

        if since is None:
            from datetime import timedelta

            since = datetime.now() - timedelta(days=7)

        args = [
            "log",
            _FULL_FORMAT,
            "--stat",
            f"--after={since.isoformat()}",
            f"--max-count={max_commits}",
        ]
        if until:
            args.append(f"--before={until.isoformat()}")
        if author:
            args += ["--author", author]

        try:
            raw = _run_git(args, self.repo_path)
        except RuntimeError as exc:
            logger.error("Failed to collect git log: %s", exc)
            return []

        return self._parse_log_output(raw)

    def _parse_log_output(self, raw: str) -> List[Activity]:
        """Parse combined ``git log --format ... --stat`` output."""
        activities: List[Activity] = []
        # Records are NUL-terminated
        records = raw.split("\x00")
        repo = self.repo_name()

        for record in records:
            record = record.strip()
            if not record:
                continue

            # Split header from stat block (blank line separates them)
            parts = record.split("\n\n", 1)
            header_block = parts[0]
            stat_block = parts[1] if len(parts) > 1 else ""

            fields = header_block.split(_GIT_LOG_SEP)
            if len(fields) < 6:
                continue

            full_hash, short_hash, author_name, author_email, date_str, subject = fields[:6]
            body = fields[6].strip() if len(fields) > 6 else ""

            try:
                timestamp = datetime.fromisoformat(date_str.strip())
                # Normalize to naive local time so timestamps are comparable
                if timestamp.tzinfo is not None:
                    timestamp = timestamp.astimezone().replace(tzinfo=None)
            except ValueError:
                logger.debug("Could not parse date %r", date_str)
                continue

            # Parse stat lines for files changed
            changed_files: List[str] = []
            files_changed = insertions = deletions = 0
            for line in stat_block.splitlines():
                line = line.strip()
                if not line:
                    continue
                if "file" in line and "changed" in line:
                    files_changed, insertions, deletions = _parse_stat_line(line)
                elif "|" in line:
                    fname = line.split("|")[0].strip()
                    if fname:
                        changed_files.append(fname)

            intent = _detect_intent(subject)

            details: Dict[str, Any] = {
                "hash": full_hash.strip(),
                "short_hash": short_hash.strip(),
                "author_name": author_name.strip(),
                "author_email": author_email.strip(),
                "subject": subject.strip(),
                "body": body,
                "intent": intent,
                "files_changed": files_changed,
                "insertions": insertions,
                "deletions": deletions,
                "changed_files": changed_files,
            }

            summary = f"[{repo}] {subject.strip()} ({files_changed} files, +{insertions}/-{deletions})"

            activities.append(
                Activity(
                    timestamp=timestamp,
                    type="git_commit",
                    source=self.SOURCE,
                    repo=repo,
                    summary=summary,
                    details=details,
                )
            )

        return activities

    def get_current_branch(self) -> str:
        """Return the current branch name."""
        try:
            return _run_git(["rev-parse", "--abbrev-ref", "HEAD"], self.repo_path).strip()
        except RuntimeError:
            return "unknown"

    def get_open_branches(self) -> List[str]:
        """Return list of local branch names that are not main/master."""
        try:
            raw = _run_git(["branch", "--format=%(refname:short)"], self.repo_path)
            branches = [b.strip() for b in raw.splitlines() if b.strip()]
            return [b for b in branches if b not in ("main", "master", "HEAD")]
        except RuntimeError:
            return []
