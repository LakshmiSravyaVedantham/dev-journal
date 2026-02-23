"""
Daily standup note generator.

Produces "What I did yesterday / What I'm doing today / Blockers" summaries
from stored Activity objects. Supports text, markdown, and JSON output formats.
"""

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from dev_journal.storage import Activity, ActivityStorage

logger = logging.getLogger(__name__)


def _group_by_repo(activities: List[Activity]) -> Dict[str, List[Activity]]:
    groups: Dict[str, List[Activity]] = defaultdict(list)
    for a in activities:
        groups[a.repo or "general"].append(a)
    return dict(groups)


def _infer_blockers(activities: List[Activity]) -> List[str]:
    """
    Heuristically detect blockers from activity details.

    Current signals:
    - shell commands that returned non-zero (not captured yet, placeholder)
    - commit messages with "wip", "broken", "todo", "fixme"
    """
    blockers: List[str] = []
    for a in activities:
        if a.type == "git_commit":
            msg = a.details.get("subject", "").lower()
            if any(kw in msg for kw in ("wip", "broken", "fixme", "hack", "todo", "not working")):
                blockers.append(f"Unfinished work in [{a.repo}]: {a.details.get('subject', '')}")
    return blockers


def _infer_today_plan(activities: List[Activity], open_branches: Optional[List[str]] = None) -> List[str]:
    """
    Infer what the developer might work on today.

    Uses open branches and recent partial-work commits as signals.
    """
    plan: List[str] = []
    seen: set = set()

    if open_branches:
        for branch in open_branches[:3]:
            hint = branch.replace("-", " ").replace("_", " ").capitalize()
            if hint not in seen:
                plan.append(f"Continue work on branch: {branch}")
                seen.add(hint)

    for a in activities:
        if a.type == "git_commit":
            subject = a.details.get("subject", "")
            intent = a.details.get("intent", "feature")
            if intent == "fix" and subject not in seen:
                plan.append(f"Verify fix: {subject}")
                seen.add(subject)
            elif intent == "feature" and "wip" in subject.lower() and subject not in seen:
                plan.append(f"Continue: {subject.replace('WIP', '').replace('wip', '').strip()}")
                seen.add(subject)

    if not plan:
        plan.append("Review open pull requests and address feedback")
        plan.append("Continue work from yesterday")

    return plan[:5]


class StandupGenerator:
    """Generate daily standup notes from stored activities."""

    def __init__(self, storage: ActivityStorage):
        self.storage = storage

    def generate(
        self,
        target_date: Optional[date] = None,
        output_format: str = "markdown",
        open_branches: Optional[List[str]] = None,
        max_commits: int = 10,
        max_files: int = 15,
    ) -> str:
        """
        Generate standup notes for the day *before* target_date.

        Parameters
        ----------
        target_date:   The "today" reference date (default: today)
        output_format: "text", "markdown", or "json"
        open_branches: List of open branch names (for today's plan)
        max_commits:   Max commits to include
        max_files:     Max files to mention
        """
        if target_date is None:
            target_date = date.today()

        yesterday = target_date - timedelta(days=1)
        activities = self.storage.query_date(yesterday)

        data = self._build_data(
            activities,
            yesterday,
            target_date,
            open_branches or [],
            max_commits,
            max_files,
        )

        if output_format == "json":
            return json.dumps(data, indent=2, default=str)
        elif output_format == "text":
            return self._render_text(data)
        else:
            return self._render_markdown(data)

    def _build_data(
        self,
        activities: List[Activity],
        yesterday: date,
        today: date,
        open_branches: List[str],
        max_commits: int,
        max_files: int,
    ) -> Dict[str, Any]:
        commits = [a for a in activities if a.type == "git_commit"][:max_commits]
        files = [a for a in activities if a.type == "file_change"][:max_files]
        shell_cmds = [a for a in activities if a.type == "shell_command"]

        by_repo = _group_by_repo(commits)
        blockers = _infer_blockers(activities)
        today_plan = _infer_today_plan(activities, open_branches)

        yesterday_items: List[Dict[str, Any]] = []
        for repo, repo_commits in by_repo.items():
            for c in repo_commits:
                yesterday_items.append(
                    {
                        "repo": repo,
                        "summary": c.details.get("subject", c.summary),
                        "files_changed": c.details.get("files_changed", 0),
                        "insertions": c.details.get("insertions", 0),
                        "deletions": c.details.get("deletions", 0),
                        "intent": c.details.get("intent", "feature"),
                        "hash": c.details.get("short_hash", ""),
                    }
                )

        # Add high-level file stats if no commits
        if not yesterday_items and files:
            langs: Dict[str, int] = defaultdict(int)
            for f in files:
                langs[f.details.get("language", "Unknown")] += 1
            for lang, count in sorted(langs.items(), key=lambda x: x[1], reverse=True)[:5]:
                yesterday_items.append(
                    {
                        "repo": "files",
                        "summary": f"Modified {count} {lang} file(s)",
                        "files_changed": count,
                        "insertions": 0,
                        "deletions": 0,
                        "intent": "edit",
                        "hash": "",
                    }
                )

        stats = {
            "total_commits": len(commits),
            "total_files_changed": sum(c.details.get("files_changed", 0) for c in commits),
            "total_insertions": sum(c.details.get("insertions", 0) for c in commits),
            "total_deletions": sum(c.details.get("deletions", 0) for c in commits),
            "repos_touched": list(by_repo.keys()),
            "shell_commands": len(shell_cmds),
        }

        return {
            "date_yesterday": str(yesterday),
            "date_today": str(today),
            "yesterday_items": yesterday_items,
            "today_plan": today_plan,
            "blockers": blockers,
            "stats": stats,
        }

    def _render_markdown(self, data: Dict[str, Any]) -> str:
        yesterday_dt = datetime.strptime(data["date_yesterday"], "%Y-%m-%d")
        today_dt = datetime.strptime(data["date_today"], "%Y-%m-%d")
        yesterday_fmt = yesterday_dt.strftime("%B %-d, %Y")
        today_fmt = today_dt.strftime("%B %-d, %Y")

        lines: List[str] = [
            f"## Daily Standup — {today_fmt}",
            "",
        ]

        lines.append("### What I did yesterday:")
        if data["yesterday_items"]:
            for item in data["yesterday_items"]:
                repo = item["repo"]
                summary = item["summary"]
                fc = item["files_changed"]
                ins = item["insertions"]
                dels = item["deletions"]
                hash_str = f" `{item['hash']}`" if item.get("hash") else ""
                lines.append(f"- **[{repo}]** {summary} ({fc} files, +{ins}/-{dels}){hash_str}")
        else:
            lines.append(f"- No recorded activity for {yesterday_fmt}")
        lines.append("")

        lines.append("### What I'm working on today:")
        for plan_item in data["today_plan"]:
            lines.append(f"- {plan_item}")
        lines.append("")

        lines.append("### Blockers:")
        if data["blockers"]:
            for blocker in data["blockers"]:
                lines.append(f"- {blocker}")
        else:
            lines.append("- None")
        lines.append("")

        stats = data["stats"]
        if stats["total_commits"] > 0:
            lines += [
                "---",
                f"*Stats: {stats['total_commits']} commits | "
                f"{stats['total_files_changed']} files | "
                f"+{stats['total_insertions']}/-{stats['total_deletions']} lines | "
                f"repos: {', '.join(stats['repos_touched'])}*",
            ]

        return "\n".join(lines)

    def _render_text(self, data: Dict[str, Any]) -> str:
        yesterday_dt = datetime.strptime(data["date_yesterday"], "%Y-%m-%d")
        today_dt = datetime.strptime(data["date_today"], "%Y-%m-%d")
        yesterday_fmt = yesterday_dt.strftime("%B %-d, %Y")
        today_fmt = today_dt.strftime("%B %-d, %Y")

        lines: List[str] = [
            f"DAILY STANDUP - {today_fmt}",
            "=" * 40,
            "",
            "WHAT I DID YESTERDAY:",
        ]

        if data["yesterday_items"]:
            for item in data["yesterday_items"]:
                fc = item["files_changed"]
                ins = item["insertions"]
                dels = item["deletions"]
                lines.append(f"  [{item['repo']}] {item['summary']} ({fc} files, +{ins}/-{dels})")
        else:
            lines.append(f"  No recorded activity for {yesterday_fmt}")
        lines.append("")

        lines.append("WHAT I'M WORKING ON TODAY:")
        for plan_item in data["today_plan"]:
            lines.append(f"  - {plan_item}")
        lines.append("")

        lines.append("BLOCKERS:")
        if data["blockers"]:
            for blocker in data["blockers"]:
                lines.append(f"  - {blocker}")
        else:
            lines.append("  None")

        return "\n".join(lines)
