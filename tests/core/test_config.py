"""Tests for user settings persistence."""

import json

from core.config import UserConfig, load, save


class TestUserConfig:
    def test_defaults(self):
        cfg = UserConfig()
        assert cfg.theme == "light"
        assert cfg.outputs_dir == ""

    def test_custom_values(self):
        cfg = UserConfig(theme="dark", outputs_dir="/tmp/out")
        assert cfg.theme == "dark"
        assert cfg.outputs_dir == "/tmp/out"


class TestLoadSave:
    def test_load_returns_defaults_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.config._CONFIG_PATH", tmp_path / "missing.json")
        cfg = load()
        assert cfg.theme == "light"
        assert cfg.outputs_dir == ""

    def test_save_then_load_roundtrips(self, tmp_path, monkeypatch):
        path = tmp_path / "config.json"
        monkeypatch.setattr("core.config._CONFIG_PATH", path)

        save(UserConfig(theme="dark", outputs_dir="/my/outputs"))
        cfg = load()
        assert cfg.theme == "dark"
        assert cfg.outputs_dir == "/my/outputs"

    def test_save_creates_parent_dirs(self, tmp_path, monkeypatch):
        path = tmp_path / "nested" / "dir" / "config.json"
        monkeypatch.setattr("core.config._CONFIG_PATH", path)

        save(UserConfig())
        assert path.exists()

    def test_load_handles_corrupt_json(self, tmp_path, monkeypatch):
        path = tmp_path / "config.json"
        path.write_text("{invalid json", encoding="utf-8")
        monkeypatch.setattr("core.config._CONFIG_PATH", path)

        cfg = load()
        assert cfg.theme == "light"

    def test_load_handles_missing_keys(self, tmp_path, monkeypatch):
        path = tmp_path / "config.json"
        path.write_text("{}", encoding="utf-8")
        monkeypatch.setattr("core.config._CONFIG_PATH", path)

        cfg = load()
        assert cfg.theme == "light"
        assert cfg.outputs_dir == ""

    def test_saved_file_is_valid_json(self, tmp_path, monkeypatch):
        path = tmp_path / "config.json"
        monkeypatch.setattr("core.config._CONFIG_PATH", path)

        save(UserConfig(theme="dark", outputs_dir="C:\\out"))
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["theme"] == "dark"
        assert data["outputs_dir"] == "C:\\out"
