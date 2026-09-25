"""Tests for core.env — .env file loading and the user-writable key store."""

import os
import sys

import pytest

from core import env
from core.env import load_env, set_env_value


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point both .env locations into tmp_path so tests never touch real files."""
    monkeypatch.setattr("core.env._repo_root", lambda: tmp_path / "repo")
    monkeypatch.setattr("core.env.user_env_path", lambda: tmp_path / "user" / ".env")
    (tmp_path / "repo").mkdir()
    monkeypatch.delenv("FOO_TEST_VAR", raising=False)


def _repo_env(tmp_path, text):
    (tmp_path / "repo" / ".env").write_text(text, encoding="utf-8")


def test_load_env_sets_vars(tmp_path):
    _repo_env(tmp_path, "FOO_TEST_VAR=bar\n")
    load_env()
    assert os.environ["FOO_TEST_VAR"] == "bar"


def test_load_env_does_not_overwrite_existing(tmp_path, monkeypatch):
    _repo_env(tmp_path, "FOO_TEST_VAR=from_file\n")
    monkeypatch.setenv("FOO_TEST_VAR", "from_shell")
    load_env()
    assert os.environ["FOO_TEST_VAR"] == "from_shell"


def test_load_env_strips_quotes(tmp_path):
    _repo_env(tmp_path, 'FOO_TEST_VAR="quoted"\n')
    load_env()
    assert os.environ["FOO_TEST_VAR"] == "quoted"


def test_load_env_skips_comments_and_blanks(tmp_path):
    _repo_env(tmp_path, "# comment\n\nnot a pair\nFOO_TEST_VAR=ok\n")
    load_env()
    assert os.environ["FOO_TEST_VAR"] == "ok"


def test_load_env_noop_when_no_file():
    load_env()
    assert "FOO_TEST_VAR" not in os.environ


def test_user_env_is_read_after_the_repo_env(tmp_path):
    """The developer's repo file wins; the user file fills in what it lacks."""
    _repo_env(tmp_path, "FOO_TEST_VAR=repo\n")
    user = env.user_env_path()
    user.parent.mkdir()
    user.write_text("FOO_TEST_VAR=user\nOTHER_TEST_VAR=user\n", encoding="utf-8")
    try:
        load_env()
        assert os.environ["FOO_TEST_VAR"] == "repo"
        assert os.environ["OTHER_TEST_VAR"] == "user"
    finally:
        os.environ.pop("OTHER_TEST_VAR", None)


def test_user_env_path_sits_next_to_config(monkeypatch):
    monkeypatch.undo()
    assert env.user_env_path().parent.name == "scriptorium"
    assert env.user_env_path().name == ".env"


class TestSetEnvValue:
    def test_writes_the_file_and_the_process(self):
        set_env_value("FOO_TEST_VAR", " secret ")
        assert env.user_env_path().read_text(encoding="utf-8") == "FOO_TEST_VAR=secret\n"
        assert os.environ["FOO_TEST_VAR"] == "secret"

    def test_keeps_other_keys(self):
        set_env_value("FOO_TEST_VAR", "one")
        set_env_value("BAR_TEST_VAR", "two")
        try:
            text = env.user_env_path().read_text(encoding="utf-8")
            assert "FOO_TEST_VAR=one" in text
            assert "BAR_TEST_VAR=two" in text
        finally:
            os.environ.pop("BAR_TEST_VAR", None)

    def test_empty_value_removes_the_key(self):
        set_env_value("FOO_TEST_VAR", "one")
        set_env_value("FOO_TEST_VAR", "")
        assert "FOO_TEST_VAR" not in env.user_env_path().read_text(encoding="utf-8")
        assert "FOO_TEST_VAR" not in os.environ

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
    def test_file_is_owner_only(self):
        set_env_value("FOO_TEST_VAR", "one")
        assert env.user_env_path().stat().st_mode & 0o777 == 0o600
