"""Tests for user settings persistence."""

import json

from core.config import UserConfig, clean_favourites, clean_sort_order, load, save


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


class TestFavourites:
    """Favourites moved out of localStorage so all three launch tiers agree."""

    def test_default_is_empty_and_not_shared_between_instances(self):
        """A bare list default on a dataclass would be shared by every config."""
        a, b = UserConfig(), UserConfig()
        a.favourites.append("av.trim")
        assert b.favourites == []

    def test_roundtrips(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.config._CONFIG_PATH", tmp_path / "config.json")
        save(UserConfig(favourites=["av.trim", "gif.make_gif"], sort_order="count"))
        cfg = load()
        assert cfg.favourites == ["av.trim", "gif.make_gif"]
        assert cfg.sort_order == "count"

    def test_absent_keys_load_as_defaults(self, tmp_path, monkeypatch):
        """Configs written before this field existed must still load."""
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        monkeypatch.setattr("core.config._CONFIG_PATH", path)
        cfg = load()
        assert cfg.favourites == []
        assert cfg.sort_order == "az"


class TestCleanFavourites:
    """config.json is user-editable, so anything can turn up in it."""

    def test_drops_non_strings_and_blanks(self):
        assert clean_favourites(["av.trim", 3, None, "", "gif.make_gif"]) == [
            "av.trim",
            "gif.make_gif",
        ]

    def test_deduplicates_preserving_order(self):
        assert clean_favourites(["b", "a", "b"]) == ["b", "a"]

    def test_a_non_list_becomes_empty(self):
        assert clean_favourites("av.trim") == []
        assert clean_favourites(None) == []


class TestCleanSortOrder:
    def test_known_orders_pass_through(self):
        for order in ("az", "za", "count"):
            assert clean_sort_order(order) == order

    def test_anything_else_falls_back(self):
        assert clean_sort_order("sideways") == "az"
        assert clean_sort_order(None) == "az"
