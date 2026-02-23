"""
Weekly sprint summary generator.

Aggregates a full week of Activity objects into a sprint-review-friendly
report with commit stats, file changes, highlights, and per-repo breakdowns.
"""

import json
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from dev_journal.storage import Activity, ActivityStorage

logger = logging.getLogger(__name__)


def _week_bounds(ref_date: Optional[date] = None) -> Tuple[date, date]:
    """Return (Monday, Sunday) of the ISO week containing *ref_date*."""
    if ref_date is None:
        ref_date = date.today()
    monday = ref_date - timedelta(days=ref_date.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _highlight_commits(commits: List[Activity]) -> List[str]:
    """Pick the most significant commits to call out as highlights."""
    scored: List[Tuple[int, Activity]] = []
    for c in commits:
        score = 0
        subject = c.details.get("subject", "")
        ins = c.details.get("insertions", 0)
        dels = c.details.get("deletions", 0)
        fc = c.details.get("files_changed", 0)
        # Large commits
        score += min(ins + dels, 500) // 50
        score += min(fc, 20)
        # Meaningful intent
        if c.details.get("intent") in ("feature", "fix"):
            score += 3
        # Not a chore
        if c.details.get("intent") == "chore":
            score -= 1
        # Not a WIP
        if "wip" not in subject.lower():
            score += 1
        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    highlights: List[str] = []
    seen: set = set()
    for _, c in scored[:5]:
        subject = c.details.get("subject", c.summary)
        if subject not in seen:
            highlights.append(f"[{c.repo}] {subject}")
            seen.add(subject)
    return highlights


class WeeklyGenerator:
    """Generate weekly sprint summaries from stored activities."""

    def __init__(self, storage: ActivityStorage):
        self.storage = storage

    def generate(
        self,
        week_of: Optional[date] = None,
        output_format: str = "markdown",
    ) -> str:
        """
        Generate a weekly summary.

        Parameters
        ----------
        week_of:       Any date inside the target week (default: current week)
        output_format: "text", "markdown", or "json"
        """
        start_date, end_date = _week_bounds(week_of)
        activities = self.storage.query_date_range(start_date, end_date)
        data = self._build_data(activities, start_date, end_date)

        if output_format == "json":
            return json.dumps(data, indent=2, default=str)
        elif output_format == "text":
            return self._render_text(data)
        else:
            return self._render_markdown(data)

    def _build_data(
        self,
        activities: List[Activity],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        commits = [a for a in activities if a.type == "git_commit"]
        files = [a for a in activities if a.type == "file_change"]
        shell_cmds = [a for a in activities if a.type == "shell_command"]

        # Aggregate stats
        total_insertions = sum(c.details.get("insertions", 0) for c in commits)
        total_deletions = sum(c.details.get("deletions", 0) for c in commits)
        total_files_changed = sum(c.details.get("files_changed", 0) for c in commits)

        # Per-repo breakdown
        repo_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"commits": 0, "insertions": 0, "deletions": 0, "files_changed": 0, "intents": defaultdict(int)}
        )
        for c in commits:
            repo = c.repo or "unknown"
            repo_stats[repo]["commits"] += 1
            repo_stats[repo]["insertions"] += c.details.get("insertions", 0)
            repo_stats[repo]["deletions"] += c.details.get("deletions", 0)
            repo_stats[repo]["files_changed"] += c.details.get("files_changed", 0)
            intent = c.details.get("intent", "feature")
            repo_stats[repo]["intents"][intent] += 1

        # Convert defaultdicts to plain dicts for JSON serialization
        repo_stats_clean: Dict[str, Any] = {}
        for repo, stats in repo_stats.items():
            repo_stats_clean[repo] = {
                "commits": stats["commits"],
                "insertions": stats["insertions"],
                "deletions": stats["deletions"],
                "files_changed": stats["files_changed"],
                "intents": dict(stats["intents"]),
            }

        # Intent breakdown across all commits
        intent_counts: Dict[str, int] = defaultdict(int)
        for c in commits:
            intent_counts[c.details.get("intent", "feature")] += 1

        # Daily activity heatmap
        daily_commits: Dict[str, int] = defaultdict(int)
        for c in commits:
            day_str = c.timestamp.date().isoformat()
            daily_commits[day_str] += 1

        # File type breakdown
        lang_counts: Dict[str, int] = defaultdict(int)
        for f in files:
            lang_counts[f.details.get("language", "Unknown")] += 1

        highlights = _highlight_commits(commits)

        # Most active day
        most_active_day = ""
        if daily_commits:
            most_active_day = max(daily_commits.items(), key=lambda x: x[1])[0]

        return {
            "week_start": str(start_date),
            "week_end": str(end_date),
            "total_commits": len(commits),
            "total_insertions": total_insertions,
            "total_deletions": total_deletions,
            "total_files_changed": total_files_changed,
            "total_file_modifications": len(files),
            "total_shell_commands": len(shell_cmds),
            "repos_touched": list(repo_stats_clean.keys()),
            "repo_stats": repo_stats_clean,
            "intent_counts": dict(intent_counts),
            "daily_commits": dict(daily_commits),
            "language_counts": dict(sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)),
            "highlights": highlights,
            "most_active_day": most_active_day,
        }

    def _render_markdown(self, data: Dict[str, Any]) -> str:
        from datetime import datetime

        start_fmt = datetime.strptime(data["week_start"], "%Y-%m-%d").strftime("%B %-d")
        end_fmt = datetime.strptime(data["week_end"], "%Y-%m-%d").strftime("%B %-d, %Y")

        lines: List[str] = [
            f"# Weekly Sprint Summary — {start_fmt}–{end_fmt}",
            "",
            "## Overview",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Commits | {data['total_commits']} |",
            f"| Lines added | +{data['total_insertions']} |",
            f"| Lines removed | -{data['total_deletions']} |",
            f"| Files changed | {data['total_files_changed']} |",
            f"| Repos touched | {len(data['repos_touched'])} |",
        ]
        if data.get("most_active_day"):
            from datetime import datetime as dt

            most_active_fmt = dt.strptime(data["most_active_day"], "%Y-%m-%d").strftime("%A, %B %-d")
            commit_count = data["daily_commits"].get(data["most_active_day"], 0)
            lines.append(f"| Most active day | {most_active_fmt} ({commit_count} commits) |")
        lines.append("")

        if data["highlights"]:
            lines += ["## Highlights", ""]
            for h in data["highlights"]:
                lines.append(f"- {h}")
            lines.append("")

        if data["repo_stats"]:
            lines += ["## Per-Repository Breakdown", ""]
            for repo, stats in sorted(data["repo_stats"].items(), key=lambda x: x[1]["commits"], reverse=True):
                lines.append(f"### `{repo}`")
                lines.append(f"- Commits: {stats['commits']}")
                lines.append(f"- Lines: +{stats['insertions']}/-{stats['deletions']}")
                lines.append(f"- Files changed: {stats['files_changed']}")
                intents = stats.get("intents", {})
                if intents:
                    intent_str = ", ".join(f"{k}: {v}" for k, v in sorted(intents.items()))
                    lines.append(f"- Work type: {intent_str}")
                lines.append("")

        if data["intent_counts"]:
            lines += ["## Work Type Breakdown", ""]
            total = sum(data["intent_counts"].values()) or 1
            for intent, count in sorted(data["intent_counts"].items(), key=lambda x: x[1], reverse=True):
                pct = int(count / total * 100)
                bar = "#" * (pct // 5)
                lines.append(f"- **{intent.capitalize()}**: {count} commits ({pct}%) `{bar}`")
            lines.append("")

        if data["daily_commits"]:
            from datetime import datetime as dt

            lines += ["## Daily Activity", ""]
            for day_str in sorted(data["daily_commits"].keys()):
                day_fmt = dt.strptime(day_str, "%Y-%m-%d").strftime("%a %b %-d")
                count = data["daily_commits"][day_str]
                bar = "*" * count
                lines.append(f"- {day_fmt}: {bar} ({count})")
            lines.append("")

        return "\n".join(lines)

    def _render_text(self, data: Dict[str, Any]) -> str:
        from datetime import datetime

        start_fmt = datetime.strptime(data["week_start"], "%Y-%m-%d").strftime("%b %-d")
        end_fmt = datetime.strptime(data["week_end"], "%Y-%m-%d").strftime("%b %-d, %Y")

        lines: List[str] = [
            f"WEEKLY SPRINT SUMMARY — {start_fmt} to {end_fmt}",
            "=" * 50,
            "",
            f"Total commits:     {data['total_commits']}",
            f"Lines added:       +{data['total_insertions']}",
            f"Lines removed:     -{data['total_deletions']}",
            f"Files changed:     {data['total_files_changed']}",
            f"Repos touched:     {', '.join(data['repos_touched']) or 'none'}",
            "",
        ]

        if data["highlights"]:
            lines += ["HIGHLIGHTS:", ""]
            for h in data["highlights"]:
                lines.append(f"  * {h}")
            lines.append("")

        if data["repo_stats"]:
            lines.append("PER-REPO STATS:")
            for repo, stats in sorted(data["repo_stats"].items(), key=lambda x: x[1]["commits"], reverse=True):
                lines.append(f"  {repo}: {stats['commits']} commits, +{stats['insertions']}/-{stats['deletions']}")
            lines.append("")

        return "\n".join(lines)
