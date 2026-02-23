"""
dev-journal CLI entry point.

Commands
--------
init       Initialize dev-journal for the current repo
collect    Manually collect recent activity
standup    Generate today's standup notes
weekly     Generate weekly sprint summary
blog       Generate a blog post draft
timeline   Show activity timeline
version    Show version information
"""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from dev_journal import __version__
from dev_journal.config import Config
from dev_journal.storage import ActivityStorage

logger = logging.getLogger("dev_journal")
err_console = Console(stderr=True)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _get_storage(config: Config) -> ActivityStorage:
    return ActivityStorage(config.db_path)


def _parse_date(value: Optional[str]) -> Optional[date]:
    """Parse a date string in YYYY-MM-DD format."""
    if value is None:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise click.BadParameter(f"Cannot parse date: {value!r}. Use YYYY-MM-DD format.")


# ====================================================================== #
# Root group                                                               #
# ====================================================================== #


@click.group()
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable verbose logging.")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """dev-journal — Your work log writes itself.

    Track git commits, file changes, and shell activity, then auto-generate
    daily standup notes, weekly sprint summaries, and blog post drafts.
    """
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["config"] = Config()


# ====================================================================== #
# init                                                                     #
# ====================================================================== #


@main.command()
@click.option("--repo", "-r", default=".", show_default=True, help="Path to the git repository to track.")
@click.option("--enable-shell-history", is_flag=True, default=False, help="Opt-in to shell history collection.")
@click.option("--history-path", default=None, help="Custom shell history file path.")
@click.pass_context
def init(ctx: click.Context, repo: str, enable_shell_history: bool, history_path: Optional[str]) -> None:
    """Initialize dev-journal for a repository.

    Creates ~/.dev-journal/ directory with config.toml and journal.db.
    """
    from dev_journal.formatter import print_info, print_success, print_title

    config: Config = ctx.obj["config"]

    print_title("dev-journal init", subtitle="Setting up your work log...")

    # Initialize config directory and file
    config.initialize()
    print_success(f"Config directory: {config.config_dir}")

    # Register repo
    repo_path = str(Path(repo).resolve())
    config.add_repo(repo_path)
    print_success(f"Tracking repo: {repo_path}")

    # Optionally enable shell history
    if enable_shell_history:
        config.enable_shell_history(history_path)
        hist_path = history_path or config.shell_history_path
        print_success(f"Shell history enabled: {hist_path}")
    else:
        print_info("Shell history collection is OFF (use --enable-shell-history to opt-in)")

    # Initialize database
    storage = _get_storage(config)
    print_success(f"Database: {config.db_path}")

    count = storage.count()
    print_info(f"Activities in journal: {count}")

    click.echo("")
    click.echo("Run 'dev-journal collect' to import your recent git activity.")


# ====================================================================== #
# collect                                                                  #
# ====================================================================== #


@main.command()
@click.option("--since", default=None, help="Collect since date (YYYY-MM-DD). Default: yesterday.")
@click.option("--repo", "-r", default=".", show_default=True, help="Repository path to collect from.")
@click.option("--no-files", is_flag=True, default=False, help="Skip file change collection.")
@click.option("--no-shell", is_flag=True, default=False, help="Skip shell history collection.")
@click.pass_context
def collect(
    ctx: click.Context,
    since: Optional[str],
    repo: str,
    no_files: bool,
    no_shell: bool,
) -> None:
    """Collect recent activity from git, files, and shell history.

    Stores results in the local SQLite journal database.
    """
    from dev_journal.collectors import FileCollector, GitCollector, ShellCollector
    from dev_journal.formatter import print_info, print_success, print_title

    config: Config = ctx.obj["config"]
    storage = _get_storage(config)

    since_date: Optional[date] = _parse_date(since) if since else (date.today() - timedelta(days=1))
    since_dt = datetime(since_date.year, since_date.month, since_date.day)

    repo_path = str(Path(repo).resolve())
    print_title("dev-journal collect", subtitle=f"Collecting activity since {since_date} in {repo_path}")

    total = 0

    # --- Git ---
    git = GitCollector(repo_path)
    if git.is_git_repo():
        git_activities = git.collect(since=since_dt)
        count = storage.insert_many(git_activities)
        total += count
        print_success(f"Git: collected {count} commit(s)")
    else:
        print_info(f"Skipping git: {repo_path} is not a git repository")

    # --- Files ---
    if not no_files:
        file_collector = FileCollector(
            repo_path,
            ignored_extensions=config.ignored_extensions,
            ignored_directories=config.ignored_directories,
        )
        file_activities = file_collector.collect(since=since_dt)
        count = storage.insert_many(file_activities)
        total += count
        print_success(f"Files: collected {count} modification(s)")

    # --- Shell ---
    if not no_shell and config.shell_history_enabled:
        shell_collector = ShellCollector(
            history_path=config.shell_history_path if config.shell_history_path else None,
            sensitive_patterns=config.sensitive_patterns,
        )
        shell_activities = shell_collector.collect(since=since_dt)
        count = storage.insert_many(shell_activities)
        total += count
        print_success(f"Shell: collected {count} command(s)")
    elif not config.shell_history_enabled:
        print_info("Shell history: disabled (use 'dev-journal init --enable-shell-history' to opt-in)")

    click.echo("")
    click.echo(f"Total activities collected: {total}")
    click.echo(f"Total in journal: {storage.count()}")


# ====================================================================== #
# standup                                                                  #
# ====================================================================== #


@main.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "markdown", "json"], case_sensitive=False),
    default="markdown",
    show_default=True,
    help="Output format.",
)
@click.option("--date", "target_date_str", default=None, help="Reference date (YYYY-MM-DD). Default: today.")
@click.option("--copy", is_flag=True, default=False, help="Copy output to clipboard.")
@click.option("--repo", "-r", default=None, help="Limit to a specific repo name.")
@click.pass_context
def standup(
    ctx: click.Context,
    output_format: str,
    target_date_str: Optional[str],
    copy: bool,
    repo: Optional[str],
) -> None:
    """Generate today's standup notes.

    Reports what you did yesterday, what you plan to do today,
    and any blockers detected from your activity.
    """
    from dev_journal.collectors import GitCollector
    from dev_journal.formatter import print_error, render_standup
    from dev_journal.generators import StandupGenerator

    config: Config = ctx.obj["config"]
    storage = _get_storage(config)
    target_date = _parse_date(target_date_str) if target_date_str else date.today()

    # Try to get open branches from current repo
    open_branches: list = []
    try:
        git = GitCollector()
        if git.is_git_repo():
            open_branches = git.get_open_branches()
    except Exception:
        pass

    generator = StandupGenerator(storage)
    content = generator.generate(
        target_date=target_date,
        output_format=output_format,
        open_branches=open_branches,
    )

    if output_format == "json":
        click.echo(content)
        return

    render_standup(content, output_format)

    if copy:
        try:
            import pyperclip

            pyperclip.copy(content)
            click.echo("\nCopied to clipboard.")
        except Exception as exc:
            print_error(f"Could not copy to clipboard: {exc}")


# ====================================================================== #
# weekly                                                                   #
# ====================================================================== #


@main.command()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "markdown", "json"], case_sensitive=False),
    default="markdown",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--week", "week_str", default=None, help="Any date in the target week (YYYY-MM-DD). Default: current week."
)
@click.pass_context
def weekly(ctx: click.Context, output_format: str, week_str: Optional[str]) -> None:
    """Generate a weekly sprint summary.

    Aggregates all activity for the current (or specified) week into a
    sprint-review-ready report with per-repo stats and highlights.
    """
    from dev_journal.formatter import render_weekly
    from dev_journal.generators import WeeklyGenerator

    config: Config = ctx.obj["config"]
    storage = _get_storage(config)

    week_date = _parse_date(week_str) if week_str else None

    generator = WeeklyGenerator(storage)
    content = generator.generate(week_of=week_date, output_format=output_format)

    if output_format == "json":
        click.echo(content)
        return

    render_weekly(content, output_format)


# ====================================================================== #
# blog                                                                     #
# ====================================================================== #


@main.command()
@click.option("--days", default=7, show_default=True, help="Number of days to cover.")
@click.option("--title", default=None, help="Override auto-generated title.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json"], case_sensitive=False),
    default="markdown",
    show_default=True,
    help="Output format.",
)
@click.option("--output", "-o", default=None, help="Write output to a file instead of stdout.")
@click.pass_context
def blog(
    ctx: click.Context,
    days: int,
    title: Optional[str],
    output_format: str,
    output: Optional[str],
) -> None:
    """Generate a blog post draft from recent coding activity.

    Produces a Dev.to-compatible Markdown file with frontmatter,
    narrative sections per repo, stats, and placeholder sections
    for you to fill in before publishing.
    """
    from dev_journal.formatter import print_success, render_blog
    from dev_journal.generators import BlogGenerator

    config: Config = ctx.obj["config"]
    storage = _get_storage(config)

    generator = BlogGenerator(storage)
    content = generator.generate(
        days=days,
        title=title,
        tags=config.blog_tags,
        author=config.author_name,
        output_format=output_format,
    )

    if output:
        out_path = Path(output)
        out_path.write_text(content, encoding="utf-8")
        print_success(f"Blog draft saved to: {out_path.resolve()}")
        return

    if output_format == "json":
        click.echo(content)
        return

    render_blog(content)


# ====================================================================== #
# timeline                                                                 #
# ====================================================================== #


@main.command()
@click.option("--days", default=7, show_default=True, help="Number of days to show.")
@click.option("--repo", "-r", default=None, help="Filter by repo name.")
@click.option(
    "--type",
    "activity_type",
    default=None,
    type=click.Choice(["git_commit", "file_change", "shell_command"], case_sensitive=False),
    help="Filter by activity type.",
)
@click.pass_context
def timeline(
    ctx: click.Context,
    days: int,
    repo: Optional[str],
    activity_type: Optional[str],
) -> None:
    """Show an activity timeline in the terminal.

    Displays a color-coded table of all tracked activities,
    grouped by day and sorted newest-first.
    """
    from dev_journal.formatter import print_info, render_timeline

    config: Config = ctx.obj["config"]
    storage = _get_storage(config)

    activities = storage.query_since(days)

    if repo:
        activities = [a for a in activities if a.repo == repo]
    if activity_type:
        activities = [a for a in activities if a.type == activity_type]

    if not activities:
        print_info(f"No activity found for the last {days} day(s).")
        if storage.count() == 0:
            click.echo("Run 'dev-journal collect' to import your activity first.")
        return

    render_timeline(activities, days=days)

    click.echo(f"\nTotal: {len(activities)} activit{'y' if len(activities) == 1 else 'ies'}")


# ====================================================================== #
# version                                                                  #
# ====================================================================== #


@main.command()
def version() -> None:
    """Show dev-journal version information."""
    import platform

    from rich.console import Console
    from rich.table import Table

    c = Console()
    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column(style="bold")
    table.add_row("dev-journal", __version__)
    table.add_row("Python", platform.python_version())
    table.add_row("Platform", platform.platform())
    c.print(table)


# ====================================================================== #
# config show                                                              #
# ====================================================================== #


@main.command("config")
@click.pass_context
def show_config(ctx: click.Context) -> None:
    """Show the current configuration."""
    from rich.console import Console
    from rich.syntax import Syntax

    config: Config = ctx.obj["config"]
    c = Console()

    if config.config_file.exists():
        raw = config.config_file.read_text(encoding="utf-8")
        c.print(Syntax(raw, "toml", theme="monokai", line_numbers=True))
        c.print(f"\n[dim]Config file: {config.config_file}[/dim]")
    else:
        c.print(f"[dim]No config file found at {config.config_file}[/dim]")
        c.print("[dim]Run 'dev-journal init' to create one.[/dim]")
