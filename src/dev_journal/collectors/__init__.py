"""
Activity collectors for dev-journal.

Available collectors:
- GitCollector: parse git log for commits and diffs
- FileCollector: scan directories for recently modified files
- ShellCollector: parse shell history (opt-in only)
"""

from dev_journal.collectors.file_collector import FileCollector
from dev_journal.collectors.git_collector import GitCollector
from dev_journal.collectors.shell_collector import ShellCollector

__all__ = ["GitCollector", "FileCollector", "ShellCollector"]
