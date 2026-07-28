"""Shared fixtures for the webapp tests."""

import pytest

from core import history


@pytest.fixture(autouse=True)
def isolate_history(tmp_path, monkeypatch):
    """Keep run history out of the developer's real ~/scriptorium directory.

    Any test that exercises the run endpoint records a run, and without this
    those records land in the user's actual history file. Autouse so a new test
    cannot forget it.
    """
    monkeypatch.setattr(history, "_HISTORY_PATH", tmp_path / "history.json")
