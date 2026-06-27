"""Tests for core.registry — verifies the real on-disk scripts/ tree is discovered."""

from core.registry import (
    discover,
    discover_themes,
    scripts_for_category,
    scripts_for_file,
    theme_descriptions,
    theme_labels,
)


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


class TestScriptsForCategory:
    def test_video_returns_results(self):
        results = scripts_for_category("video")
        keys = [k for k, _ in results]
        assert "formats.convert_video" in keys

    def test_audio_includes_transcribe(self):
        keys = [k for k, _ in scripts_for_category("audio")]
        assert "speech.transcribe" in keys

    def test_image_includes_make_gif(self):
        keys = [k for k, _ in scripts_for_category("image")]
        assert "gif.make_gif" in keys

    def test_unknown_category_returns_empty(self):
        assert scripts_for_category("spreadsheet") == []

    def test_results_are_sorted(self):
        results = scripts_for_category("video")
        keys = [k for k, _ in results]
        assert keys == sorted(keys)


class TestScriptsForFile:
    def test_mp4_matches_video_scripts(self):
        results = scripts_for_file("clip.mp4")
        keys = [k for k, _ in results]
        assert "formats.convert_video" in keys
        assert "av.trim" in keys

    def test_unknown_extension_returns_empty(self):
        assert scripts_for_file("data.xyz") == []

    def test_flac_matches_audio_scripts(self):
        keys = [k for k, _ in scripts_for_file("song.flac")]
        assert "formats.convert_audio" in keys


class TestDiscoverThemes:
    def test_groups_by_theme(self):
        grouped = discover_themes()
        assert "lora" in grouped
        assert "export_captions" in grouped["lora"]

    def test_no_empty_themes(self):
        for theme, scripts in discover_themes().items():
            assert scripts, f"theme {theme!r} has no scripts"
