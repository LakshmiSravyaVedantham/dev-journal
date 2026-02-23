# dev-journal — Your Work Log Writes Itself

[![CI](https://github.com/sravyalu/dev-journal/actions/workflows/ci.yml/badge.svg)](https://github.com/sravyalu/dev-journal/actions/workflows/ci.yml)
[![Python Versions](https://img.shields.io/pypi/pyversions/dev-journal)](https://pypi.org/project/dev-journal/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**dev-journal** tracks your git commits, file changes, and shell activity, then auto-generates daily standup notes, weekly sprint summaries, and blog post drafts — so you spend less time writing about what you did and more time doing it.

---

## Quick Install

```bash
pip install dev-journal
```

Or, for development:

```bash
git clone https://github.com/sravyalu/dev-journal
cd dev-journal
pip install -e ".[dev]"
```

---

## Quick Start

```bash
# 1. Initialize dev-journal in your repo
dev-journal init --repo /path/to/my-project

# 2. Collect recent activity (git commits + file changes)
dev-journal collect --since 2026-02-17

# 3. Generate today's standup
dev-journal standup

# 4. See what you've been up to this week
dev-journal timeline --days 7

# 5. Generate a weekly sprint summary
dev-journal weekly

# 6. Draft a blog post from the last 7 days of work
dev-journal blog --days 7 --output my-week.md
```

### Example Standup Output

```
## Daily Standup — February 23, 2026

### What I did yesterday:
- **[my-app]** feat: implement rate limiting middleware (4 files, +112/-8) `a3f9b12`
- **[my-app]** fix: correct null check in auth handler (2 files, +15/-6) `c7d4e01`
- **[api-client]** chore: bump httpx to 0.27 (1 files, +3/-3) `f8a2c33`

### What I'm working on today:
- Continue work on branch: feature/oauth2-integration
- Verify fix: correct null check in auth handler

### Blockers:
- None

---
*Stats: 3 commits | 7 files | +130/-17 lines | repos: my-app, api-client*
```

---

## Features

### Activity Tracking
dev-journal collects developer workflow signals from multiple sources:
- **Git commits** — hash, message, author, files changed, insertions/deletions, intent classification
- **File changes** — recently modified source files grouped by language and directory
- **Shell history** — opt-in only; records developer commands like `git`, `pytest`, `docker`, `make`

All data is stored locally in a SQLite database at `~/.dev-journal/journal.db`. Nothing leaves your machine.

### Daily Standup Generator
Produces a ready-to-paste standup update in text, Markdown, or JSON format:
- **Yesterday**: summarizes commits grouped by repo, with file stats
- **Today**: infers plans from open branches and recent WIP commits
- **Blockers**: detects unfinished work, broken commits, and WIP markers

```bash
dev-journal standup --format markdown
dev-journal standup --format text --copy   # also copy to clipboard
dev-journal standup --format json          # pipe to other tools
```

### Weekly Sprint Summary
Aggregates a full ISO week of activity into a sprint-review report:
- Total commits, lines added/removed, files touched
- Per-repository breakdown with work type analysis
- Daily activity heatmap
- Top highlights by commit impact

```bash
dev-journal weekly
dev-journal weekly --week 2026-02-16   # specific week
dev-journal weekly --format json       # JSON output
```

### Blog Post Draft Generator
Turns your coding activity into a structured Dev.to blog post draft:
- Dev.to-compatible Markdown with YAML frontmatter
- Narrative sections per repository
- Stats, work type breakdown, and languages used
- Placeholder sections for "What's Next" and "Lessons Learned"

```bash
dev-journal blog --days 7
dev-journal blog --title "Building a Rate Limiter" --output my-post.md
```

### Timeline View
Color-coded activity timeline rendered in your terminal:
- Git commits in green with intent labels (FEATURE, FIX, REFACTOR...)
- File changes in blue with language tags
- Shell commands in yellow
- Grouped by day, sorted newest-first

```bash
dev-journal timeline
dev-journal timeline --days 14
dev-journal timeline --type git_commit
```

---

## CLI Reference

```
dev-journal [--verbose] COMMAND [OPTIONS]

Commands:
  init       Initialize dev-journal (creates ~/.dev-journal/)
  collect    Collect recent activity into the journal
  standup    Generate today's standup notes
  weekly     Generate a weekly sprint summary
  blog       Generate a blog post draft
  timeline   Show activity timeline in terminal
  config     Show current configuration
  version    Show version information
```

### init

```bash
dev-journal init [--repo PATH] [--enable-shell-history] [--history-path PATH]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--repo` | `.` | Path to the git repository to track |
| `--enable-shell-history` | off | Opt-in to shell command tracking |
| `--history-path` | auto-detected | Path to shell history file |

### collect

```bash
dev-journal collect [--since DATE] [--repo PATH] [--no-files] [--no-shell]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--since` | yesterday | Collect activity since this date (YYYY-MM-DD) |
| `--repo` | `.` | Repository path to collect from |
| `--no-files` | off | Skip file change collection |
| `--no-shell` | off | Skip shell history collection |

### standup

```bash
dev-journal standup [--format FORMAT] [--date DATE] [--copy]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--format` | markdown | Output format: text, markdown, json |
| `--date` | today | Reference "today" date (YYYY-MM-DD) |
| `--copy` | off | Copy output to clipboard |

### weekly

```bash
dev-journal weekly [--format FORMAT] [--week DATE]
```

### blog

```bash
dev-journal blog [--days N] [--title TEXT] [--format FORMAT] [--output FILE]
```

### timeline

```bash
dev-journal timeline [--days N] [--repo NAME] [--type TYPE]
```

---

## Configuration

dev-journal stores its configuration at `~/.dev-journal/config.toml`:

```toml
[general]
default_format = "markdown"

[tracking]
repos = ["/path/to/project"]
shell_history_enabled = false
ignored_extensions = [".pyc", ".pyo", ".DS_Store"]
ignored_directories = [".git", "__pycache__", "node_modules"]

[privacy]
opt_in_shell_history = false
redact_sensitive_commands = true
sensitive_patterns = ["password", "secret", "token", "api_key"]

[blog]
default_tags = ["programming", "productivity", "developer-tools"]
author_name = "Your Name"
devto_api_key = ""

[display]
max_commits_in_standup = 10
max_files_in_standup = 15
```

Edit with any text editor. Changes take effect on the next command run.

---

## Privacy

dev-journal is designed with privacy first:

- **All data is local.** The SQLite database lives at `~/.dev-journal/journal.db` and never leaves your machine.
- **Shell history is opt-in.** It is disabled by default. You must explicitly enable it with `--enable-shell-history`.
- **Sensitive commands are filtered.** Any shell command matching patterns like `password`, `secret`, `token`, `api_key`, or environment variable assignments is automatically skipped and never stored.
- **You control what is tracked.** Configure `ignored_extensions`, `ignored_directories`, and `sensitive_patterns` in your config file.

---

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest -v

# Check formatting
black --check src/ tests/
isort --check-only src/ tests/

# Lint
flake8 src/ tests/ --max-line-length 120
```

### Project Structure

```
dev-journal/
├── src/dev_journal/
│   ├── __init__.py          # version, public API
│   ├── cli.py               # Click CLI entry point
│   ├── config.py            # TOML configuration management
│   ├── storage.py           # SQLite activity storage
│   ├── formatter.py         # Rich terminal output
│   ├── collectors/
│   │   ├── git_collector.py     # Parse git log
│   │   ├── file_collector.py    # Scan file mtimes
│   │   └── shell_collector.py   # Parse shell history
│   └── generators/
│       ├── standup.py           # Daily standup notes
│       ├── weekly.py            # Weekly sprint summary
│       └── blog.py              # Blog post draft
└── tests/
    ├── conftest.py
    ├── test_storage.py
    ├── test_git_collector.py
    ├── test_generators.py
    └── test_cli.py
```

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

*Built with [Click](https://click.palletsprojects.com/), [Rich](https://rich.readthedocs.io/), and a lot of standup meetings that ran too long.*
