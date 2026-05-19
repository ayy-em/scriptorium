"""Tests for scripts.formats._utils (run_convert + past_inputs integration)."""

from pathlib import Path

import pytest

from core import paths
from scripts.formats import _utils
from scripts.formats._utils import BatchConvertError, run_convert


@pytest.fixture
def archive_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Redirect inputs/past_inputs to per-test tmp paths."""
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


def _make(directory: Path, name: str, content: str = "x") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_text(content, encoding="utf-8")
    return p


class TestRunConvertArchiving:
    def test_single_file_input_moved_after_success(self, archive_setup: tuple[Path, Path], tmp_path: Path):
        inputs, past = archive_setup
        src = _make(inputs / "formats", "song.flac", "audio")
        out_dir = tmp_path / "out"

        def fn(inp: Path, out: Path) -> None:
            out.write_text(inp.read_text(encoding="utf-8"))

        outputs = run_convert(src, frozenset({".flac"}), out_dir, "mp3", fn)

        assert len(outputs) == 1
        assert outputs[0].exists()
        assert not src.exists()
        assert (past / "formats" / "song.flac").read_text() == "audio"

    def test_batch_mode_moves_each_processed_input(self, archive_setup: tuple[Path, Path], tmp_path: Path):
        inputs, past = archive_setup
        _make(inputs / "formats", "a.flac", "alpha")
        _make(inputs / "formats", "b.flac", "beta")
        out_dir = tmp_path / "out"

        def fn(inp: Path, out: Path) -> None:
            out.write_text(inp.read_text(encoding="utf-8"))

        outputs = run_convert(inputs / "formats", frozenset({".flac"}), out_dir, "mp3", fn)

        assert len(outputs) == 2
        names = sorted(p.name for p in (past / "formats").iterdir())
        assert names == ["a.flac", "b.flac"]

    def test_failed_files_are_not_moved(self, archive_setup: tuple[Path, Path], tmp_path: Path):
        inputs, past = archive_setup
        ok = _make(inputs / "formats", "ok.flac", "ok")
        bad = _make(inputs / "formats", "bad.flac", "bad")
        out_dir = tmp_path / "out"

        def fn(inp: Path, out: Path) -> None:
            if inp.name == "bad.flac":
                raise RuntimeError("nope")
            out.write_text("done")

        with pytest.raises(BatchConvertError):
            run_convert(inputs / "formats", frozenset({".flac"}), out_dir, "mp3", fn)

        assert (past / "formats" / "ok.flac").exists()
        assert not ok.exists()
        assert bad.exists()
        assert not (past / "formats" / "bad.flac").exists()

    def test_files_outside_inputs_dir_not_moved(self, archive_setup: tuple[Path, Path], tmp_path: Path):
        _, past = archive_setup
        external = _make(tmp_path / "elsewhere", "x.flac", "external")
        out_dir = tmp_path / "out"

        def fn(inp: Path, out: Path) -> None:
            out.write_text("done")

        outputs = run_convert(external, frozenset({".flac"}), out_dir, "mp3", fn)

        assert len(outputs) == 1
        assert external.exists()
        assert not (past / "formats" / "x.flac").exists()


def test_module_exposes_run_convert() -> None:
    assert _utils.run_convert is run_convert
