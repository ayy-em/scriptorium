"""Tests for core.paths helpers, especially move_to_past_inputs."""

import contextlib
from datetime import datetime
import io
import os
from pathlib import Path
import time

import pytest

from core import paths
from core.outputs import find_reported_outputs
from tests.core.test_outputs import _fake_home


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

    def test_newest_copy_keeps_the_plain_name_on_conflict(self, themed_dirs: tuple[Path, Path]):
        """The name must point at the newest copy, or re-runs find the wrong file.

        Looking a staged file up in the archive is a plain path lookup, so
        whichever copy holds the unsuffixed name is the one a second run gets.
        Archiving a replacement under a timestamped name and leaving the old
        one at ``song.mp3`` meant re-running fed the script last month's file.
        """
        inputs, past = themed_dirs
        src = inputs / "song.mp3"
        src.write_text("new")
        existing = past / "song.mp3"
        existing.write_text("old")

        dest = paths.move_to_past_inputs("formats", src)

        assert dest == existing
        assert dest.read_text() == "new"

    def test_displaced_copy_is_preserved_under_a_timestamp(self, themed_dirs: tuple[Path, Path]):
        inputs, past = themed_dirs
        (past / "song.mp3").write_text("old")
        src = inputs / "song.mp3"
        src.write_text("new")

        paths.move_to_past_inputs("formats", src)

        archived = sorted(p.read_text() for p in past.iterdir())
        assert archived == ["new", "old"], "the displaced copy must not be overwritten"

    def test_displacement_stamp_comes_from_the_displaced_file(self, themed_dirs: tuple[Path, Path]):
        """The suffix says when that copy is from, not when it was bumped."""
        inputs, past = themed_dirs
        existing = past / "song.mp3"
        existing.write_text("old")
        os.utime(existing, (1_000_000_000, 1_000_000_000))
        expected = datetime.fromtimestamp(1_000_000_000).strftime("%Y%m%dT%H%M%S")
        src = inputs / "song.mp3"
        src.write_text("new")

        paths.move_to_past_inputs("formats", src)

        assert (past / f"song_{expected}.mp3").read_text() == "old"

    def test_repeated_collisions_each_keep_their_own_copy(self, themed_dirs: tuple[Path, Path]):
        inputs, past = themed_dirs
        for text in ("first", "second", "third"):
            src = inputs / "song.mp3"
            src.write_text(text)
            paths.move_to_past_inputs("formats", src)

        assert (past / "song.mp3").read_text() == "third"
        assert sorted(p.read_text() for p in past.iterdir()) == ["first", "second", "third"]


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

    def test_outputs_root_has_no_theme_subdir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from core.config import UserConfig  # noqa: PLC0415

        monkeypatch.setattr(paths, "_bundle_dir", lambda: tmp_path)
        monkeypatch.setattr(paths, "FROZEN", False)
        monkeypatch.setattr("core.config.load", UserConfig)

        result = paths.outputs_root()

        assert result == tmp_path / "outputs"
        assert result.exists()

    def test_outputs_root_honours_custom_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from core.config import UserConfig  # noqa: PLC0415

        custom = tmp_path / "elsewhere"
        monkeypatch.setattr(paths, "FROZEN", False)
        monkeypatch.setattr("core.config.load", lambda: UserConfig(outputs_dir=str(custom)))

        assert paths.outputs_root() == custom

    def test_drop_session_dir_is_isolated_per_session(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(paths, "_bundle_dir", lambda: tmp_path)
        monkeypatch.setattr(paths, "FROZEN", False)

        first = paths.drop_session_dir("20260101-000000-aaaaaa")
        second = paths.drop_session_dir("20260101-000001-bbbbbb")

        assert first == tmp_path / "inputs" / "drop" / "20260101-000000-aaaaaa"
        assert first.exists()
        assert first != second

    def test_logs_dir_is_created(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(paths, "_bundle_dir", lambda: tmp_path)
        monkeypatch.setattr(paths, "FROZEN", False)

        result = paths.logs_dir()

        assert result.exists()
        assert result == tmp_path / "logs"


class TestResolveInput:
    """Input paths have the same tilde hole outputs did.

    Nothing in the web UI passes through a shell, so ``~`` has to be expanded
    here or not at all.
    """

    @pytest.fixture
    def webapp(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
        """Web UI caller, with home and the staged inputs directory redirected."""
        from core.invocation import CALLER_ENV_VAR  # noqa: PLC0415

        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        home = _fake_home(tmp_path, monkeypatch)
        staged = tmp_path / "inputs"
        staged.mkdir()
        monkeypatch.setattr(paths, "inputs_dir", lambda _theme: staged)
        return home, staged

    @pytest.fixture
    def cli(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
        """Command-line caller standing in a known directory."""
        from core.invocation import CALLER_ENV_VAR  # noqa: PLC0415

        monkeypatch.delenv(CALLER_ENV_VAR, raising=False)
        home = _fake_home(tmp_path, monkeypatch)
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        return home, cwd

    def test_tilde_expands_to_home(self, webapp: tuple[Path, Path]):
        home, _ = webapp
        assert paths.resolve_input(Path("~/Music/song.mp3"), "av") == home / "Music" / "song.mp3"

    def test_absolute_path_untouched(self, webapp: tuple[Path, Path], tmp_path: Path):
        target = tmp_path / "elsewhere" / "song.mp3"
        assert paths.resolve_input(target, "av") == target

    def test_bare_name_still_reads_from_staged_inputs(self, webapp: tuple[Path, Path]):
        _, staged = webapp
        assert paths.resolve_input(Path("song.mp3"), "av") == staged / "song.mp3"

    def test_relative_with_directory_part_anchors_to_home(self, webapp: tuple[Path, Path]):
        home, _ = webapp
        assert paths.resolve_input(Path("Music/song.mp3"), "av") == home / "Music" / "song.mp3"

    def test_tilde_expands_on_the_cli_too(self, cli: tuple[Path, Path]):
        home, _ = cli
        assert paths.resolve_input(Path("~/song.mp3"), "av") == home / "song.mp3"

    def test_bare_name_stays_relative_on_the_cli(self, cli: tuple[Path, Path]):
        assert paths.resolve_input(Path("song.mp3"), "av") == Path("song.mp3")

    def test_relative_with_directory_part_anchors_to_cwd_on_the_cli(self, cli: tuple[Path, Path]):
        _, cwd = cli
        assert paths.resolve_input(Path("Music/song.mp3"), "av") == cwd / "Music" / "song.mp3"


class TestReadBuildSha:
    """A frozen build reads the hash its spec recorded; development has none."""

    def test_reads_the_bundled_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(paths, "_bundle_dir", lambda: tmp_path)
        (tmp_path / "build_sha.txt").write_text("abc1234\n", encoding="utf-8")
        assert paths.read_build_sha() == "abc1234"

    def test_empty_when_the_file_is_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(paths, "_bundle_dir", lambda: tmp_path)
        assert paths.read_build_sha() == ""


class TestArchivedCopy:
    """Following an input that a previous run filed away."""

    def test_finds_the_archived_file(self, themed_dirs: tuple[Path, Path]):
        inputs, past = themed_dirs
        (past / "clip.mp4").write_text("archived")

        assert paths.archived_copy("av", inputs / "clip.mp4") == past / "clip.mp4"

    def test_returns_none_while_the_file_is_still_staged(self, themed_dirs: tuple[Path, Path]):
        """A staged file wins; the archive is only consulted once it is gone."""
        inputs, past = themed_dirs
        (inputs / "clip.mp4").write_text("current")
        (past / "clip.mp4").write_text("archived")

        assert paths.archived_copy("av", inputs / "clip.mp4") is None

    def test_does_not_follow_a_path_outside_the_inputs_tree(self, themed_dirs: tuple[Path, Path], tmp_path: Path):
        """A missing ~/Movies/clip.mp4 must not resolve to an unrelated archived file."""
        _, past = themed_dirs
        (past / "clip.mp4").write_text("someone else's clip")
        elsewhere = tmp_path / "Movies" / "clip.mp4"

        assert paths.archived_copy("av", elsewhere) is None

    def test_returns_none_when_nothing_was_archived(self, themed_dirs: tuple[Path, Path]):
        inputs, _ = themed_dirs
        assert paths.archived_copy("av", inputs / "never-existed.mp4") is None

    def test_only_files_are_recovered(self, themed_dirs: tuple[Path, Path]):
        """``processed/`` only ever holds files, so only files come back.

        A directory-native script (``gif.make_gif``, ``lora.*``) pointed at a
        missing folder gets nothing from the archive to be confused by, because
        archiving refuses directories in the first place.
        """
        inputs, past = themed_dirs
        frames = inputs / "frames"
        frames.mkdir()
        (frames / "001.png").write_text("frame")

        assert paths.move_to_past_inputs("gif", frames) is None
        assert list(past.iterdir()) == []
        assert frames.is_dir(), "a directory input must be left alone"


class TestRunningTheSameScriptTwice:
    """The UX this exists for: pressing Run twice without re-adding the file.

    The web form holds one path for the whole session and is not cleared after
    a run, so the path it holds stops existing the moment the first run
    archives it. Before this, the second Run failed on a file sitting in
    ``processed/``.
    """

    def test_a_held_path_keeps_working_across_runs(self, themed_dirs: tuple[Path, Path]):
        inputs, _ = themed_dirs
        staged = inputs / "clip.mp4"
        staged.write_text("video")
        held_by_the_form = staged

        for _ in range(3):
            resolved = paths.resolve_input(held_by_the_form, "av")
            assert resolved.is_file(), "a re-run could not find the file"
            assert resolved.read_text() == "video"
            paths.move_to_past_inputs("av", resolved)

    def test_an_already_archived_input_is_not_moved_again(self, themed_dirs: tuple[Path, Path]):
        """Re-running must not shuffle the archive or multiply copies."""
        inputs, past = themed_dirs
        staged = inputs / "clip.mp4"
        staged.write_text("video")

        for _ in range(3):
            paths.move_to_past_inputs("av", paths.resolve_input(staged, "av"))

        assert [p.name for p in past.iterdir()] == ["clip.mp4"]

    def test_the_substitution_is_announced(self, themed_dirs: tuple[Path, Path], capsys):
        """Reading a different path than the caller asked for is worth saying."""
        inputs, past = themed_dirs
        (past / "clip.mp4").write_text("archived")

        paths.resolve_input(inputs / "clip.mp4", "av")

        assert "archived by an earlier run" in capsys.readouterr().out

    def test_nothing_is_announced_when_the_file_is_where_it_should_be(self, themed_dirs: tuple[Path, Path], capsys):
        inputs, _ = themed_dirs
        (inputs / "clip.mp4").write_text("video")

        paths.resolve_input(inputs / "clip.mp4", "av")

        assert capsys.readouterr().out == ""

    def test_the_note_is_not_credited_as_a_produced_output(
        self, themed_dirs: tuple[Path, Path], monkeypatch, tmp_path: Path
    ):
        """The note names a real file, and output detection reads stdout.

        It survives only because archiving preserves mtime, so the archived
        input predates the run that mentions it. If that ever stops being true
        the input starts appearing in the results list.
        """
        inputs, past = themed_dirs
        archived = past / "clip.mp4"
        archived.write_text("archived")
        os.utime(archived, (1_000_000_000, 1_000_000_000))
        outputs_root = tmp_path / "outputs"
        outputs_root.mkdir()

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            paths.resolve_input(inputs / "clip.mp4", "av")

        reported = find_reported_outputs(buffer.getvalue().splitlines(), root=outputs_root, since=time.time())
        assert reported == []
