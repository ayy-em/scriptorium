"""Tests for core.registry — verifies the real on-disk scripts/ tree is discovered."""

from core.registry import discover, discover_themes, theme_descriptions, theme_labels


class TestDiscover:
    def test_returns_at_least_one_script(self):
        scripts = discover()
        assert scripts, "expected at least one script in scripts/"

    def test_keys_are_theme_dot_script(self):
        for key in discover():
            assert "." in key
            theme, script = key.split(".", 1)
            assert theme and script
            assert not theme.startswith("_")
            assert not script.startswith("_")

    def test_every_module_has_required_attrs(self):
        for key, mod in discover().items():
            for attr in ("TITLE", "DESCRIPTION", "run"):
                assert hasattr(mod, attr), f"{key} missing {attr}"

    def test_lora_scripts_are_discovered(self):
        keys = set(discover())
        assert {"lora.export_captions", "lora.import_captions", "lora.renumber", "lora.validate"} <= keys


class TestThemeLabels:
    def test_returns_a_mapping(self):
        labels = theme_labels()
        assert isinstance(labels, dict)
        assert labels

    def test_lora_label_is_defined(self):
        assert "lora" in theme_labels()


class TestThemeDescriptions:
    def test_returns_a_mapping(self):
        descriptions = theme_descriptions()
        assert isinstance(descriptions, dict)
        assert descriptions

    def test_themes_match_labels(self):
        assert set(theme_labels()) == set(theme_descriptions())


class TestDiscoverThemes:
    def test_groups_by_theme(self):
        grouped = discover_themes()
        assert "lora" in grouped
        assert "export_captions" in grouped["lora"]

    def test_no_empty_themes(self):
        for theme, scripts in discover_themes().items():
            assert scripts, f"theme {theme!r} has no scripts"
