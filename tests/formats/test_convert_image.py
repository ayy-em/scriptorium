"""Tests for scripts.formats.convert_image."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.formats._utils import BatchConvertError
from scripts.formats.convert_image import convert


def _mock_image(mode="RGB"):
    img = MagicMock()
    img.mode = mode
    img.convert.return_value = img
    return img


def test_convert_single_file(tmp_path):
    src = tmp_path / "photo.png"
    src.touch()
    out_dir = tmp_path / "out"
    mock_img = _mock_image()
    with patch("scripts.formats.convert_image.Image") as MockImage:
        MockImage.open.return_value = mock_img
        result = convert(src, "jpg", out_dir)
    assert len(result) == 1
    assert result[0].suffix == ".jpg"


def test_convert_rgba_to_jpeg_converts_to_rgb(tmp_path):
    src = tmp_path / "image.png"
    src.touch()
    out_dir = tmp_path / "out"
    mock_img = _mock_image(mode="RGBA")
    with patch("scripts.formats.convert_image.Image") as MockImage:
        MockImage.open.return_value = mock_img
        convert(src, "jpg", out_dir)
    mock_img.convert.assert_called_once_with("RGB")


def test_convert_rgb_to_jpeg_skips_conversion(tmp_path):
    src = tmp_path / "image.png"
    src.touch()
    out_dir = tmp_path / "out"
    mock_img = _mock_image(mode="RGB")
    with patch("scripts.formats.convert_image.Image") as MockImage:
        MockImage.open.return_value = mock_img
        convert(src, "jpg", out_dir)
    mock_img.convert.assert_not_called()


def test_convert_jpeg_passes_quality(tmp_path):
    src = tmp_path / "image.png"
    src.touch()
    out_dir = tmp_path / "out"
    mock_img = _mock_image()
    with patch("scripts.formats.convert_image.Image") as MockImage:
        MockImage.open.return_value = mock_img
        convert(src, "jpg", out_dir, quality=90)
    mock_img.save.assert_called_once()
    _, kwargs = mock_img.save.call_args
    assert kwargs.get("quality") == 90


def test_convert_png_target_has_no_quality(tmp_path):
    src = tmp_path / "image.jpg"
    src.touch()
    out_dir = tmp_path / "out"
    mock_img = _mock_image()
    with patch("scripts.formats.convert_image.Image") as MockImage:
        MockImage.open.return_value = mock_img
        convert(src, "png", out_dir)
    _, kwargs = mock_img.save.call_args
    assert "quality" not in kwargs


def test_convert_batch_processes_all_files(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name in ["a.jpg", "b.png", "c.webp"]:
        (src_dir / name).touch()
    out_dir = tmp_path / "out"
    mock_img = _mock_image()
    with patch("scripts.formats.convert_image.Image") as MockImage:
        MockImage.open.return_value = mock_img
        result = convert(src_dir, "webp", out_dir)
    assert len(result) == 3


def test_convert_batch_continues_on_error(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name in ["good.png", "bad.png"]:
        (src_dir / name).touch()
    out_dir = tmp_path / "out"

    call_count = 0

    def fake_open(path):
        nonlocal call_count
        call_count += 1
        if "bad" in str(path):
            raise OSError("corrupt image")
        return _mock_image()

    with patch("scripts.formats.convert_image.Image") as MockImage:
        MockImage.open.side_effect = fake_open
        with pytest.raises(BatchConvertError) as exc_info:
            convert(src_dir, "jpg", out_dir)

    assert len(exc_info.value.succeeded) == 1
