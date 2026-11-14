"""Tests for the crop editor's preview: upright, size-capped, contained."""

import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from core.paths import inputs_dir
from webapp._image_preview import PreviewError, render_preview
from webapp.app import app

client = TestClient(app)

# EXIF Orientation 6: rotate 90° clockwise to display.
_ROTATE_CW = 6


def _rotated_jpeg(path: Path, size: tuple[int, int]) -> Path:
    exif = Image.Exif()
    exif[0x0112] = _ROTATE_CW
    Image.new("RGB", size, (90, 120, 150)).save(path, exif=exif)
    return path


class TestRenderPreview:
    def test_reports_the_upright_size_not_the_stored_one(self, tmp_path: Path):
        preview = render_preview(_rotated_jpeg(tmp_path / "phone.jpg", (300, 100)))
        assert (preview.width, preview.height) == (100, 300)
        assert preview.media_type == "image/jpeg"

    def test_scales_down_but_keeps_the_full_size_alongside(self, tmp_path: Path):
        src = tmp_path / "big.png"
        Image.new("RGB", (400, 200)).save(src)
        preview = render_preview(src, max_side=100)
        assert (preview.width, preview.height) == (400, 200)
        with Image.open(io.BytesIO(preview.data)) as shown:
            assert shown.size == (100, 50)

    def test_transparency_survives_as_png(self, tmp_path: Path):
        src = tmp_path / "alpha.png"
        Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(src)
        assert render_preview(src).media_type == "image/png"

    def test_a_file_that_is_not_an_image(self, tmp_path: Path):
        src = tmp_path / "notes.jpg"
        src.write_text("not an image", encoding="utf-8")
        with pytest.raises(PreviewError):
            render_preview(src)


@pytest.fixture
def staged(tmp_path: Path):
    """An image staged in the real inputs tree, removed afterwards."""
    path = _rotated_jpeg(inputs_dir("photo") / f"crop-preview-test-{tmp_path.name}.jpg", (60, 20))
    yield path
    path.unlink(missing_ok=True)


class TestEndpoint:
    def test_serves_a_staged_image_with_its_upright_size(self, staged: Path):
        response = client.get("/api/image-preview", params={"path": str(staged)})
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert (response.headers["x-image-width"], response.headers["x-image-height"]) == ("20", "60")

    def test_refuses_a_file_outside_the_inputs_tree(self, tmp_path: Path):
        outside = _rotated_jpeg(tmp_path / "elsewhere.jpg", (10, 10))
        assert client.get("/api/image-preview", params={"path": str(outside)}).status_code == 403

    def test_a_staged_non_image_is_unprocessable(self, tmp_path: Path):
        bogus = inputs_dir("photo") / f"crop-preview-bogus-{tmp_path.name}.jpg"
        bogus.write_text("nope", encoding="utf-8")
        try:
            assert client.get("/api/image-preview", params={"path": str(bogus)}).status_code == 422
        finally:
            bogus.unlink(missing_ok=True)
