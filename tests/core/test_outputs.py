"""Tests for core.outputs — standardized output path resolution."""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from core.invocation import CALLER_ENV_VAR
from core.outputs import (
    anchor_user_path,
    deduplicate,
    default_stem,
    names_a_file,
    relative_root,
    resolve_output,
    resolve_output_dir,
    resolve_single_output,
)


def _fake_home(tmp_path, monkeypatch):
    """Point tilde expansion at a throwaway directory.

    ``Path.expanduser`` reads the environment rather than calling ``Path.home``,
    so patching the method is not enough — the variables are what has to move.

    Args:
        tmp_path: Test-scoped temporary directory.
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        The directory ``~`` now expands to.
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


class TestDefaultStem:
    def test_matches_timestamp_format(self):
        stem = default_stem()
        datetime.strptime(stem, "%Y%m%d_%H%M")

    def test_length(self):
        assert len(default_stem()) == 13  # YYYYMMDD_HHmm


class TestDeduplicate:
    def test_no_collision(self, tmp_path):
        path = tmp_path / "file.pdf"
        assert deduplicate(path) == path

    def test_single_collision(self, tmp_path):
        path = tmp_path / "file.pdf"
        path.touch()
        assert deduplicate(path) == tmp_path / "file_001.pdf"

    def test_multiple_collisions(self, tmp_path):
        path = tmp_path / "file.pdf"
        path.touch()
        (tmp_path / "file_001.pdf").touch()
        (tmp_path / "file_002.pdf").touch()
        assert deduplicate(path) == tmp_path / "file_003.pdf"

    def test_preserves_extension(self, tmp_path):
        path = tmp_path / "sheet.png"
        path.touch()
        result = deduplicate(path)
        assert result.suffix == ".png"
        assert result.stem == "sheet_001"

    def test_all_slots_exhausted(self, tmp_path):
        path = tmp_path / "file.pdf"
        path.touch()
        for i in range(1, 1000):
            (tmp_path / f"file_{i:03d}.pdf").touch()
        with pytest.raises(FileExistsError):
            deduplicate(path)


class TestAnchorUserPath:
    """Where a user-supplied path actually points.

    Nothing typed into the web UI goes through a shell, so this is the only
    thing standing between ``~/Downloads/x.txt`` and a directory named ``~``.
    """

    @pytest.fixture()
    def webapp(self, tmp_path, monkeypatch):
        """Web UI caller, with home and the managed outputs tree redirected."""
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        home = _fake_home(tmp_path, monkeypatch)
        managed = tmp_path / "managed"
        managed.mkdir()
        monkeypatch.setattr("core.outputs.outputs_dir", lambda theme: managed)
        return home, managed

    @pytest.fixture()
    def cli(self, tmp_path, monkeypatch):
        """Command-line caller standing in a known directory."""
        monkeypatch.delenv(CALLER_ENV_VAR, raising=False)
        home = _fake_home(tmp_path, monkeypatch)
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        return home, cwd

    def test_tilde_expands_to_home(self, webapp):
        home, _ = webapp
        assert anchor_user_path("~/Downloads/x.txt", theme="speech") == home / "Downloads" / "x.txt"

    def test_tilde_result_is_absolute(self, webapp):
        assert anchor_user_path("~/Downloads/x.txt", theme="speech").is_absolute()

    def test_bare_tilde_is_home_itself(self, webapp):
        home, _ = webapp
        assert anchor_user_path("~", theme="speech") == home

    def test_absolute_path_untouched(self, webapp, tmp_path):
        target = tmp_path / "elsewhere" / "x.txt"
        assert anchor_user_path(str(target), theme="speech") == target

    def test_relative_with_directory_part_anchors_to_home_in_webapp(self, webapp):
        home, _ = webapp
        assert anchor_user_path("Downloads/x.txt", theme="speech") == home / "Downloads" / "x.txt"

    def test_bare_name_anchors_to_managed_outputs_in_webapp(self, webapp):
        _, managed = webapp
        assert anchor_user_path("x.txt", theme="speech") == managed / "x.txt"

    def test_relative_with_directory_part_anchors_to_cwd_on_the_cli(self, cli):
        _, cwd = cli
        assert anchor_user_path("Downloads/x.txt", theme="speech") == cwd / "Downloads" / "x.txt"

    def test_bare_name_anchors_to_cwd_on_the_cli(self, cli):
        _, cwd = cli
        assert anchor_user_path("x.txt", theme="speech") == cwd / "x.txt"

    def test_tilde_expands_on_the_cli_too(self, cli):
        home, _ = cli
        assert anchor_user_path("~/x.txt", theme="speech") == home / "x.txt"

    def test_accepts_a_path_object(self, webapp):
        home, _ = webapp
        assert anchor_user_path(Path("~/x.txt"), theme="speech") == home / "x.txt"

    def test_relative_root_follows_the_caller(self, webapp):
        home, _ = webapp
        assert relative_root() == home


class TestResolveOutputAnchoring:
    """``resolve_output`` inherits anchoring from ``anchor_user_path``.

    Its absence is what put a transcript in ``<repo>/~/Downloads/`` instead of
    the user's actual Downloads folder.
    """

    @pytest.fixture()
    def webapp(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        home = _fake_home(tmp_path, monkeypatch)
        (home / "Downloads").mkdir(parents=True)
        managed = tmp_path / "managed"
        managed.mkdir()
        monkeypatch.setattr("core.outputs.outputs_dir", lambda theme: managed)
        monkeypatch.chdir(managed)
        return home, managed

    def test_tilde_output_lands_in_the_real_home(self, webapp):
        home, _ = webapp
        result = resolve_output("~/Downloads/transc.txt", theme="speech", ext=".txt")
        assert result == home / "Downloads" / "transc.txt"

    def test_no_literal_tilde_directory_is_created(self, webapp, tmp_path):
        resolve_output("~/Downloads/transc.txt", theme="speech", ext=".txt")
        assert not (tmp_path / "managed" / "~").exists()
        assert not Path("~").exists()

    def test_tilde_directory_output_lands_in_the_real_home(self, webapp):
        home, _ = webapp
        result = resolve_output("~/Downloads", theme="speech", ext=".txt")
        assert result.parent == home / "Downloads"

    def test_relative_output_dir_anchors_to_home(self, webapp):
        home, _ = webapp
        result = resolve_output("Downloads/transc.txt", theme="speech", ext=".txt")
        assert result == home / "Downloads" / "transc.txt"

    def test_output_dir_helper_expands_tilde_too(self, webapp):
        home, _ = webapp
        assert resolve_output_dir("~/Downloads", theme="speech") == home / "Downloads"

    def test_output_dir_helper_expands_tilde_on_a_file_path(self, webapp):
        home, _ = webapp
        assert resolve_output_dir("~/Downloads/x.txt", theme="speech") == home / "Downloads"


class TestResolveOutput:
    @pytest.fixture()
    def mock_outputs(self, tmp_path, monkeypatch):
        """The managed outputs dir, as the webapp caller sees it."""
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        d = tmp_path / "default_outputs"
        d.mkdir()
        with patch("core.outputs.outputs_dir", return_value=d):
            yield d

    def test_none_returns_timestamp_in_default_dir(self, mock_outputs):
        result = resolve_output(None, theme="av", ext=".pdf")
        assert result.parent == mock_outputs
        assert result.suffix == ".pdf"
        datetime.strptime(result.stem, "%Y%m%d_%H%M")

    def test_existing_dir_uses_timestamp_filename(self, tmp_path, mock_outputs):
        custom = tmp_path / "custom"
        custom.mkdir()
        result = resolve_output(str(custom), theme="av", ext=".pdf")
        assert result.parent == custom
        assert result.suffix == ".pdf"

    def test_filename_only_placed_in_default_dir(self, mock_outputs):
        result = resolve_output("report.pdf", theme="av", ext=".pdf")
        assert result.parent == mock_outputs
        assert result.name == "report.pdf"

    def test_full_path_used_as_is(self, tmp_path, mock_outputs):
        full = tmp_path / "my" / "custom" / "output.pdf"
        result = resolve_output(str(full), theme="av", ext=".pdf")
        assert result == full
        assert full.parent.exists()

    def test_no_extension_treated_as_directory(self, tmp_path, mock_outputs):
        new_dir = tmp_path / "my_output_folder"
        result = resolve_output(str(new_dir), theme="av", ext=".pdf")
        assert result.parent == new_dir
        assert result.suffix == ".pdf"
        assert new_dir.exists()

    def test_collision_avoidance(self, mock_outputs):
        first = resolve_output("report.pdf", theme="av", ext=".pdf")
        first.touch()
        second = resolve_output("report.pdf", theme="av", ext=".pdf")
        assert second != first
        assert second.stem == "report_001"

    def test_ext_normalized_without_dot(self, mock_outputs):
        result = resolve_output(None, theme="av", ext="pdf")
        assert result.suffix == ".pdf"

    def test_makedirs_creates_parents(self, tmp_path, mock_outputs):
        deep = tmp_path / "a" / "b" / "c" / "file.pdf"
        result = resolve_output(str(deep), theme="av", ext=".pdf")
        assert result.parent.exists()

    def test_makedirs_false_skips_creation(self, tmp_path, mock_outputs):
        deep = tmp_path / "nonexistent" / "file.pdf"
        result = resolve_output(str(deep), theme="av", ext=".pdf", makedirs=False)
        assert not result.parent.exists()


class TestResolveOutputDir:
    @pytest.fixture()
    def mock_outputs(self, tmp_path, monkeypatch):
        """The managed outputs dir, as the webapp caller sees it."""
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        d = tmp_path / "default_outputs"
        d.mkdir()
        with patch("core.outputs.outputs_dir", return_value=d):
            yield d

    def test_none_returns_default_dir(self, mock_outputs):
        assert resolve_output_dir(None, theme="formats") == mock_outputs

    def test_existing_dir_returned(self, tmp_path, mock_outputs):
        custom = tmp_path / "custom"
        custom.mkdir()
        assert resolve_output_dir(str(custom), theme="formats") == custom

    def test_file_path_extracts_parent(self, tmp_path, mock_outputs):
        result = resolve_output_dir(str(tmp_path / "sub" / "file.png"), theme="formats")
        assert result == tmp_path / "sub"

    def test_bare_filename_returns_default_dir(self, mock_outputs):
        assert resolve_output_dir("file.png", theme="formats") == mock_outputs

    def test_no_extension_treated_as_dir(self, tmp_path, mock_outputs):
        new_dir = tmp_path / "batch_output"
        result = resolve_output_dir(str(new_dir), theme="formats")
        assert result == new_dir
        assert new_dir.exists()


class TestNamesAFile:
    def test_path_with_extension_names_a_file(self):
        assert names_a_file("D:/out/pic.png") is True

    def test_bare_directory_does_not(self):
        assert names_a_file("D:/out") is False

    def test_none_does_not(self):
        assert names_a_file(None) is False

    def test_accepts_a_path_object(self):
        assert names_a_file(Path("out/pic.png")) is True


class TestResolveSingleOutput:
    def test_returns_the_exact_path_the_user_named(self, tmp_path):
        target = tmp_path / "sub" / "my_name.png"
        assert resolve_single_output(target, theme="photo", ext=".png") == target

    def test_returns_none_for_a_directory(self, tmp_path):
        assert resolve_single_output(tmp_path, theme="photo", ext=".png") is None

    def test_returns_none_for_no_output(self):
        assert resolve_single_output(None, theme="photo", ext=".png") is None

    def test_deduplicates_against_an_existing_file(self, tmp_path):
        target = tmp_path / "taken.png"
        target.write_bytes(b"x")
        got = resolve_single_output(target, theme="photo", ext=".png")
        assert got != target
        assert got.name == "taken_001.png"

    def test_bare_filename_lands_in_the_theme_outputs_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        monkeypatch.setattr("core.paths._user_data_dir", lambda: tmp_path)
        monkeypatch.setattr("core.outputs.outputs_dir", lambda theme: tmp_path / theme)
        got = resolve_single_output("just_a_name.png", theme="photo", ext=".png")
        assert got.parent.name == "photo"
        assert got.name == "just_a_name.png"
