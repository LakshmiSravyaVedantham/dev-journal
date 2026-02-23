---
title: "I Built a CLI That Auto-Generates My Daily Standup Notes from Git History"
published: false
description: "dev-journal collects git commits, file changes, and shell history to auto-generate standups, weekly summaries, and blog drafts. No more scrambling before standup."
tags: productivity, python, developer, opensource
cover_image: ""
canonical_url:
series: "Building Developer Tools in 2026"
---

## The Problem: Nobody Remembers What They Did Yesterday

Every morning, the same ritual. Standup starts in 5 minutes. You stare at Slack trying to reconstruct what you worked on. You check your browser history. You scroll through `git log`. You write something vague like "continued work on the feature."

I got tired of this. My git history already has everything — what I changed, when, and why. Why am I manually summarizing it every day?

So I built `dev-journal`.

## 3 Lines to Get Started

```bash
pip install dev-journal
dev-journal collect --since 2026-02-17
dev-journal standup
```

That's it. Your standup is ready to paste.

## What It Generates

### Daily Standup

```markdown
## Daily Standup — February 23, 2026

### What I did yesterday:
- **[my-app]** feat: implement rate limiting middleware (4 files, +112/-8)
- **[my-app]** fix: correct null check in auth handler (2 files, +15/-6)
- **[api-client]** chore: bump httpx to 0.27 (1 file, +3/-3)

### What I'm working on today:
- Continue work on branch: feature/oauth2-integration

### Blockers:
- None

---
*Stats: 3 commits | 7 files | +130/-17 lines | repos: my-app, api-client*
```

### Weekly Sprint Summary

Aggregates an entire ISO week: total commits, lines changed, per-repo breakdown, daily heatmap, and top highlights by impact.

### Blog Post Draft

Generates Dev.to-compatible markdown with YAML frontmatter, narrative sections per repo, stats, and placeholder sections for "Lessons Learned." (Yes, I used dev-journal to help write this post.)

## How It Works

dev-journal has three **collectors** and three **generators**:

```
Collectors:               Generators:
┌──────────────┐         ┌──────────────────┐
│ git log      │───┐     │ standup (daily)   │
│ file mtime   │───┼────>│ weekly (sprint)   │
│ shell history│───┘     │ blog (Dev.to)     │
└──────────────┘         └──────────────────┘
        │                         │
        ▼                         ▼
   SQLite DB              text / markdown / json
```

### Git Collector

Parses `git log --stat` output and classifies each commit's intent:

| Prefix | Intent |
|--------|--------|
| `feat:` | FEATURE |
| `fix:` | FIX |
| `refactor:` | REFACTOR |
| `docs:` | DOCS |
| `test:` | TEST |
| Everything else | CHORE |

It also extracts file counts, insertions/deletions, and normalizes timezone-aware timestamps.

### File Collector

Scans for recently modified files grouped by language and directory. Respects `.gitignore` patterns and skips common junk (`__pycache__`, `node_modules`, etc.).

### Shell Collector (Opt-in)

Parses zsh/bash history for developer commands (`git`, `pytest`, `docker`, `make`). **Disabled by default.** Sensitive commands containing `password`, `token`, `secret`, or `api_key` are automatically filtered and never stored.

## Architecture

```
src/dev_journal/
├── cli.py               # Click CLI: 7 commands
├── config.py            # TOML config at ~/.dev-journal/
├── storage.py           # SQLite with full CRUD
├── formatter.py         # Rich terminal output
├── collectors/
│   ├── git_collector.py     # git log parser
│   ├── file_collector.py    # mtime scanner
│   └── shell_collector.py   # history parser
└── generators/
    ├── standup.py           # daily notes
    ├── weekly.py            # sprint summary
    └── blog.py              # Dev.to draft
```

## Privacy First

This was a core design principle:

- **All data is local.** SQLite at `~/.dev-journal/journal.db`. Nothing leaves your machine.
- **Shell history is opt-in.** Disabled by default. You explicitly enable it.
- **Sensitive commands are filtered.** Anything matching `password`, `secret`, `token`, `api_key` is skipped.
- **You control what's tracked.** Configure ignored extensions, directories, and patterns.

## The Interesting Technical Bits

### Commit Intent Classification

I wanted the standup to group commits by *what kind of work* they represent, not just list them chronologically. The classifier uses conventional commit prefixes first, then falls back to keyword analysis in the commit message:

- Messages containing "add", "implement", "create" -> FEATURE
- Messages containing "fix", "resolve", "patch" -> FIX
- Messages containing "refactor", "restructure", "clean" -> REFACTOR

### Standup "Today" Inference

The hardest generator problem: predicting what you'll work on *today*. dev-journal looks at:

1. Open branches (not merged to main)
2. Recent WIP commits
3. Commits from today that look incomplete (small changes, no tests)

It's not perfect, but it beats staring at a blank text box.

## Numbers

- **67 tests** passing
- **74% coverage**
- **Python 3.9-3.12** matrix CI
- **3 output formats**: text, markdown, JSON

## Try It

```bash
pip install dev-journal
dev-journal collect --since $(date -v-7d +%Y-%m-%d)
dev-journal standup --copy  # copies to clipboard
```

Star it on GitHub: [github.com/LakshmiSravyaVedantham/dev-journal](https://github.com/LakshmiSravyaVedantham/dev-journal)

---

*How do you prepare for standup? Let me know in the comments if you've tried automating it.*
