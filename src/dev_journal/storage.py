"""
SQLite-based local activity storage for dev-journal.

Schema
------
activities(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,          -- ISO-8601
    type        TEXT NOT NULL,          -- git_commit | file_change | shell_command
    source      TEXT NOT NULL,          -- collector name
    repo        TEXT NOT NULL DEFAULT '',
    summary     TEXT NOT NULL DEFAULT '',
    details     TEXT NOT NULL DEFAULT '' -- JSON blob
)
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT    NOT NULL,
    type      TEXT    NOT NULL,
    source    TEXT    NOT NULL,
    repo      TEXT    NOT NULL DEFAULT '',
    summary   TEXT    NOT NULL DEFAULT '',
    details   TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_activities_timestamp ON activities (timestamp);
CREATE INDEX IF NOT EXISTS idx_activities_type      ON activities (type);
CREATE INDEX IF NOT EXISTS idx_activities_repo      ON activities (repo);
"""


class Activity:
    """Represents a single tracked developer activity."""

    __slots__ = ("id", "timestamp", "type", "source", "repo", "summary", "details")

    def __init__(
        self,
        timestamp: datetime,
        type: str,  # noqa: A002
        source: str,
        repo: str = "",
        summary: str = "",
        details: Optional[Dict[str, Any]] = None,
        id: Optional[int] = None,  # noqa: A002
    ):
        self.id = id
        self.timestamp = timestamp
        self.type = type
        self.source = source
        self.repo = repo
        self.summary = summary
        self.details: Dict[str, Any] = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "type": self.type,
            "source": self.source,
            "repo": self.repo,
            "summary": self.summary,
            "details": self.details,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Activity":
        details: Dict[str, Any] = {}
        try:
            details = json.loads(row["details"])
        except (json.JSONDecodeError, TypeError):
            pass
        ts = datetime.fromisoformat(row["timestamp"])
        # Normalize to naive local time for consistent comparison
        if ts.tzinfo is not None:
            ts = ts.astimezone().replace(tzinfo=None)
        return cls(
            id=row["id"],
            timestamp=ts,
            type=row["type"],
            source=row["source"],
            repo=row["repo"],
            summary=row["summary"],
            details=details,
        )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Activity id={self.id} type={self.type!r} ts={self.timestamp.date()}>"


class ActivityStorage:
    """Manages persistence of Activity objects in a local SQLite database."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".dev-journal" / "journal.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ #
    # CRUD                                                                  #
    # ------------------------------------------------------------------ #

    def insert(self, activity: Activity) -> int:
        """Persist an activity and return its new row id."""
        sql = """
            INSERT INTO activities (timestamp, type, source, repo, summary, details)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        with self._conn() as conn:
            cur = conn.execute(
                sql,
                (
                    activity.timestamp.isoformat(),
                    activity.type,
                    activity.source,
                    activity.repo,
                    activity.summary,
                    json.dumps(activity.details),
                ),
            )
            row_id = cur.lastrowid or 0
        activity.id = row_id
        return row_id

    def insert_many(self, activities: List[Activity]) -> int:
        """Bulk insert a list of activities. Returns count inserted."""
        if not activities:
            return 0
        sql = """
            INSERT INTO activities (timestamp, type, source, repo, summary, details)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        rows = [
            (
                a.timestamp.isoformat(),
                a.type,
                a.source,
                a.repo,
                a.summary,
                json.dumps(a.details),
            )
            for a in activities
        ]
        with self._conn() as conn:
            conn.executemany(sql, rows)
        return len(rows)

    def get(self, activity_id: int) -> Optional[Activity]:
        """Fetch a single activity by id."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
        return Activity.from_row(row) if row else None

    def delete(self, activity_id: int) -> bool:
        """Delete an activity by id. Returns True if a row was deleted."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
            return cur.rowcount > 0

    def clear_all(self) -> int:
        """Remove all activities. Returns count deleted."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM activities")
            return cur.rowcount

    # ------------------------------------------------------------------ #
    # Queries                                                               #
    # ------------------------------------------------------------------ #

    def query(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        activity_type: Optional[str] = None,
        repo: Optional[str] = None,
        limit: int = 500,
    ) -> List[Activity]:
        """Return activities filtered by the given criteria, newest first."""
        clauses = []
        params: List[Any] = []

        if start:
            clauses.append("timestamp >= ?")
            params.append(start.isoformat())
        if end:
            clauses.append("timestamp <= ?")
            params.append(end.isoformat())
        if activity_type:
            clauses.append("type = ?")
            params.append(activity_type)
        if repo:
            clauses.append("repo = ?")
            params.append(repo)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM activities {where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [Activity.from_row(r) for r in rows]

    def query_date(self, target_date: date) -> List[Activity]:
        """Return all activities for a given calendar date."""
        start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
        end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59)
        return self.query(start=start, end=end)

    def query_date_range(self, start_date: date, end_date: date) -> List[Activity]:
        """Return all activities between start_date and end_date (inclusive)."""
        start = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
        end = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
        return self.query(start=start, end=end)

    def query_since(self, days: int) -> List[Activity]:
        """Return activities from the last *days* days."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        return self.query(start=start_date, end=end_date)

    def count(self, activity_type: Optional[str] = None) -> int:
        """Return total number of stored activities, optionally filtered by type."""
        if activity_type:
            sql = "SELECT COUNT(*) FROM activities WHERE type = ?"
            params: tuple = (activity_type,)
        else:
            sql = "SELECT COUNT(*) FROM activities"
            params = ()
        with self._conn() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row[0]) if row else 0

    def repos(self) -> List[str]:
        """Return a sorted list of distinct repo paths that have activity."""
        with self._conn() as conn:
            rows = conn.execute("SELECT DISTINCT repo FROM activities WHERE repo != '' ORDER BY repo").fetchall()
        return [r["repo"] for r in rows]
