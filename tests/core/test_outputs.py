"""Tests for core.outputs — standardized output path resolution."""

from datetime import datetime
from unittest.mock import patch

import pytest

from core.outputs import deduplicate, default_stem, resolve_output, resolve_output_dir


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


class TestResolveOutput:
    @pytest.fixture()
    def mock_outputs(self, tmp_path):
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
    def mock_outputs(self, tmp_path):
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
