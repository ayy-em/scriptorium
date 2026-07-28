"""Tests for compatibility badge derivation."""

from types import SimpleNamespace

from core.registry import discover
from webapp._badges import badges_for
from webapp._form import fields_from_parser


def _specs(key):
    """Return the field specs for a discovered script, or [] if it has no parser."""
    mod = discover()[key]
    return fields_from_parser(mod.get_parser()) if hasattr(mod, "get_parser") else []


class TestFromAccepts:
    def test_uses_accepts_categories(self):
        mod = SimpleNamespace(ACCEPTS={"image"})
        assert badges_for("photo.something", mod, []) == ["image"]

    def test_multiple_categories_follow_fixed_order(self):
        mod = SimpleNamespace(ACCEPTS={"audio", "video"})
        assert badges_for("misc.thing", mod, []) == ["video", "audio"]

    def test_script_without_accepts_gets_no_category_badge(self):
        assert badges_for("misc.thing", SimpleNamespace(), []) == []


class TestToolBadges:
    def test_av_theme_implies_ffmpeg(self):
        assert "ffmpeg" in badges_for("av.whatever", SimpleNamespace(), [])

    def test_downloads_theme_implies_yt_dlp(self):
        assert "yt-dlp" in badges_for("downloads.download", SimpleNamespace(), [])

    def test_per_key_override_beats_theme_default(self):
        # formats has no theme-wide tool, but these two shell out to ffmpeg.
        assert "ffmpeg" in badges_for("formats.convert_video", SimpleNamespace(), [])

    def test_theme_without_a_known_tool_gets_none(self):
        badges = badges_for("lora.validate", SimpleNamespace(), [])
        assert "ffmpeg" not in badges
        assert "yt-dlp" not in badges


class TestBatchBadge:
    def test_directory_input_adds_batch(self):
        assert "batch" in badges_for("photo.remove_bg", discover()["photo.remove_bg"], _specs("photo.remove_bg"))

    def test_single_file_input_does_not_add_batch(self):
        assert "batch" not in badges_for("av.filmstrip", discover()["av.filmstrip"], _specs("av.filmstrip"))


class TestRealScripts:
    def test_filmstrip(self):
        key = "av.filmstrip"
        assert badges_for(key, discover()[key], _specs(key)) == ["video", "ffmpeg"]

    def test_no_duplicates(self):
        for key, mod in discover().items():
            badges = badges_for(key, mod, _specs(key))
            assert len(badges) == len(set(badges)), key

    def test_ordering_is_stable_across_calls(self):
        key = "av.join"
        assert badges_for(key, discover()[key], _specs(key)) == badges_for(key, discover()[key], _specs(key))
