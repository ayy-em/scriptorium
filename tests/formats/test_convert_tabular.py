"""Tests for scripts.formats.convert_tabular."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.formats._utils import BatchConvertError
from scripts.formats.convert_tabular import convert


def _mock_df():
    df = MagicMock()
    df.to_csv = MagicMock()
    df.to_excel = MagicMock()
    df.to_json = MagicMock()
    return df


def test_convert_csv_to_xlsx(tmp_path):
    src = tmp_path / "data.csv"
    src.touch()
    out_dir = tmp_path / "out"
    df = _mock_df()
    with patch("scripts.formats.convert_tabular.pd") as mock_pd:
        mock_pd.read_csv.return_value = df
        result = convert(src, "xlsx", out_dir)
    assert len(result) == 1
    assert result[0].suffix == ".xlsx"
    df.to_excel.assert_called_once()


def test_convert_xlsx_to_csv(tmp_path):
    src = tmp_path / "report.xlsx"
    src.touch()
    out_dir = tmp_path / "out"
    df = _mock_df()
    with patch("scripts.formats.convert_tabular.pd") as mock_pd:
        mock_pd.read_excel.return_value = df
        convert(src, "csv", out_dir)
    df.to_csv.assert_called_once()


def test_convert_xlsx_with_sheet(tmp_path):
    src = tmp_path / "report.xlsx"
    src.touch()
    out_dir = tmp_path / "out"
    df = _mock_df()
    with patch("scripts.formats.convert_tabular.pd") as mock_pd:
        mock_pd.read_excel.return_value = df
        convert(src, "csv", out_dir, sheet="Summary")
    mock_pd.read_excel.assert_called_once_with(src, sheet_name="Summary")


def test_convert_json_to_csv(tmp_path):
    src = tmp_path / "data.json"
    src.touch()
    out_dir = tmp_path / "out"
    df = _mock_df()
    with patch("scripts.formats.convert_tabular.pd") as mock_pd:
        mock_pd.read_json.return_value = df
        convert(src, "csv", out_dir)
    df.to_csv.assert_called_once()


def test_convert_creates_output_directory(tmp_path):
    src = tmp_path / "data.csv"
    src.touch()
    out_dir = tmp_path / "out" / "nested"
    df = _mock_df()
    with patch("scripts.formats.convert_tabular.pd") as mock_pd:
        mock_pd.read_csv.return_value = df
        convert(src, "xlsx", out_dir)
    assert out_dir.is_dir()


def test_convert_batch_processes_all_files(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name in ["a.csv", "b.csv", "c.json"]:
        (src_dir / name).touch()
    out_dir = tmp_path / "out"
    df = _mock_df()
    with patch("scripts.formats.convert_tabular.pd") as mock_pd:
        mock_pd.read_csv.return_value = df
        mock_pd.read_json.return_value = df
        result = convert(src_dir, "xlsx", out_dir)
    assert len(result) == 3


def test_convert_batch_continues_on_error(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name in ["good.csv", "bad.csv"]:
        (src_dir / name).touch()
    out_dir = tmp_path / "out"

    def fake_read_csv(path, **kwargs):
        if "bad" in str(path):
            raise ValueError("parse error")
        return _mock_df()

    with patch("scripts.formats.convert_tabular.pd") as mock_pd:
        mock_pd.read_csv.side_effect = fake_read_csv
        with pytest.raises(BatchConvertError) as exc_info:
            convert(src_dir, "xlsx", out_dir)

    assert len(exc_info.value.succeeded) == 1
