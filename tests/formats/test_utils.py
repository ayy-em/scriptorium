"""Tests for scripts.formats._utils (run_convert + past_inputs integration)."""

from pathlib import Path

import pytest

from core import paths
from scripts.formats import _utils
from scripts.formats._utils import IMAGE_EXTS, BatchConvertError, run_convert, single_source


@pytest.fixture
def archive_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Redirect inputs/past_inputs to per-test tmp paths (shared root + processed/)."""
    inputs = tmp_path / "inputs"
    past = inputs / "processed"
    inputs.mkdir(parents=True, exist_ok=True)
    past.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(paths, "inputs_dir", lambda _theme: inputs)
    monkeypatch.setattr(paths, "past_inputs_dir", lambda _theme: past)
    return inputs, past


def _make(directory: Path, name: str, content: str = "x") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_text(content, encoding="utf-8")
    return p


class TestRunConvertArchiving:
    def test_single_file_input_moved_after_success(self, archive_setup: tuple[Path, Path], tmp_path: Path):
        inputs, past = archive_setup
        src = _make(inputs, "song.flac", "audio")
        out_dir = tmp_path / "out"

        def fn(inp: Path, out: Path) -> None:
            out.write_text(inp.read_text(encoding="utf-8"))

        outputs = run_convert(src, frozenset({".flac"}), out_dir, "mp3", fn)

        assert len(outputs) == 1
        assert outputs[0].exists()
        assert not src.exists()
        assert (past / "song.flac").read_text() == "audio"

    def test_batch_mode_moves_each_processed_input(self, archive_setup: tuple[Path, Path], tmp_path: Path):
        inputs, past = archive_setup
        _make(inputs, "a.flac", "alpha")
        _make(inputs, "b.flac", "beta")
        out_dir = tmp_path / "out"

        def fn(inp: Path, out: Path) -> None:
            out.write_text(inp.read_text(encoding="utf-8"))

        outputs = run_convert(inputs, frozenset({".flac"}), out_dir, "mp3", fn)

        assert len(outputs) == 2
        names = sorted(p.name for p in past.iterdir())
        assert names == ["a.flac", "b.flac"]

    def test_failed_files_are_not_moved(self, archive_setup: tuple[Path, Path], tmp_path: Path):
        inputs, past = archive_setup
        ok = _make(inputs, "ok.flac", "ok")
        bad = _make(inputs, "bad.flac", "bad")
        out_dir = tmp_path / "out"

        def fn(inp: Path, out: Path) -> None:
            if inp.name == "bad.flac":
                raise RuntimeError("nope")
            out.write_text("done")

        with pytest.raises(BatchConvertError):
            run_convert(inputs, frozenset({".flac"}), out_dir, "mp3", fn)

        assert (past / "ok.flac").exists()
        assert not ok.exists()
        assert bad.exists()
        assert not (past / "bad.flac").exists()

    def test_files_outside_inputs_dir_not_moved(self, archive_setup: tuple[Path, Path], tmp_path: Path):
        _, past = archive_setup
        external = _make(tmp_path / "elsewhere", "x.flac", "external")
        out_dir = tmp_path / "out"

        def fn(inp: Path, out: Path) -> None:
            out.write_text("done")

        outputs = run_convert(external, frozenset({".flac"}), out_dir, "mp3", fn)

        assert len(outputs) == 1
        assert external.exists()
        assert not (past / "x.flac").exists()


class TestRunConvertDeduplication:
    @pytest.fixture(autouse=True)
    def _freeze_stem(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_utils, "default_stem", lambda: "20260720_1505")

    def test_batch_deduplicates_output_names(self, archive_setup: tuple[Path, Path], tmp_path: Path):
        inputs, _ = archive_setup
        _make(inputs, "a.flac", "alpha")
        _make(inputs, "b.flac", "beta")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "20260720_1505_001.mp3").write_text("old")
        (out_dir / "20260720_1505_002.mp3").write_text("old")

        def fn(inp: Path, out: Path) -> None:
            out.write_text("new")

        outputs = run_convert(inputs, frozenset({".flac"}), out_dir, "mp3", fn)

        assert len(outputs) == 2
        all_outputs = sorted(out_dir.iterdir())
        assert len(all_outputs) == 4


def test_module_exposes_run_convert() -> None:
    assert _utils.run_convert is run_convert


class TestSingleSource:
    def test_a_file_is_its_own_single_source(self, tmp_path):
        f = tmp_path / "a.png"
        f.write_bytes(b"x")
        assert single_source(f, IMAGE_EXTS) == f

    def test_directory_with_exactly_one_match_collapses_to_it(self, tmp_path):
        """The web UI uploads even one file into a batch directory."""
        f = tmp_path / "only.png"
        f.write_bytes(b"x")
        assert single_source(tmp_path, IMAGE_EXTS) == f

    def test_directory_with_several_matches_stays_a_batch(self, tmp_path):
        for n in ("a.png", "b.png"):
            (tmp_path / n).write_bytes(b"x")
        assert single_source(tmp_path, IMAGE_EXTS) is None

    def test_empty_directory_is_not_a_single_source(self, tmp_path):
        assert single_source(tmp_path, IMAGE_EXTS) is None

    def test_ignores_files_of_other_types(self, tmp_path):
        (tmp_path / "keep.png").write_bytes(b"x")
        (tmp_path / "skip.txt").write_bytes(b"x")
        assert single_source(tmp_path, IMAGE_EXTS).name == "keep.png"

    def test_missing_path_is_not_a_single_source(self, tmp_path):
        assert single_source(tmp_path / "nope", IMAGE_EXTS) is None


class TestRunConvertExplicitOutput:
    @staticmethod
    def _touch(p):
        p.write_bytes(b"x")
        return p

    def test_honours_an_explicit_filename_for_one_file(self, tmp_path):
        src = tmp_path / "in"
        src.mkdir()
        self._touch(src / "only.png")
        out_dir = tmp_path / "out"
        target = tmp_path / "named.jpg"

        written = run_convert(src, IMAGE_EXTS, out_dir, "jpg", lambda i, o: o.write_bytes(b"y"), explicit_output=target)
        assert written == [target]
        assert target.exists()

    def test_ignores_an_explicit_filename_for_a_real_batch(self, tmp_path):
        src = tmp_path / "in"
        src.mkdir()
        for n in ("a.png", "b.png"):
            self._touch(src / n)
        out_dir = tmp_path / "out"

        written = run_convert(
            src, IMAGE_EXTS, out_dir, "jpg", lambda i, o: o.write_bytes(b"y"), explicit_output=tmp_path / "one.jpg"
        )
        assert len(written) == 2
        assert all(p.parent == out_dir for p in written)

    def test_without_an_explicit_output_it_timestamps_as_before(self, tmp_path):
        src = tmp_path / "in"
        src.mkdir()
        self._touch(src / "only.png")
        out_dir = tmp_path / "out"

        written = run_convert(src, IMAGE_EXTS, out_dir, "jpg", lambda i, o: o.write_bytes(b"y"))
        assert written[0].parent == out_dir
        assert written[0].suffix == ".jpg"

    def test_creates_the_explicit_output_parent(self, tmp_path):
        src = tmp_path / "in"
        src.mkdir()
        self._touch(src / "only.png")
        target = tmp_path / "deep" / "nested" / "named.jpg"

        run_convert(src, IMAGE_EXTS, tmp_path / "out", "jpg", lambda i, o: o.write_bytes(b"y"), explicit_output=target)
        assert target.exists()
