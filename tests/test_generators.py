"""
Tests for standup, weekly, and blog generators.
"""

import json
from datetime import date, timedelta

from dev_journal.generators.blog import BlogGenerator, _auto_title, _slugify
from dev_journal.generators.standup import StandupGenerator
from dev_journal.generators.weekly import WeeklyGenerator, _week_bounds
from dev_journal.storage import ActivityStorage
from tests.conftest import make_commit

# ------------------------------------------------------------------ #
# Helper functions                                                      #
# ------------------------------------------------------------------ #


def test_week_bounds_monday() -> None:
    """_week_bounds returns correct Monday-Sunday range."""
    wednesday = date(2026, 2, 18)  # a Wednesday
    monday, sunday = _week_bounds(wednesday)
    assert monday == date(2026, 2, 16)
    assert sunday == date(2026, 2, 22)
    assert monday.weekday() == 0  # Monday
    assert sunday.weekday() == 6  # Sunday


def test_week_bounds_default_is_current_week() -> None:
    monday, sunday = _week_bounds()
    assert monday.weekday() == 0
    assert sunday.weekday() == 6
    assert sunday - monday == timedelta(days=6)


def test_slugify_basic() -> None:
    assert _slugify("Hello World!") == "hello-world"


def test_slugify_special_chars() -> None:
    slug = _slugify("feat: Add Login & Auth (OAuth2)")
    assert " " not in slug
    assert "(" not in slug
    assert "&" not in slug


def test_slugify_truncates_long_titles() -> None:
    long_title = "a" * 100
    assert len(_slugify(long_title)) <= 80


# ------------------------------------------------------------------ #
# StandupGenerator                                                      #
# ------------------------------------------------------------------ #


def test_standup_markdown_output(storage: ActivityStorage) -> None:
    """Standup markdown output contains expected sections."""
    storage.insert_many(
        [
            make_commit(subject="feat: add profile page", intent="feature", days_ago=1),
            make_commit(subject="fix: correct date parsing", intent="fix", days_ago=1),
        ]
    )

    gen = StandupGenerator(storage)
    output = gen.generate(target_date=date.today(), output_format="markdown")

    assert "## Daily Standup" in output
    assert "### What I did yesterday:" in output
    assert "### What I'm working on today:" in output
    assert "### Blockers:" in output
    assert "feat: add profile page" in output or "profile page" in output


def test_standup_text_output(storage: ActivityStorage) -> None:
    """Standup text output contains plain-text section headers."""
    storage.insert(make_commit(days_ago=1))
    gen = StandupGenerator(storage)
    output = gen.generate(target_date=date.today(), output_format="text")

    assert "DAILY STANDUP" in output
    assert "WHAT I DID YESTERDAY:" in output
    assert "WHAT I'M WORKING ON TODAY:" in output
    assert "BLOCKERS:" in output


def test_standup_json_output(storage: ActivityStorage) -> None:
    """Standup JSON output is valid JSON with expected keys."""
    storage.insert(make_commit(days_ago=1))
    gen = StandupGenerator(storage)
    raw = gen.generate(target_date=date.today(), output_format="json")
    data = json.loads(raw)

    assert "yesterday_items" in data
    assert "today_plan" in data
    assert "blockers" in data
    assert "stats" in data


def test_standup_no_activity(storage: ActivityStorage) -> None:
    """Standup with no recorded activity mentions no activity."""
    gen = StandupGenerator(storage)
    output = gen.generate(target_date=date.today(), output_format="markdown")

    assert "No recorded activity" in output


def test_standup_blockers_detection(storage: ActivityStorage) -> None:
    """Standup detects WIP/broken commits as blockers."""
    storage.insert(make_commit(subject="WIP: broken login flow", intent="fix", days_ago=1))
    gen = StandupGenerator(storage)
    output = gen.generate(target_date=date.today(), output_format="markdown")

    assert "### Blockers:" in output
    blockers_section = output.split("### Blockers:")[1]
    assert "broken login flow" in blockers_section or "WIP" in blockers_section or "None" not in blockers_section


def test_standup_with_open_branches(storage: ActivityStorage) -> None:
    """Open branches are reflected in today's plan."""
    storage.insert(make_commit(days_ago=1))
    gen = StandupGenerator(storage)
    output = gen.generate(
        target_date=date.today(),
        output_format="markdown",
        open_branches=["feature/new-dashboard"],
    )
    assert "new-dashboard" in output or "feature/new-dashboard" in output


# ------------------------------------------------------------------ #
# WeeklyGenerator                                                       #
# ------------------------------------------------------------------ #


def test_weekly_markdown_output(storage: ActivityStorage) -> None:
    """Weekly markdown output contains correct sections."""
    from datetime import datetime as dt

    # Insert all commits inside the same known week (Mon Feb 16 .. Sun Feb 22, 2026)
    monday = date(2026, 2, 16)
    for offset in range(6):
        c = make_commit(repo="my-app")
        c.timestamp = dt(2026, 2, 16 + offset, 12, 0)
        storage.insert(c)

    gen = WeeklyGenerator(storage)
    output = gen.generate(week_of=monday, output_format="markdown")

    assert "Weekly Sprint Summary" in output
    assert "Overview" in output
    assert "Highlights" in output or "Per-Repository" in output
    assert "my-app" in output


def test_weekly_json_contains_stats(storage: ActivityStorage) -> None:
    """Weekly JSON output contains all expected stat keys."""
    # Use a fixed Monday so all commits fall inside the same ISO week
    from datetime import datetime as dt

    monday = date(2026, 2, 16)
    for i in range(3):
        c = make_commit()
        c.timestamp = dt(2026, 2, 17 + i, 10, 0)  # Tue/Wed/Thu of that week
        storage.insert(c)

    gen = WeeklyGenerator(storage)
    raw = gen.generate(week_of=monday, output_format="json")
    data = json.loads(raw)

    assert data["total_commits"] == 3
    assert "repo_stats" in data
    assert "highlights" in data
    assert "daily_commits" in data
    assert "intent_counts" in data


def test_weekly_empty_storage(storage: ActivityStorage) -> None:
    """Weekly generator handles an empty journal without errors."""
    gen = WeeklyGenerator(storage)
    output = gen.generate(output_format="markdown")
    assert "Weekly Sprint Summary" in output
    assert "0" in output


# ------------------------------------------------------------------ #
# BlogGenerator                                                         #
# ------------------------------------------------------------------ #


def test_blog_markdown_has_frontmatter(storage: ActivityStorage) -> None:
    """Blog markdown output starts with Dev.to YAML frontmatter."""
    storage.insert_many([make_commit(days_ago=i) for i in range(3)])
    gen = BlogGenerator(storage)
    output = gen.generate(days=7, output_format="markdown")

    assert output.startswith("---")
    assert "title:" in output
    assert "published: false" in output
    assert "tags:" in output


def test_blog_contains_stats(storage: ActivityStorage) -> None:
    """Blog draft includes commit and line stats."""
    storage.insert(make_commit(insertions=200, deletions=50, files_changed=10))
    gen = BlogGenerator(storage)
    output = gen.generate(days=1, output_format="markdown")

    assert "commit" in output.lower()
    assert "200" in output or "+200" in output


def test_blog_custom_title(storage: ActivityStorage) -> None:
    """Custom title is used in the generated output."""
    storage.insert(make_commit())
    gen = BlogGenerator(storage)
    output = gen.generate(days=1, title="My Awesome Week", output_format="markdown")

    assert "My Awesome Week" in output


def test_blog_json_output(storage: ActivityStorage) -> None:
    """Blog JSON output is valid JSON with expected keys."""
    storage.insert(make_commit())
    gen = BlogGenerator(storage)
    raw = gen.generate(days=1, output_format="json")
    data = json.loads(raw)

    assert "title" in data
    assert "total_commits" in data
    assert "sections" in data
    assert "highlights" in data


def test_blog_includes_whats_next_section(storage: ActivityStorage) -> None:
    """Blog draft has placeholder sections for polishing."""
    storage.insert(make_commit())
    gen = BlogGenerator(storage)
    output = gen.generate(days=1, output_format="markdown")

    assert "What's Next" in output
    assert "Lessons Learned" in output


def test_blog_auto_title_from_highlights(storage: ActivityStorage) -> None:
    """Auto-title uses the top commit subject."""
    storage.insert(make_commit(subject="feat: implement rate limiting", repo="api-service"))
    gen = BlogGenerator(storage)
    data = gen._build_data(
        storage.query_since(1),
        start_date=date.today() - timedelta(days=1),
        end_date=date.today(),
    )
    data["date_start"] = str(date.today() - timedelta(days=7))
    data["date_end"] = str(date.today())
    title = _auto_title(data)

    assert title  # non-empty
    assert "Dev Log" in title or "rate limiting" in title or "api-service" in title
