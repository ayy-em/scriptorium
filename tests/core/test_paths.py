"""Tests for core.paths helpers, especially move_to_past_inputs."""

from pathlib import Path

import pytest

from core import paths


@pytest.fixture
def themed_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Redirect inputs_dir/past_inputs_dir to per-test tmp paths.

    Mirrors the production layout: ``inputs/`` is shared across themes, and
    ``inputs/processed/`` is where archived files land. Both directories are
    pre-created so tests can write into them directly.
    """
    inputs = tmp_path / "inputs"
    past = inputs / "processed"
    inputs.mkdir(parents=True, exist_ok=True)
    past.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(paths, "inputs_dir", lambda _theme: inputs)
    monkeypatch.setattr(paths, "past_inputs_dir", lambda _theme: past)
    return inputs, past


class TestMoveToPastInputs:
    def test_moves_file_inside_inputs_dir(self, themed_dirs: tuple[Path, Path]):
        inputs, past = themed_dirs
        src = inputs / "song.mp3"
        src.write_text("audio")

        dest = paths.move_to_past_inputs("formats", src)

        assert dest is not None
        assert dest == past / "song.mp3"
        assert dest.read_text() == "audio"
        assert not src.exists()

    def test_returns_none_for_missing_source(self, themed_dirs: tuple[Path, Path]):
        inputs, _ = themed_dirs
        result = paths.move_to_past_inputs("formats", inputs / "ghost.mp3")
        assert result is None

    def test_ignores_files_outside_inputs_dir(self, themed_dirs: tuple[Path, Path], tmp_path: Path):
        external = tmp_path / "elsewhere" / "song.mp3"
        external.parent.mkdir(parents=True, exist_ok=True)
        external.write_text("audio")

        result = paths.move_to_past_inputs("formats", external)

        assert result is None
        assert external.exists()

    def test_ignores_files_already_in_processed(self, themed_dirs: tuple[Path, Path]):
        _, past = themed_dirs
        src = past / "song.mp3"
        src.write_text("already archived")

        result = paths.move_to_past_inputs("formats", src)

        assert result is None
        assert src.exists()

    def test_appends_timestamp_on_conflict(self, themed_dirs: tuple[Path, Path]):
        inputs, past = themed_dirs
        src = inputs / "song.mp3"
        src.write_text("new")
        existing = past / "song.mp3"
        existing.write_text("old")

        dest = paths.move_to_past_inputs("formats", src)

        assert dest is not None
        assert dest != existing
        assert dest.parent == past
        assert dest.read_text() == "new"
        assert existing.read_text() == "old"


class TestPathHelpers:
    def test_inputs_dir_is_repo_root_inputs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(paths, "_bundle_dir", lambda: tmp_path)
        monkeypatch.setattr(paths, "FROZEN", False)

        result = paths.inputs_dir("any-theme")

        assert result == tmp_path / "inputs"
        assert result.exists()

    def test_inputs_dir_ignores_theme(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(paths, "_bundle_dir", lambda: tmp_path)
        monkeypatch.setattr(paths, "FROZEN", False)

        assert paths.inputs_dir("lora") == paths.inputs_dir("av")

    def test_past_inputs_lives_inside_inputs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(paths, "_bundle_dir", lambda: tmp_path)
        monkeypatch.setattr(paths, "FROZEN", False)

        result = paths.past_inputs_dir("widgets")

        assert result == tmp_path / "inputs" / "processed"
        assert result.exists()

    def test_outputs_dir_is_repo_root_outputs_theme(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from core.config import UserConfig  # noqa: PLC0415

        monkeypatch.setattr(paths, "_bundle_dir", lambda: tmp_path)
        monkeypatch.setattr(paths, "FROZEN", False)
        monkeypatch.setattr("core.config.load", UserConfig)

        result = paths.outputs_dir("lora")

        assert result == tmp_path / "outputs" / "lora"
        assert result.exists()

    def test_logs_dir_is_created(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(paths, "_bundle_dir", lambda: tmp_path)
        monkeypatch.setattr(paths, "FROZEN", False)

        result = paths.logs_dir()

        assert result.exists()
        assert result == tmp_path / "logs"
