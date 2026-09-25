"""Tests for scripts.formats.convert_image."""

from unittest.mock import MagicMock, patch

from PIL import Image
import pytest

from core.images import ensure_image_formats
from scripts.formats._utils import IMAGE_EXTS, BatchConvertError
from scripts.formats.convert_image import _convert, convert


def _mock_image(mode="RGB"):
    img = MagicMock()
    # exif_transpose hands back a copy when there is nothing to rotate.
    img.copy.return_value = img
    img.mode = mode
    img.convert.return_value = img
    return img


def test_heic_is_an_accepted_input():
    assert {".heic", ".heif"} <= IMAGE_EXTS


def test_heic_opens_through_pillow(tmp_path):
    """pillow-heif registers an opener; a real .heic then round-trips to PNG."""
    pillow_heif = pytest.importorskip("pillow_heif")
    ensure_image_formats()
    src = tmp_path / "photo.heic"
    heif = pillow_heif.from_pillow(Image.new("RGB", (8, 4), (200, 30, 30)))
    heif.save(src)
    out = tmp_path / "photo.png"
    _convert(src, out, quality=90)
    with Image.open(out) as img:
        assert img.size == (8, 4)


def test_exif_orientation_is_baked_in(tmp_path):
    """A portrait shot stored sideways with an orientation tag must come out upright."""
    src = tmp_path / "rotated.jpg"
    img = Image.new("RGB", (8, 4))
    exif = img.getexif()
    exif[0x0112] = 6  # rotate 90° clockwise to display
    img.save(src, exif=exif.tobytes())
    out = tmp_path / "upright.png"
    _convert(src, out, quality=90)
    with Image.open(out) as result:
        assert result.size == (4, 8)


def test_convert_single_file(tmp_path):
    src = tmp_path / "photo.png"
    src.touch()
    out_dir = tmp_path / "out"
    mock_img = _mock_image()
    with patch("scripts.formats.convert_image.Image") as mock_pil:
        mock_pil.open.return_value = mock_img
        result = convert(src, "jpg", out_dir)
    assert len(result) == 1
    assert result[0].suffix == ".jpg"


def test_convert_rgba_to_jpeg_converts_to_rgb(tmp_path):
    src = tmp_path / "image.png"
    src.touch()
    out_dir = tmp_path / "out"
    mock_img = _mock_image(mode="RGBA")
    with patch("scripts.formats.convert_image.Image") as mock_pil:
        mock_pil.open.return_value = mock_img
        convert(src, "jpg", out_dir)
    mock_img.convert.assert_called_once_with("RGB")


def test_convert_rgb_to_jpeg_skips_conversion(tmp_path):
    src = tmp_path / "image.png"
    src.touch()
    out_dir = tmp_path / "out"
    mock_img = _mock_image(mode="RGB")
    with patch("scripts.formats.convert_image.Image") as mock_pil:
        mock_pil.open.return_value = mock_img
        convert(src, "jpg", out_dir)
    mock_img.convert.assert_not_called()


def test_convert_jpeg_passes_quality(tmp_path):
    src = tmp_path / "image.png"
    src.touch()
    out_dir = tmp_path / "out"
    mock_img = _mock_image()
    with patch("scripts.formats.convert_image.Image") as mock_pil:
        mock_pil.open.return_value = mock_img
        convert(src, "jpg", out_dir, quality=90)
    mock_img.save.assert_called_once()
    _, kwargs = mock_img.save.call_args
    assert kwargs.get("quality") == 90


def test_convert_png_target_has_no_quality(tmp_path):
    src = tmp_path / "image.jpg"
    src.touch()
    out_dir = tmp_path / "out"
    mock_img = _mock_image()
    with patch("scripts.formats.convert_image.Image") as mock_pil:
        mock_pil.open.return_value = mock_img
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
    with patch("scripts.formats.convert_image.Image") as mock_pil:
        mock_pil.open.return_value = mock_img
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

    with patch("scripts.formats.convert_image.Image") as mock_pil:
        mock_pil.open.side_effect = fake_open
        with pytest.raises(BatchConvertError) as exc_info:
            convert(src_dir, "jpg", out_dir)

    assert len(exc_info.value.succeeded) == 1
