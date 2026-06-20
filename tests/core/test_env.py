"""Tests for core.env — .env file loading."""

import os

from core.env import load_env


def test_load_env_sets_vars(tmp_path, monkeypatch):
    monkeypatch.setattr("core.env._repo_root", lambda: tmp_path)
    (tmp_path / ".env").write_text("FOO_TEST_VAR=bar\n", encoding="utf-8")
    monkeypatch.delenv("FOO_TEST_VAR", raising=False)

    load_env()

    assert os.environ["FOO_TEST_VAR"] == "bar"
    monkeypatch.delenv("FOO_TEST_VAR")


def test_load_env_does_not_overwrite_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("core.env._repo_root", lambda: tmp_path)
    (tmp_path / ".env").write_text("FOO_TEST_VAR=from_file\n", encoding="utf-8")
    monkeypatch.setenv("FOO_TEST_VAR", "from_shell")

    load_env()

    assert os.environ["FOO_TEST_VAR"] == "from_shell"


def test_load_env_strips_quotes(tmp_path, monkeypatch):
    monkeypatch.setattr("core.env._repo_root", lambda: tmp_path)
    (tmp_path / ".env").write_text('QUOTED_VAR="hello world"\n', encoding="utf-8")
    monkeypatch.delenv("QUOTED_VAR", raising=False)

    load_env()

    assert os.environ["QUOTED_VAR"] == "hello world"
    monkeypatch.delenv("QUOTED_VAR")


def test_load_env_skips_comments_and_blanks(tmp_path, monkeypatch):
    monkeypatch.setattr("core.env._repo_root", lambda: tmp_path)
    (tmp_path / ".env").write_text("# comment\n\nVALID_KEY=1\n", encoding="utf-8")
    monkeypatch.delenv("VALID_KEY", raising=False)

    load_env()

    assert os.environ["VALID_KEY"] == "1"
    assert "# comment" not in os.environ
    monkeypatch.delenv("VALID_KEY")


def test_load_env_noop_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("core.env._repo_root", lambda: tmp_path)
    load_env()
