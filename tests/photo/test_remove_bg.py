"""Tests for scripts.photo.remove_bg."""

import sys
from unittest.mock import MagicMock, patch

import pytest

mock_rembg = MagicMock()
sys.modules["rembg"] = mock_rembg

from scripts.photo import remove_bg as remove_bg_mod  # noqa: E402
from scripts.photo.remove_bg import get_parser, remove_bg, remove_bg_batch  # noqa: E402


def _mock_image():
    img = MagicMock()
    img.mode = "RGBA"
    return img


@pytest.fixture(autouse=True)
def _reset_rembg_mock():
    mock_rembg.reset_mock()
    mock_rembg.remove.return_value = _mock_image()


@patch("scripts.photo.remove_bg.Image")
def test_remove_bg_single_file(mock_pil, tmp_path):
    src = tmp_path / "photo.jpg"
    src.touch()
    out = tmp_path / "out" / "result.png"
    result_img = _mock_image()
    mock_pil.open.return_value = _mock_image()
    mock_rembg.remove.return_value = result_img

    remove_bg(src, out)

    mock_pil.open.assert_called_once_with(src)
    mock_rembg.remove.assert_called_once()
    result_img.save.assert_called_once_with(out, format="PNG")


@patch("scripts.photo.remove_bg.Image")
def test_remove_bg_batch_single_file(mock_pil, tmp_path):
    src = tmp_path / "photo.png"
    src.touch()
    out_dir = tmp_path / "out"
    mock_pil.open.return_value = _mock_image()

    result = remove_bg_batch(src, out_dir)

    assert len(result) == 1
    assert result[0].suffix == ".png"


@patch("scripts.photo.remove_bg.Image")
def test_remove_bg_batch_directory(mock_pil, tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name in ["a.jpg", "b.png", "c.webp"]:
        (src_dir / name).touch()
    out_dir = tmp_path / "out"
    mock_pil.open.return_value = _mock_image()

    result = remove_bg_batch(src_dir, out_dir)

    assert len(result) == 3
    assert all(p.suffix == ".png" for p in result)


@patch("scripts.photo.remove_bg.Image")
def test_remove_bg_batch_skips_non_image_files(mock_pil, tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "photo.jpg").touch()
    (src_dir / "readme.txt").touch()
    (src_dir / "data.csv").touch()
    out_dir = tmp_path / "out"
    mock_pil.open.return_value = _mock_image()

    result = remove_bg_batch(src_dir, out_dir)

    assert len(result) == 1


def test_remove_bg_batch_raises_on_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        remove_bg_batch(tmp_path / "nonexistent", tmp_path / "out")


@patch("scripts.photo.remove_bg.Image")
def test_remove_bg_batch_reports_failures(mock_pil, tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "good.png").touch()
    (src_dir / "bad.png").touch()

    def fake_open(path):
        if "bad" in str(path):
            raise OSError("corrupt image")
        return _mock_image()

    mock_pil.open.side_effect = fake_open

    with pytest.raises(RuntimeError, match="1 of 2"):
        remove_bg_batch(src_dir, tmp_path / "out")


@patch("scripts.photo.remove_bg.Image")
def test_remove_bg_batch_empty_directory(mock_pil, tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    out_dir = tmp_path / "out"

    result = remove_bg_batch(src_dir, out_dir)

    assert result == []
    mock_pil.open.assert_not_called()


def test_get_parser_requires_source():
    parser = get_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_module_constants():
    assert remove_bg_mod.TITLE == "Remove background"
    assert remove_bg_mod.DESCRIPTION
    assert "image" in remove_bg_mod.ACCEPTS
    assert callable(remove_bg_mod.run)
