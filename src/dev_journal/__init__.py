"""
dev-journal: Auto-generate your work log from terminal activity.

This package provides tools for tracking developer activity (git commits,
file changes, shell commands) and generating daily standup notes, weekly
sprint summaries, and blog post drafts.
"""

__version__ = "0.1.0"
__author__ = "sravyalu"
__license__ = "MIT"

from dev_journal.config import Config
from dev_journal.storage import ActivityStorage

__all__ = [
    "__version__",
    "__author__",
    "__license__",
    "ActivityStorage",
    "Config",
]
