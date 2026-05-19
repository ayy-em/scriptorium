"""Tests for scripts.lora.validate."""

from pathlib import Path

import pytest

from scripts.lora.validate import validate


def _touch(path: Path, content: str = "") -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _make_pair(d: Path, stem: str, ext: str = ".jpg") -> None:
    _touch(d / f"{stem}{ext}")
    _touch(d / f"{stem}.txt", "caption")


class TestValidate:
    def test_valid_dataset_returns_true(self, tmp_path: Path):
        _make_pair(tmp_path, "img_001")
        _make_pair(tmp_path, "img_002")
        assert validate(tmp_path) is True

    def test_missing_directory_returns_false(self, tmp_path: Path):
        assert validate(tmp_path / "nope") is False

    def test_bad_image_name_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        _touch(tmp_path / "alpha.jpg")
        _touch(tmp_path / "alpha.txt", "caption")

        assert validate(tmp_path) is False
        assert "bad name" in capsys.readouterr().out

    def test_missing_caption_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        _touch(tmp_path / "img_001.jpg")

        assert validate(tmp_path) is False
        assert "missing caption" in capsys.readouterr().out

    def test_orphan_caption_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        _make_pair(tmp_path, "img_001")
        _touch(tmp_path / "img_999.txt", "stray")

        assert validate(tmp_path) is False
        assert "orphan caption" in capsys.readouterr().out

    def test_empty_directory_is_valid(self, tmp_path: Path):
        assert validate(tmp_path) is True
