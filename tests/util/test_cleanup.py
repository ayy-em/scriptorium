"""Tests for scripts.util.cleanup."""

from pathlib import Path

import pytest

from scripts.util.cleanup import cleanup


def _make_tree(root: Path, layout: dict[str, str]) -> None:
    for rel, content in layout.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class TestCleanup:
    def test_dry_run_does_not_move_files(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        _make_tree(scripts, {"lora/inputs/img.jpg": "x", "av/outputs/out.mp4": "y"})
        archive = tmp_path / "archive" / "ts1"

        moved = cleanup(scripts, archive, dry_run=True)

        assert moved == 2
        assert (scripts / "lora/inputs/img.jpg").exists()
        assert (scripts / "av/outputs/out.mp4").exists()
        assert not archive.exists()

    def test_apply_moves_files_preserving_relative_paths(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        _make_tree(
            scripts,
            {
                "lora/inputs/img_001.jpg": "a",
                "lora/outputs/captions.json": "b",
                "av/inputs/clip.mp4": "c",
            },
        )
        archive = tmp_path / "archive" / "ts1"

        moved = cleanup(scripts, archive, dry_run=False)

        assert moved == 3
        assert (archive / "lora/inputs/img_001.jpg").read_text(encoding="utf-8") == "a"
        assert (archive / "lora/outputs/captions.json").read_text(encoding="utf-8") == "b"
        assert (archive / "av/inputs/clip.mp4").read_text(encoding="utf-8") == "c"
        assert not (scripts / "lora/inputs/img_001.jpg").exists()

    def test_apply_preserves_nested_subdirectories(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        _make_tree(scripts, {"av/outputs/anim/frames/001.png": "frame"})
        archive = tmp_path / "archive" / "ts1"

        cleanup(scripts, archive, dry_run=False)

        assert (archive / "av/outputs/anim/frames/001.png").read_text(encoding="utf-8") == "frame"

    def test_empty_inputs_and_outputs_dirs_are_silent(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        scripts = tmp_path / "scripts"
        (scripts / "lora/inputs").mkdir(parents=True)
        (scripts / "lora/outputs").mkdir(parents=True)

        moved = cleanup(scripts, tmp_path / "archive" / "ts1", dry_run=False)

        assert moved == 0
        assert "nothing to archive" in capsys.readouterr().out

    def test_ignores_files_outside_inputs_and_outputs(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        _make_tree(
            scripts,
            {
                "lora/inputs/img.jpg": "keep",
                "lora/source_code.py": "skip",
                "lora/_helpers.py": "skip",
            },
        )
        archive = tmp_path / "archive" / "ts1"

        cleanup(scripts, archive, dry_run=False)

        assert (archive / "lora/inputs/img.jpg").exists()
        assert (scripts / "lora/source_code.py").exists()
        assert (scripts / "lora/_helpers.py").exists()
        assert not (archive / "lora/source_code.py").exists()

    def test_no_inputs_or_outputs_dirs(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()

        moved = cleanup(scripts, tmp_path / "archive" / "ts1", dry_run=False)

        assert moved == 0
