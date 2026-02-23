"""
Tests for dev_journal.storage — ActivityStorage CRUD and query operations.
"""

from datetime import date, timedelta

from dev_journal.storage import ActivityStorage
from tests.conftest import make_commit, make_file_change, make_shell_cmd

# ------------------------------------------------------------------ #
# Basic CRUD                                                            #
# ------------------------------------------------------------------ #


def test_insert_and_get(storage: ActivityStorage) -> None:
    """Inserting an activity assigns it an id and get() retrieves it."""
    act = make_commit(subject="feat: initial commit")
    row_id = storage.insert(act)

    assert row_id > 0
    assert act.id == row_id

    retrieved = storage.get(row_id)
    assert retrieved is not None
    assert retrieved.type == "git_commit"
    assert retrieved.details["subject"] == "feat: initial commit"


def test_get_nonexistent_returns_none(storage: ActivityStorage) -> None:
    """get() for a missing id returns None."""
    result = storage.get(99999)
    assert result is None


def test_delete_existing(storage: ActivityStorage) -> None:
    """delete() removes the row and returns True."""
    act = make_commit()
    row_id = storage.insert(act)

    deleted = storage.delete(row_id)
    assert deleted is True
    assert storage.get(row_id) is None


def test_delete_nonexistent_returns_false(storage: ActivityStorage) -> None:
    """delete() on a missing id returns False."""
    assert storage.delete(99999) is False


def test_insert_many(storage: ActivityStorage) -> None:
    """insert_many() stores all items and returns the correct count."""
    activities = [make_commit(subject=f"commit {i}") for i in range(5)]
    count = storage.insert_many(activities)

    assert count == 5
    assert storage.count() == 5


def test_insert_many_empty_list(storage: ActivityStorage) -> None:
    """insert_many() with an empty list is a no-op."""
    count = storage.insert_many([])
    assert count == 0


def test_clear_all(storage: ActivityStorage) -> None:
    """clear_all() removes every row."""
    storage.insert_many([make_commit() for _ in range(3)])
    deleted = storage.clear_all()
    assert deleted == 3
    assert storage.count() == 0


# ------------------------------------------------------------------ #
# Query operations                                                      #
# ------------------------------------------------------------------ #


def test_query_by_type(storage: ActivityStorage) -> None:
    """query() correctly filters by activity type."""
    storage.insert(make_commit())
    storage.insert(make_file_change())
    storage.insert(make_shell_cmd())

    commits = storage.query(activity_type="git_commit")
    assert len(commits) == 1
    assert commits[0].type == "git_commit"

    files = storage.query(activity_type="file_change")
    assert len(files) == 1


def test_query_by_repo(storage: ActivityStorage) -> None:
    """query() correctly filters by repo name."""
    storage.insert(make_commit(repo="repo-a"))
    storage.insert(make_commit(repo="repo-b"))
    storage.insert(make_commit(repo="repo-a"))

    results = storage.query(repo="repo-a")
    assert len(results) == 2
    assert all(a.repo == "repo-a" for a in results)


def test_query_date(storage: ActivityStorage) -> None:
    """query_date() returns only activities for the specified calendar day."""
    today_act = make_commit(days_ago=0)
    yesterday_act = make_commit(days_ago=1)
    storage.insert(today_act)
    storage.insert(yesterday_act)

    results = storage.query_date(date.today())
    assert len(results) == 1
    assert results[0].timestamp.date() == date.today()


def test_query_date_range(storage: ActivityStorage) -> None:
    """query_date_range() returns activities within the inclusive range."""
    for days_ago in range(5):
        storage.insert(make_commit(days_ago=days_ago))

    start = date.today() - timedelta(days=2)
    end = date.today()
    results = storage.query_date_range(start, end)

    assert len(results) == 3
    for a in results:
        assert start <= a.timestamp.date() <= end


def test_query_since(storage: ActivityStorage) -> None:
    """query_since() returns activities from the last N days."""
    storage.insert(make_commit(days_ago=0))
    storage.insert(make_commit(days_ago=3))
    storage.insert(make_commit(days_ago=10))

    results = storage.query_since(days=5)
    assert len(results) == 2


def test_repos_list(storage: ActivityStorage) -> None:
    """repos() returns distinct non-empty repo names."""
    storage.insert(make_commit(repo="alpha"))
    storage.insert(make_commit(repo="beta"))
    storage.insert(make_commit(repo="alpha"))
    storage.insert(make_shell_cmd())  # no repo

    repos = storage.repos()
    assert sorted(repos) == ["alpha", "beta"]


def test_count_by_type(storage: ActivityStorage) -> None:
    """count() filtered by type returns the correct number."""
    storage.insert(make_commit())
    storage.insert(make_commit())
    storage.insert(make_file_change())

    assert storage.count("git_commit") == 2
    assert storage.count("file_change") == 1
    assert storage.count("shell_command") == 0
    assert storage.count() == 3


# ------------------------------------------------------------------ #
# Serialization round-trip                                             #
# ------------------------------------------------------------------ #


def test_details_json_round_trip(storage: ActivityStorage) -> None:
    """Complex details dict survives a storage round-trip."""
    act = make_commit()
    act.details["changed_files"] = ["a.py", "b.py", "c.py"]
    act.details["nested"] = {"key": [1, 2, 3]}

    row_id = storage.insert(act)
    retrieved = storage.get(row_id)

    assert retrieved is not None
    assert retrieved.details["changed_files"] == ["a.py", "b.py", "c.py"]
    assert retrieved.details["nested"] == {"key": [1, 2, 3]}
