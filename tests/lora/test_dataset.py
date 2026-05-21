"""Tests for scripts.lora._dataset helpers."""

from pathlib import Path

from scripts.lora._dataset import IMAGE_EXTS, IMG_NAME_RE, find_captions, find_images


def _touch(path: Path) -> Path:
    path.write_bytes(b"")
    return path


class TestFindImages:
    def test_returns_sorted_image_files(self, tmp_path: Path):
        _touch(tmp_path / "b.png")
        _touch(tmp_path / "a.jpg")
        _touch(tmp_path / "c.webp")
        result = find_images(tmp_path)
        assert [p.name for p in result] == ["a.jpg", "b.png", "c.webp"]

    def test_ignores_non_image_files(self, tmp_path: Path):
        _touch(tmp_path / "ok.png")
        _touch(tmp_path / "notes.txt")
        _touch(tmp_path / "data.json")
        result = find_images(tmp_path)
        assert [p.name for p in result] == ["ok.png"]

    def test_supports_all_known_extensions(self, tmp_path: Path):
        for ext in IMAGE_EXTS:
            _touch(tmp_path / f"file{ext}")
        result = find_images(tmp_path)
        assert len(result) == len(IMAGE_EXTS)

    def test_case_insensitive_suffix(self, tmp_path: Path):
        _touch(tmp_path / "shouty.JPG")
        result = find_images(tmp_path)
        assert [p.name for p in result] == ["shouty.JPG"]


class TestFindCaptions:
    def test_returns_only_txt_files(self, tmp_path: Path):
        _touch(tmp_path / "a.txt")
        _touch(tmp_path / "b.png")
        _touch(tmp_path / "c.txt")
        result = find_captions(tmp_path)
        assert [p.name for p in result] == ["a.txt", "c.txt"]


class TestImgNameRe:
    def test_matches_expected_pattern(self):
        assert IMG_NAME_RE.match("img_001")
        assert IMG_NAME_RE.match("img_12345")

    def test_rejects_other_patterns(self):
        assert not IMG_NAME_RE.match("img_abc")
        assert not IMG_NAME_RE.match("photo_001")
        assert not IMG_NAME_RE.match("img-001")
