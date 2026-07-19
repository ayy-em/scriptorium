"""Tests for scripts.photo.remove_bg."""

import sys
from unittest.mock import MagicMock, patch

import pytest

mock_rembg = MagicMock()
sys.modules["rembg"] = mock_rembg

from scripts.photo import remove_bg as remove_bg_mod  # noqa: E402
from scripts.photo.remove_bg import (  # noqa: E402
    MODELS,
    get_parser,
    hex_to_rgba,
    remove_bg,
    remove_bg_batch,
)


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


def test_get_parser_source_is_optional():
    args = get_parser().parse_args([])
    assert args.source is None


def test_get_parser_defaults():
    args = get_parser().parse_args(["photo.jpg"])

    assert args.model == "u2net"
    assert args.alpha_matting is False
    assert args.alpha_matting_foreground_threshold == 240
    assert args.alpha_matting_background_threshold == 10
    assert args.alpha_matting_erode_size == 10
    assert args.only_mask is False
    assert args.post_process_mask is False
    assert args.bgcolor is None


def test_get_parser_accepts_all_options():
    args = get_parser().parse_args(
        [
            "photo.jpg",
            "--model",
            "birefnet-portrait",
            "--alpha-matting",
            "--alpha-matting-foreground-threshold",
            "200",
            "--alpha-matting-background-threshold",
            "20",
            "--alpha-matting-erode-size",
            "5",
            "--only-mask",
            "--post-process-mask",
            "--bgcolor",
            "#ffffff",
        ]
    )

    assert args.model == "birefnet-portrait"
    assert args.alpha_matting is True
    assert args.alpha_matting_foreground_threshold == 200
    assert args.alpha_matting_background_threshold == 20
    assert args.alpha_matting_erode_size == 5
    assert args.only_mask is True
    assert args.post_process_mask is True
    assert args.bgcolor == (255, 255, 255, 255)


def test_get_parser_rejects_unknown_model():
    with pytest.raises(SystemExit):
        get_parser().parse_args(["photo.jpg", "--model", "nonexistent"])


def test_get_parser_help_text_on_all_options():
    parser = get_parser()
    for action in parser._actions:
        assert action.help, f"missing help text for {action.dest}"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#ffffff", (255, 255, 255, 255)),
        ("ffffff", (255, 255, 255, 255)),
        ("#fff", (255, 255, 255, 255)),
        ("#00ff0080", (0, 255, 0, 128)),
        ("#000000", (0, 0, 0, 255)),
    ],
)
def test_hex_to_rgba_valid(value, expected):
    assert hex_to_rgba(value) == expected


@pytest.mark.parametrize("value", ["", "#ff", "#fffff", "#gggggg", "not a color"])
def test_hex_to_rgba_invalid(value):
    with pytest.raises(ValueError, match="invalid hex color"):
        hex_to_rgba(value)


def test_models_list_excludes_special_models():
    assert "u2net" in MODELS
    assert "sam" not in MODELS
    assert not any("custom" in m for m in MODELS)


@patch("scripts.photo.remove_bg.Image")
def test_remove_bg_forwards_options(mock_pil, tmp_path):
    src = tmp_path / "photo.jpg"
    src.touch()
    mock_pil.open.return_value = _mock_image()

    remove_bg(
        src,
        tmp_path / "out.png",
        alpha_matting=True,
        alpha_matting_foreground_threshold=200,
        alpha_matting_background_threshold=20,
        alpha_matting_erode_size=5,
        only_mask=True,
        post_process_mask=True,
        bgcolor=(255, 255, 255, 255),
    )

    kwargs = mock_rembg.remove.call_args.kwargs
    assert kwargs["alpha_matting"] is True
    assert kwargs["alpha_matting_foreground_threshold"] == 200
    assert kwargs["alpha_matting_background_threshold"] == 20
    assert kwargs["alpha_matting_erode_size"] == 5
    assert kwargs["only_mask"] is True
    assert kwargs["post_process_mask"] is True
    assert kwargs["bgcolor"] == (255, 255, 255, 255)


@patch("scripts.photo.remove_bg.Image")
def test_remove_bg_creates_session_from_model(mock_pil, tmp_path):
    src = tmp_path / "photo.jpg"
    src.touch()
    mock_pil.open.return_value = _mock_image()

    remove_bg(src, tmp_path / "out.png", model="isnet-anime")

    mock_rembg.new_session.assert_called_once_with("isnet-anime")


@patch("scripts.photo.remove_bg.move_to_past_inputs")
@patch("scripts.photo.remove_bg.Image")
def test_remove_bg_batch_archives_processed_inputs(mock_pil, mock_archive, tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.jpg").touch()
    (src_dir / "b.png").touch()
    mock_pil.open.return_value = _mock_image()

    remove_bg_batch(src_dir, tmp_path / "out")

    assert mock_archive.call_count == 2


@patch("scripts.photo.remove_bg.move_to_past_inputs")
@patch("scripts.photo.remove_bg.Image")
def test_remove_bg_batch_does_not_archive_failed_inputs(mock_pil, mock_archive, tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "bad.png").touch()
    mock_pil.open.side_effect = OSError("corrupt image")

    with pytest.raises(RuntimeError):
        remove_bg_batch(src_dir, tmp_path / "out")

    mock_archive.assert_not_called()


@patch("scripts.photo.remove_bg.Image")
def test_remove_bg_batch_reuses_session(mock_pil, tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for name in ["a.jpg", "b.png", "c.webp"]:
        (src_dir / name).touch()
    mock_pil.open.return_value = _mock_image()

    result = remove_bg_batch(src_dir, tmp_path / "out", model="birefnet-general")

    assert len(result) == 3
    mock_rembg.new_session.assert_called_once_with("birefnet-general")


def test_module_constants():
    assert remove_bg_mod.TITLE == "Remove background"
    assert remove_bg_mod.DESCRIPTION
    assert "image" in remove_bg_mod.ACCEPTS
    assert callable(remove_bg_mod.run)
