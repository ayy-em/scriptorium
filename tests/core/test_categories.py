"""Tests for core.categories — file extension categorisation."""

from core.categories import CATEGORY_EXTS, EXT_TO_CATEGORY, categorize


class TestCategoryExts:
    def test_has_all_five_categories(self):
        assert set(CATEGORY_EXTS) == {"video", "audio", "image", "tabular", "document"}

    def test_no_empty_sets(self):
        for cat, exts in CATEGORY_EXTS.items():
            assert exts, f"category {cat!r} has no extensions"

    def test_all_extensions_start_with_dot(self):
        for cat, exts in CATEGORY_EXTS.items():
            for ext in exts:
                assert ext.startswith("."), f"{ext!r} in {cat!r} missing leading dot"


class TestExtToCategory:
    def test_no_duplicate_extensions(self):
        seen: dict[str, str] = {}
        for cat, exts in CATEGORY_EXTS.items():
            for ext in exts:
                assert ext not in seen, f"{ext!r} appears in both {seen[ext]!r} and {cat!r}"
                seen[ext] = cat

    def test_mp4_is_video(self):
        assert EXT_TO_CATEGORY[".mp4"] == "video"

    def test_mp3_is_audio(self):
        assert EXT_TO_CATEGORY[".mp3"] == "audio"

    def test_png_is_image(self):
        assert EXT_TO_CATEGORY[".png"] == "image"

    def test_csv_is_tabular(self):
        assert EXT_TO_CATEGORY[".csv"] == "tabular"

    def test_pdf_is_document(self):
        assert EXT_TO_CATEGORY[".pdf"] == "document"


class TestCategorize:
    def test_video_file(self):
        assert categorize("clip.mp4") == "video"

    def test_audio_file(self):
        assert categorize("track.flac") == "audio"

    def test_image_file(self):
        assert categorize("photo.jpg") == "image"

    def test_tabular_file(self):
        assert categorize("data.xlsx") == "tabular"

    def test_document_file(self):
        assert categorize("readme.md") == "document"

    def test_unknown_extension_returns_none(self):
        assert categorize("archive.xyz") is None

    def test_case_insensitive(self):
        assert categorize("VIDEO.MP4") == "video"

    def test_path_with_directories(self):
        assert categorize("/home/user/inputs/clip.mkv") == "video"

    def test_no_extension_returns_none(self):
        assert categorize("Makefile") is None
