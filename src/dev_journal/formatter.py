"""
Rich terminal output formatting for dev-journal.

Provides helper functions for tables, panels, progress bars,
and color-coded timeline views using the ``rich`` library.
"""

import logging
from typing import Any, Dict, List, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from dev_journal.storage import Activity

logger = logging.getLogger(__name__)

# Color map for activity types
_TYPE_COLORS: Dict[str, str] = {
    "git_commit": "bright_green",
    "file_change": "bright_blue",
    "shell_command": "bright_yellow",
}

# Color map for commit intents
_INTENT_COLORS: Dict[str, str] = {
    "feature": "green",
    "fix": "red",
    "refactor": "cyan",
    "docs": "blue",
    "test": "magenta",
    "chore": "yellow",
    "edit": "white",
}

_THEME = Theme(
    {
        "title": "bold bright_cyan",
        "subtitle": "dim white",
        "highlight": "bold yellow",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "info": "dim cyan",
        "git": "bright_green",
        "file": "bright_blue",
        "shell": "bright_yellow",
        "repo": "bold magenta",
    }
)

console = Console(theme=_THEME)


def get_console() -> Console:
    """Return the shared Rich console instance."""
    return console


def print_title(text: str, subtitle: Optional[str] = None) -> None:
    """Print a styled title panel."""
    content = Text(text, style="title")
    if subtitle:
        content.append(f"\n{subtitle}", style="subtitle")
    console.print(Panel(content, box=box.DOUBLE_EDGE, padding=(0, 2)))


def print_success(message: str) -> None:
    console.print(f"[success]OK[/success]  {message}")


def print_warning(message: str) -> None:
    console.print(f"[warning]WARN[/warning]  {message}")


def print_error(message: str) -> None:
    console.print(f"[error]ERR[/error]  {message}")


def print_info(message: str) -> None:
    console.print(f"[info]INFO[/info]  {message}")


def format_activity_type(activity_type: str) -> Text:
    """Return a colored Text label for an activity type."""
    labels = {
        "git_commit": "GIT",
        "file_change": "FILE",
        "shell_command": "SHELL",
    }
    color = _TYPE_COLORS.get(activity_type, "white")
    return Text(labels.get(activity_type, activity_type.upper()[:5]), style=f"bold {color}")


def format_intent(intent: str) -> Text:
    """Return a colored Text label for a commit intent."""
    color = _INTENT_COLORS.get(intent, "white")
    return Text(intent.upper()[:7], style=color)


def render_timeline(activities: List[Activity], days: int = 7) -> None:
    """
    Render a color-coded activity timeline table in the terminal.

    Parameters
    ----------
    activities: List of Activity objects to display
    days:       Number of days the timeline covers (used in the title)
    """
    if not activities:
        console.print(Panel("[dim]No activity recorded for this period.[/dim]", title="Timeline"))
        return

    table = Table(
        title=f"Activity Timeline — Last {days} Day{'s' if days != 1 else ''}",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold cyan",
        min_width=80,
    )

    table.add_column("Time", style="dim", width=18, no_wrap=True)
    table.add_column("Type", width=7, justify="center")
    table.add_column("Repo", style="repo", width=16, no_wrap=True)
    table.add_column("Summary", min_width=40)

    current_day: Optional[str] = None

    for activity in sorted(activities, key=lambda a: a.timestamp, reverse=True):
        day_str = activity.timestamp.strftime("%a %b %-d")
        time_str = activity.timestamp.strftime("%H:%M")

        if day_str != current_day:
            # Day separator row
            table.add_section()
            table.add_row(
                Text(f"-- {day_str} --", style="bold white"),
                Text(""),
                Text(""),
                Text(""),
            )
            current_day = day_str

        type_cell = format_activity_type(activity.type)

        summary = activity.summary
        if activity.type == "git_commit":
            subject = activity.details.get("subject", summary)
            intent = activity.details.get("intent", "feature")
            ins = activity.details.get("insertions", 0)
            dels = activity.details.get("deletions", 0)
            intent_label = format_intent(intent)
            summary_text = Text()
            summary_text.append(f"{subject[:55]}", style="white")
            summary_text.append("  ")
            summary_text.append(intent_label)
            summary_text.append(f" +{ins}/-{dels}", style="dim")
        elif activity.type == "file_change":
            path = activity.details.get("path", summary)
            lang = activity.details.get("language", "")
            summary_text = Text()
            summary_text.append(path[:55], style="bright_blue")
            if lang:
                summary_text.append(f"  [{lang}]", style="dim")
        elif activity.type == "shell_command":
            cmd = activity.details.get("command", summary)
            summary_text = Text(cmd[:70], style="bright_yellow")
        else:
            summary_text = Text(summary[:70])

        table.add_row(
            f"{time_str}",
            type_cell,
            (activity.repo or "—")[:16],
            summary_text,
        )

    console.print(table)


def render_stats_panel(stats: Dict[str, Any], title: str = "Stats") -> None:
    """Render a compact statistics panel."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim")
    grid.add_column(style="bold")

    for key, value in stats.items():
        grid.add_row(key, str(value))

    console.print(Panel(grid, title=f"[title]{title}[/title]", box=box.ROUNDED))


def render_progress_bars(items: Dict[str, int], title: str, total: Optional[int] = None) -> None:
    """Render a set of labeled progress bars."""
    if not items:
        return

    max_val = total or max(items.values(), default=1)
    if max_val == 0:
        max_val = 1

    console.print(f"\n[title]{title}[/title]")
    with Progress(
        TextColumn("[progress.description]{task.description}", justify="right"),
        BarColumn(bar_width=30),
        TextColumn("{task.completed}"),
        console=console,
        transient=False,
    ) as progress:
        for label, value in sorted(items.items(), key=lambda x: x[1], reverse=True):
            task = progress.add_task(label[:20], total=max_val, completed=value)
            _ = task  # suppress unused variable warning


def render_standup(content: str, output_format: str = "markdown") -> None:
    """Print standup output with optional Rich rendering."""
    if output_format == "markdown":
        from rich.markdown import Markdown

        console.print(Markdown(content))
    else:
        console.print(content)


def render_weekly(content: str, output_format: str = "markdown") -> None:
    """Print weekly summary with optional Rich rendering."""
    if output_format == "markdown":
        from rich.markdown import Markdown

        console.print(Markdown(content))
    else:
        console.print(content)


def render_blog(content: str) -> None:
    """Print blog draft with Rich markdown rendering."""
    from rich.markdown import Markdown
    from rich.syntax import Syntax

    # Show frontmatter as a syntax block
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            frontmatter = content[: end + 3]
            body = content[end + 3 :]
            console.print(Syntax(frontmatter, "yaml", theme="monokai"))
            console.print(Markdown(body))
            return
    console.print(Markdown(content))
