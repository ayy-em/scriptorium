"""Tests for scripts.lora.renumber."""

from pathlib import Path

import pytest

from scripts.lora.renumber import renumber


def _touch(path: Path, content: str = "") -> Path:
    path.write_text(content, encoding="utf-8")
    return path


class TestRenumber:
    def test_dry_run_does_not_rename(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        _touch(tmp_path / "alpha.jpg")
        _touch(tmp_path / "beta.png")

        renumber(tmp_path, dry_run=True)

        assert (tmp_path / "alpha.jpg").exists()
        assert (tmp_path / "beta.png").exists()
        assert "would rename" in capsys.readouterr().out

    def test_apply_renames_images(self, tmp_path: Path):
        _touch(tmp_path / "alpha.jpg")
        _touch(tmp_path / "beta.png")

        renumber(tmp_path, dry_run=False)

        names = sorted(p.name for p in tmp_path.iterdir())
        assert names == ["img_001.jpg", "img_002.png"]

    def test_paired_captions_are_renamed_together(self, tmp_path: Path):
        _touch(tmp_path / "alpha.jpg")
        _touch(tmp_path / "alpha.txt", "alpha text")
        _touch(tmp_path / "beta.png")
        _touch(tmp_path / "beta.txt", "beta text")

        renumber(tmp_path, dry_run=False)

        assert (tmp_path / "img_001.txt").read_text(encoding="utf-8") == "alpha text"
        assert (tmp_path / "img_002.txt").read_text(encoding="utf-8") == "beta text"

    def test_empty_directory_is_noop(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        renumber(tmp_path, dry_run=False)
        assert "no images" in capsys.readouterr().out.lower()

    def test_already_numbered_is_noop(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        _touch(tmp_path / "img_001.jpg")
        _touch(tmp_path / "img_002.png")

        renumber(tmp_path, dry_run=False)

        assert "already correctly numbered" in capsys.readouterr().out

    def test_width_scales_with_count(self, tmp_path: Path):
        for i in range(120):
            _touch(tmp_path / f"x{i:04d}.jpg")

        renumber(tmp_path, dry_run=False)

        names = sorted(p.name for p in tmp_path.iterdir())
        assert names[0] == "img_001.jpg"
        assert names[-1] == "img_120.jpg"

    def test_missing_directory_exits(self, tmp_path: Path):
        with pytest.raises(SystemExit) as excinfo:
            renumber(tmp_path / "nope", dry_run=False)
        assert excinfo.value.code == 1

    def test_normalizes_uppercase_suffix(self, tmp_path: Path):
        _touch(tmp_path / "shouty.JPG")
        renumber(tmp_path, dry_run=False)
        assert (tmp_path / "img_001.jpg").exists()
