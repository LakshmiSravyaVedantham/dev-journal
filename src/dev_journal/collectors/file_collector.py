"""
File-change collector.

Scans a directory tree for recently modified files using ``os.stat()`` mtime.
Groups results by file type and directory. Respects configured ignore lists.
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

from dev_journal.storage import Activity

logger = logging.getLogger(__name__)

# Human-friendly labels for file extensions
_EXT_LABELS: Dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "React JSX",
    ".tsx": "React TSX",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Bash",
    ".zsh": "Zsh",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".txt": "Text",
    ".dockerfile": "Dockerfile",
}


class FileCollector:
    """Scan a directory for recently modified files."""

    SOURCE = "file_watcher"

    def __init__(
        self,
        root_path: Optional[str] = None,
        ignored_extensions: Optional[List[str]] = None,
        ignored_directories: Optional[List[str]] = None,
    ):
        self.root_path = str(Path(root_path).resolve()) if root_path else str(Path.cwd())
        self.ignored_extensions: Set[str] = set(
            ignored_extensions
            or [
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
            ]
        )
        self.ignored_directories: Set[str] = set(
            ignored_directories
            or [
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
                ".mypy_cache",
            ]
        )

    def collect(
        self,
        since: Optional[datetime] = None,
        max_files: int = 500,
    ) -> List[Activity]:
        """
        Return Activity objects for files modified since *since*.

        Parameters
        ----------
        since:     lower bound for mtime (default: 24 hours ago)
        max_files: hard cap on returned entries
        """
        if since is None:
            since = datetime.now() - timedelta(hours=24)

        since_ts = since.timestamp()
        results: List[Activity] = []
        root = Path(self.root_path)
        repo_name = root.name

        try:
            for dirpath, dirnames, filenames in os.walk(root):
                # Prune ignored directories in-place so os.walk skips them
                dirnames[:] = [d for d in dirnames if d not in self.ignored_directories and not d.startswith(".")]

                for filename in filenames:
                    if len(results) >= max_files:
                        break

                    filepath = Path(dirpath) / filename
                    ext = filepath.suffix.lower()

                    if ext in self.ignored_extensions:
                        continue

                    try:
                        stat = filepath.stat()
                    except OSError:
                        continue

                    if stat.st_mtime < since_ts:
                        continue

                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    rel_path = str(filepath.relative_to(root))
                    lang = _EXT_LABELS.get(ext, ext.lstrip(".").upper() if ext else "Unknown")

                    activity = Activity(
                        timestamp=mtime,
                        type="file_change",
                        source=self.SOURCE,
                        repo=repo_name,
                        summary=f"Modified {rel_path}",
                        details={
                            "path": rel_path,
                            "abs_path": str(filepath),
                            "extension": ext,
                            "language": lang,
                            "size_bytes": stat.st_size,
                            "directory": str(Path(dirpath).relative_to(root)),
                        },
                    )
                    results.append(activity)

        except PermissionError as exc:
            logger.warning("Permission denied walking %s: %s", self.root_path, exc)

        # Sort newest first
        results.sort(key=lambda a: a.timestamp, reverse=True)
        return results

    def summarize(self, activities: List[Activity]) -> Dict[str, object]:
        """
        Build a summary dictionary from a list of file-change activities.

        Returns a dict with: total_files, by_language, by_directory, files.
        """
        by_language: Dict[str, int] = {}
        by_directory: Dict[str, int] = {}
        files: List[str] = []

        for a in activities:
            if a.type != "file_change":
                continue
            lang = str(a.details.get("language", "Unknown"))
            directory = str(a.details.get("directory", "."))
            path = str(a.details.get("path", ""))

            by_language[lang] = by_language.get(lang, 0) + 1
            by_directory[directory] = by_directory.get(directory, 0) + 1
            if path:
                files.append(path)

        return {
            "total_files": len(activities),
            "by_language": dict(sorted(by_language.items(), key=lambda x: x[1], reverse=True)),
            "by_directory": dict(sorted(by_directory.items(), key=lambda x: x[1], reverse=True)),
            "files": files,
        }
