"""
Blog post draft generator.

Turns a week (or N days) of coding activity into a Dev.to-compatible
Markdown article with frontmatter. No AI required — it produces a
structured draft that the developer can fill in and polish.
"""

import json
import logging
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from dev_journal.storage import Activity, ActivityStorage

logger = logging.getLogger(__name__)

# Map commit intent to narrative verb phrases
_INTENT_VERBS: Dict[str, str] = {
    "feature": "implemented",
    "fix": "fixed",
    "refactor": "refactored",
    "docs": "documented",
    "test": "added tests for",
    "chore": "updated",
}


def _slugify(title: str) -> str:
    """Convert a title to a URL slug."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug.strip())
    return slug[:80]


def _auto_title(data: Dict[str, Any]) -> str:
    """Generate a descriptive title from the week's activity data."""
    repos = data.get("repos_touched", [])
    highlights = data.get("highlights", [])
    start = data.get("date_start", "")
    end = data.get("date_end", "")

    start_fmt = datetime.strptime(start, "%Y-%m-%d").strftime("%b %-d") if start else ""
    end_fmt = datetime.strptime(end, "%Y-%m-%d").strftime("%b %-d, %Y") if end else ""
    date_range = f"{start_fmt}–{end_fmt}" if start_fmt and end_fmt else ""

    if highlights:
        # Extract meaningful words from the top highlight
        first = highlights[0]
        # Strip [repo] prefix
        first = re.sub(r"^\[.+?\]\s*", "", first)
        first = first[:60]
        if date_range:
            return f"Dev Log: {first} ({date_range})"
        return f"Dev Log: {first}"

    if repos:
        repo_str = " & ".join(repos[:2])
        if date_range:
            return f"Dev Log: {repo_str} — {date_range}"
        return f"Dev Log: {repo_str}"

    return f"Dev Log — {date_range}" if date_range else "Dev Log"


class BlogGenerator:
    """Generate a Dev.to-compatible blog post draft from stored activities."""

    def __init__(self, storage: ActivityStorage):
        self.storage = storage

    def generate(
        self,
        days: int = 7,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        author: str = "",
        output_format: str = "markdown",
    ) -> str:
        """
        Generate a blog post draft.

        Parameters
        ----------
        days:          Number of past days to include
        title:         Override auto-generated title
        tags:          Dev.to tags (max 4)
        author:        Author name for the byline
        output_format: "markdown" or "json"
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)
        activities = self.storage.query_date_range(start_date, end_date)

        data = self._build_data(activities, start_date, end_date)

        if title:
            data["title"] = title
        else:
            data["title"] = _auto_title(data)

        data["slug"] = _slugify(data["title"])
        data["tags"] = (tags or ["programming", "productivity", "devlog"])[:4]
        data["author"] = author

        if output_format == "json":
            return json.dumps(data, indent=2, default=str)
        return self._render_markdown(data)

    def _build_data(
        self,
        activities: List[Activity],
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        commits = [a for a in activities if a.type == "git_commit"]
        files = [a for a in activities if a.type == "file_change"]

        # Stats
        total_insertions = sum(c.details.get("insertions", 0) for c in commits)
        total_deletions = sum(c.details.get("deletions", 0) for c in commits)
        total_files = sum(c.details.get("files_changed", 0) for c in commits)

        repos_touched = sorted({c.repo for c in commits if c.repo})

        # Group commits by repo and intent
        by_repo: Dict[str, List[Activity]] = defaultdict(list)
        for c in commits:
            by_repo[c.repo or "unknown"].append(c)

        intent_counts: Dict[str, int] = defaultdict(int)
        for c in commits:
            intent_counts[c.details.get("intent", "feature")] += 1

        # Notable commits (highest impact)
        def _impact_score(c: Activity) -> int:
            return (
                c.details.get("insertions", 0) + c.details.get("deletions", 0) + c.details.get("files_changed", 0) * 5
            )

        notable = sorted(commits, key=_impact_score, reverse=True)[:8]

        # Build narrative sections
        sections: List[Dict[str, Any]] = []
        for repo, repo_commits in sorted(by_repo.items()):
            by_intent: Dict[str, List[str]] = defaultdict(list)
            for c in repo_commits:
                intent = c.details.get("intent", "feature")
                by_intent[intent].append(c.details.get("subject", c.summary))

            bullet_groups: List[Dict[str, Any]] = []
            for intent, subjects in by_intent.items():
                verb = _INTENT_VERBS.get(intent, "worked on")
                bullet_groups.append(
                    {
                        "intent": intent,
                        "verb": verb,
                        "items": subjects[:6],
                    }
                )
            sections.append(
                {
                    "repo": repo,
                    "commit_count": len(repo_commits),
                    "bullet_groups": bullet_groups,
                }
            )

        # Language breakdown from file changes
        lang_counts: Dict[str, int] = defaultdict(int)
        for f in files:
            lang_counts[f.details.get("language", "Unknown")] += 1

        highlights: List[str] = []
        for c in notable[:5]:
            repo = c.repo
            subject = c.details.get("subject", "")
            ins = c.details.get("insertions", 0)
            dels = c.details.get("deletions", 0)
            highlights.append(f"[{repo}] {subject} (+{ins}/-{dels})")

        return {
            "date_start": str(start_date),
            "date_end": str(end_date),
            "total_commits": len(commits),
            "total_insertions": total_insertions,
            "total_deletions": total_deletions,
            "total_files_changed": total_files,
            "repos_touched": repos_touched,
            "sections": sections,
            "highlights": highlights,
            "intent_counts": dict(intent_counts),
            "language_counts": dict(sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)[:6]),
        }

    def _render_markdown(self, data: Dict[str, Any]) -> str:
        title = data["title"]
        tags = data.get("tags", [])
        author = data.get("author", "")

        start_fmt = datetime.strptime(data["date_start"], "%Y-%m-%d").strftime("%B %-d")
        end_fmt = datetime.strptime(data["date_end"], "%Y-%m-%d").strftime("%B %-d, %Y")

        tag_list = ", ".join(tags)

        lines: List[str] = [
            "---",
            f"title: {title}",
            "published: false",
            f"description: A developer log covering my coding work from {start_fmt} to {end_fmt}.",
            f"tags: {tag_list}",
            "cover_image:",
            "---",
            "",
            f"# {title}",
            "",
        ]

        if author:
            lines.append(f"*By {author} | {start_fmt}–{end_fmt}*")
        else:
            lines.append(f"*{start_fmt}–{end_fmt}*")
        lines.append("")

        # Intro
        repos_str = ", ".join(f"`{r}`" for r in data["repos_touched"]) if data["repos_touched"] else "various projects"
        lines += [
            "## What I Built This Week",
            "",
            f"This week I worked across {repos_str}. Here's a summary of what I shipped:",
            "",
            f"- **{data['total_commits']}** commits",
            f"- **+{data['total_insertions']}** lines added, **-{data['total_deletions']}** lines removed",
            f"- **{data['total_files_changed']}** files changed",
            "",
        ]

        # Highlights
        if data["highlights"]:
            lines += ["## Highlights", ""]
            for h in data["highlights"]:
                lines.append(f"- {h}")
            lines.append("")

        # Per-repo narrative sections
        if data["sections"]:
            lines += ["## Deep Dive", ""]
            for section in data["sections"]:
                repo = section["repo"]
                count = section["commit_count"]
                lines.append(f"### `{repo}` ({count} commit{'s' if count != 1 else ''})")
                lines.append("")

                for group in section["bullet_groups"]:
                    verb = group["verb"].capitalize()
                    items = group["items"]
                    lines.append(f"**{verb}:**")
                    for item in items:
                        lines.append(f"- {item}")
                    lines.append("")

        # Work type breakdown
        if data["intent_counts"]:
            lines += ["## Work Type Breakdown", ""]
            total = sum(data["intent_counts"].values()) or 1
            for intent, count in sorted(data["intent_counts"].items(), key=lambda x: x[1], reverse=True):
                pct = int(count / total * 100)
                lines.append(f"- **{intent.capitalize()}**: {count} commits ({pct}%)")
            lines.append("")

        # Languages used
        if data["language_counts"]:
            lines += ["## Languages & Technologies", ""]
            for lang, count in data["language_counts"].items():
                lines.append(f"- {lang}: {count} file modification{'s' if count != 1 else ''}")
            lines.append("")

        # What's next / conclusion placeholder
        lines += [
            "## What's Next",
            "",
            "> *[Add what you plan to work on next week here]*",
            "",
            "## Lessons Learned",
            "",
            "> *[Add any interesting insights, tricky bugs, or useful techniques you discovered]*",
            "",
            "---",
            "",
            (
                "*Generated with [dev-journal](https://github.com/sravyalu/dev-journal)"
                " \u2014 your work log that writes itself.*"
            ),
        ]

        return "\n".join(lines)
