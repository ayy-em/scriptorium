"""Tests for core.paths helpers, especially move_to_past_inputs."""

from pathlib import Path

import pytest

from core import paths


@pytest.fixture
def themed_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Redirect inputs_dir/past_inputs_dir to per-test tmp paths."""
    inputs = tmp_path / "inputs"
    past = tmp_path / "past_inputs"

    def fake_inputs(theme: str) -> Path:
        d = inputs / theme
        d.mkdir(parents=True, exist_ok=True)
        return d

    def fake_past(theme: str) -> Path:
        d = past / theme
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(paths, "inputs_dir", fake_inputs)
    monkeypatch.setattr(paths, "past_inputs_dir", fake_past)
    return inputs, past


class TestMoveToPastInputs:
    def test_moves_file_inside_inputs_dir(self, themed_dirs: tuple[Path, Path]):
        inputs, past = themed_dirs
        src = inputs / "formats" / "song.mp3"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("audio")

        dest = paths.move_to_past_inputs("formats", src)

        assert dest is not None
        assert dest == past / "formats" / "song.mp3"
        assert dest.read_text() == "audio"
        assert not src.exists()

    def test_returns_none_for_missing_source(self, themed_dirs: tuple[Path, Path]):
        inputs, _ = themed_dirs
        result = paths.move_to_past_inputs("formats", inputs / "formats" / "ghost.mp3")
        assert result is None

    def test_ignores_files_outside_inputs_dir(self, themed_dirs: tuple[Path, Path], tmp_path: Path):
        external = tmp_path / "elsewhere" / "song.mp3"
        external.parent.mkdir(parents=True, exist_ok=True)
        external.write_text("audio")

        result = paths.move_to_past_inputs("formats", external)

        assert result is None
        assert external.exists()

    def test_appends_timestamp_on_conflict(self, themed_dirs: tuple[Path, Path]):
        inputs, past = themed_dirs
        src = inputs / "formats" / "song.mp3"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("new")
        existing = past / "formats" / "song.mp3"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("old")

        dest = paths.move_to_past_inputs("formats", src)

        assert dest is not None
        assert dest != existing
        assert dest.parent == past / "formats"
        assert dest.read_text() == "new"
        assert existing.read_text() == "old"


class TestPathHelpers:
    def test_past_inputs_dir_is_created(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(paths, "_bundle_dir", lambda: tmp_path)
        monkeypatch.setattr(paths, "FROZEN", False)

        result = paths.past_inputs_dir("widgets")

        assert result.exists()
        assert result == tmp_path / "scripts" / "widgets" / "past_inputs"

    def test_logs_dir_is_created(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(paths, "_bundle_dir", lambda: tmp_path)
        monkeypatch.setattr(paths, "FROZEN", False)

        result = paths.logs_dir()

        assert result.exists()
        assert result == tmp_path / "logs"
