"""Tests for photo.crop — the box drawn on the upright picture is the box cut."""

import os
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageCms
import pytest

from core.invocation import CALLER_ENV_VAR
from scripts.photo import crop as crop_mod
from scripts.photo.crop import Box, CropError, check_box, crop, output_ext

_REPO_ROOT = Path(__file__).parent.parent.parent

RED = (220, 20, 20)
BLUE = (20, 20, 220)

# EXIF Orientation 6: the camera was turned; rotate 90° clockwise to display.
_ROTATE_CW = 6


def _halves(path: Path, size: tuple[int, int], *, orientation: int | None = None, **save) -> Path:
    """Write an image whose left half is red and right half blue, as stored."""
    w, h = size
    image = Image.new("RGB", size, BLUE)
    image.paste(RED, (0, 0, w // 2, h))
    if orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = orientation
        save["exif"] = exif
    image.save(path, **save)
    return path


def _dominant(image: Image.Image) -> str:
    r, g, b = image.convert("RGB").resize((1, 1)).getpixel((0, 0))
    return "red" if r > b else "blue"


class TestCrop:
    def test_cuts_the_requested_box(self, tmp_path: Path):
        src = _halves(tmp_path / "in.png", (40, 20))
        out = crop(src, Box(20, 0, 20, 20), tmp_path / "out.png")
        with Image.open(out) as result:
            assert result.size == (20, 20)
            assert _dominant(result) == "blue"

    def test_a_rotated_phone_photo_crops_what_was_drawn(self, tmp_path: Path):
        """Stored 40×20 on its side; shown 20×40 upright, red on top.

        The box is drawn on the upright picture, so its top square must be red.
        Without orientation applied first, the same box would cut the stored
        left half's other end, or fall outside the image.
        """
        src = _halves(tmp_path / "phone.jpg", (40, 20), orientation=_ROTATE_CW, quality=95)
        out = crop(src, Box(0, 0, 20, 20), tmp_path / "top.png")
        with Image.open(out) as result:
            assert result.size == (20, 20)
            assert _dominant(result) == "red"
        bottom = crop(src, Box(0, 20, 20, 20), tmp_path / "bottom.png")
        with Image.open(bottom) as result:
            assert _dominant(result) == "blue"

    def test_keeps_the_colour_profile(self, tmp_path: Path):
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        src = _halves(tmp_path / "in.png", (40, 20), icc_profile=icc)
        out = crop(src, Box(0, 0, 10, 10), tmp_path / "out.jpg")
        with Image.open(out) as result:
            assert result.info.get("icc_profile") == icc

    def test_transparency_is_flattened_only_for_jpeg(self, tmp_path: Path):
        src = tmp_path / "alpha.png"
        Image.new("RGBA", (10, 10), (255, 0, 0, 128)).save(src)
        with Image.open(crop(src, Box(0, 0, 5, 5), tmp_path / "out.jpg")) as result:
            assert result.mode == "RGB"
        with Image.open(crop(src, Box(0, 0, 5, 5), tmp_path / "out.png")) as result:
            assert result.mode == "RGBA"

    def test_a_box_outside_the_image_is_refused(self, tmp_path: Path):
        src = _halves(tmp_path / "in.png", (40, 20))
        with pytest.raises(CropError, match="does not fit"):
            crop(src, Box(30, 0, 20, 20), tmp_path / "out.png")


class TestCheckBox:
    @pytest.mark.parametrize("box", [Box(0, 0, 0, 5), Box(0, 0, 5, -1)])
    def test_an_empty_box_is_refused(self, box: Box):
        with pytest.raises(CropError, match="must have a size"):
            check_box(box, (10, 10))

    @pytest.mark.parametrize("box", [Box(-1, 0, 5, 5), Box(0, 6, 5, 5), Box(6, 0, 5, 5)])
    def test_a_box_past_an_edge_is_refused(self, box: Box):
        with pytest.raises(CropError, match="does not fit"):
            check_box(box, (10, 10))

    def test_the_whole_image_is_a_valid_box(self):
        check_box(Box(0, 0, 10, 10), (10, 10))


class TestOutputExt:
    def test_same_keeps_a_writable_format(self):
        assert output_ext(Path("a.webp"), "same") == (".webp", None)

    def test_same_falls_back_to_jpeg_for_heic(self):
        ext, note = output_ext(Path("IMG_0001.HEIC"), "same")
        assert ext == ".jpg"
        assert "JPEG" in note

    def test_an_explicit_format_wins(self):
        assert output_ext(Path("a.heic"), "png") == (".png", None)


class TestRun:
    def _argv(self, monkeypatch: pytest.MonkeyPatch, *args: str) -> None:
        monkeypatch.setattr(sys, "argv", ["photo.crop", *args])

    def test_writes_the_crop_and_leaves_the_input_for_another_go(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        src = _halves(tmp_path / "in.png", (40, 20))
        out = tmp_path / "out.png"
        self._argv(monkeypatch, str(src), "--x", "0", "--y", "0", "--width", "8", "--height", "6", "-o", str(out))
        crop_mod.run()
        assert capsys.readouterr().out.strip() == str(out)
        with Image.open(out) as result:
            assert result.size == (8, 6)
        assert src.exists()

    def test_a_bad_box_fails_without_leaving_a_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ):
        src = _halves(tmp_path / "in.png", (40, 20))
        out = tmp_path / "out.png"
        self._argv(monkeypatch, str(src), "--x", "35", "--y", "0", "--width", "10", "--height", "5", "-o", str(out))
        with pytest.raises(SystemExit) as excinfo:
            crop_mod.run()
        assert excinfo.value.code == 1
        assert "does not fit" in capsys.readouterr().err
        assert not out.exists()


def test_the_command_line_points_at_the_web_ui():
    """photo.crop is UI_ONLY: a terminal run, --help included, is refused."""
    env = {k: v for k, v in os.environ.items() if k != CALLER_ENV_VAR}
    result = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "main.py"), "photo.crop", "--help"],
        capture_output=True,
        text=True,
        env=env,
        cwd=_REPO_ROOT,
        check=False,
        timeout=120,
    )
    assert result.returncode == 2
    assert "web UI only" in result.stderr


def test_a_heic_photo_crops_to_jpeg(tmp_path: Path):
    """What most phones write; pillow-heif reads it, the crop is saved as JPEG."""
    pillow_heif = pytest.importorskip("pillow_heif")
    pillow_heif.register_heif_opener()
    src = tmp_path / "IMG_0001.heic"
    Image.new("RGB", (64, 32), RED).save(src)
    ext, _ = output_ext(src, "same")
    out = crop(src, Box(0, 0, 16, 16), tmp_path / f"out{ext}")
    with Image.open(out) as result:
        assert (result.format, result.size) == ("JPEG", (16, 16))
