"""Tests for scripts.photo.remove_bg."""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

mock_rembg = MagicMock()
sys.modules["rembg"] = mock_rembg

from scripts.photo import remove_bg as remove_bg_mod  # noqa: E402
from scripts.photo.remove_bg import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_PRESET,
    MODELS,
    PRESETS,
    WEIGHTS_FILES,
    Preset,
    get_parser,
    hex_to_rgba,
    models_for_args,
    presets_for_run,
    remove_bg,
    remove_bg_batch,
    settings_for,
    weights_url,
)
from webapp._form import fields_from_parser  # noqa: E402


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

    # --model is an override with no default of its own; the effective model
    # comes from the preset and must still be u2net.
    assert args.model is None
    assert settings_for(args.preset, model=args.model).model == "u2net"
    assert args.all_presets is False
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


@patch("scripts.photo.remove_bg.move_to_past_inputs")
@patch("scripts.photo.remove_bg.default_stem", return_value="20260720_1505")
@patch("scripts.photo.remove_bg.Image")
def test_remove_bg_batch_deduplicates_output_names(mock_pil, _mock_stem, _mock_archive, tmp_path):
    """Batch outputs get unique names when prior outputs with the same stamp exist."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.jpg").touch()
    (src_dir / "b.png").touch()

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "20260720_1505_001.png").write_bytes(b"old")
    (out_dir / "20260720_1505_002.png").write_bytes(b"old")

    result_img = _mock_image()
    result_img.save.side_effect = lambda path, **kw: Path(path).touch()
    mock_pil.open.return_value = _mock_image()
    mock_rembg.remove.return_value = result_img

    result = remove_bg_batch(src_dir, out_dir)

    assert len(result) == 2
    all_outputs = sorted(out_dir.iterdir())
    assert len(all_outputs) == 4
    old_files = [p for p in all_outputs if p.read_bytes() == b"old"]
    assert len(old_files) == 2


def test_module_constants():
    assert remove_bg_mod.TITLE == "Remove background"
    assert remove_bg_mod.DESCRIPTION
    assert "image" in remove_bg_mod.ACCEPTS
    assert callable(remove_bg_mod.run)


class TestPresets:
    """A preset picker for the common case; --model stays for everyone else."""

    def test_the_default_preset_is_the_previous_default(self):
        """The no-arguments result must not change under the new front end."""
        assert settings_for(DEFAULT_PRESET) == Preset(DEFAULT_MODEL)

    def test_each_preset_names_a_real_model(self):
        for preset, settings in PRESETS.items():
            assert settings.model in MODELS, f"{preset} -> {settings.model}"

    def test_presets_are_named_for_cost_not_quality(self):
        """No model wins on every image, so the names promise speed, not results."""
        assert list(PRESETS) == ["fast", "balanced", "hq"]

    def test_balanced_and_hq_clean_the_mask(self):
        assert PRESETS["balanced"].post_process_mask is True
        assert PRESETS["hq"].post_process_mask is True
        assert PRESETS["hq"].alpha_matting is True

    def test_explicit_model_overrides_the_preset(self):
        assert settings_for("fast", model="birefnet-portrait").model == "birefnet-portrait"

    def test_explicit_flags_only_add(self):
        """A store_true flag cannot say "off", so the preset's choices survive."""
        merged = settings_for("hq", alpha_matting=False, post_process_mask=False)
        assert merged.alpha_matting is True
        merged = settings_for("fast", alpha_matting=True)
        assert merged.alpha_matting is True

    def test_unknown_preset_is_rejected(self):
        with pytest.raises(ValueError, match="unknown preset"):
            settings_for("turbo")

    def test_no_preset_pulls_the_950mb_model(self):
        """A one-click preset should not start a ~1GB download."""
        assert all(p.model != "birefnet-general" for p in PRESETS.values())


class TestAllPresets:
    def test_all_presets_runs_every_preset_in_declared_order(self):
        assert presets_for_run("hq", all_presets=True) == ("fast", "balanced", "hq")

    def test_otherwise_only_the_chosen_one(self):
        assert presets_for_run("hq", all_presets=False) == ("hq",)

    def test_models_for_args_ignores_the_override_when_comparing(self):
        args = get_parser().parse_args(["x.jpg", "--all-presets", "--model", "silueta"])
        assert models_for_args(args) == ["u2net", "isnet-general-use", "birefnet-general-lite"]

    def test_models_for_args_honours_the_override_otherwise(self):
        args = get_parser().parse_args(["x.jpg", "--preset", "hq", "--model", "silueta"])
        assert models_for_args(args) == ["silueta"]

    @patch("scripts.photo.remove_bg.move_to_past_inputs")
    @patch("scripts.photo.remove_bg.Image")
    def test_run_prefixes_outputs_and_archives_once(self, mock_pil, mock_archive, tmp_path, monkeypatch, capsys):
        src = tmp_path / "pic.jpg"
        src.write_bytes(b"x")
        out_dir = tmp_path / "out"
        monkeypatch.setattr(sys, "argv", ["prog", str(src), "-o", str(out_dir / "pic.png"), "--all-presets"])
        remove_bg_mod.run()
        printed = capsys.readouterr().out.splitlines()
        assert [Path(p).name for p in printed] == ["fast_pic.png", "balanced_pic.png", "hq_pic.png"]
        assert mock_archive.call_count == 1

    @patch("scripts.photo.remove_bg.move_to_past_inputs")
    @patch("scripts.photo.remove_bg.Image")
    def test_one_failing_preset_does_not_stop_the_others(self, mock_pil, mock_archive, tmp_path, monkeypatch, capsys):
        src = tmp_path / "pic.jpg"
        src.write_bytes(b"x")
        monkeypatch.setattr(sys, "argv", ["prog", str(src), "-o", str(tmp_path / "out" / "pic.png"), "--all-presets"])
        results = iter([RuntimeError("boom"), _mock_image(), _mock_image()])

        def _remove(*args, **kwargs):
            value = next(results)
            if isinstance(value, Exception):
                raise value
            return value

        mock_rembg.remove.side_effect = _remove
        with pytest.raises(SystemExit) as exc:
            remove_bg_mod.run()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "fast" not in captured.out
        assert "balanced_pic.png" in captured.out
        assert "hq_pic.png" in captured.out
        assert "boom" in captured.err


class TestWeightsTable:
    def test_every_selectable_model_has_a_weights_file(self):
        assert set(WEIGHTS_FILES) == set(MODELS)

    def test_weights_url_is_none_for_unknown_models(self):
        assert weights_url("nope") is None

    def test_table_matches_the_installed_rembg(self):
        """The filenames are copied out of rembg; catch it if a release moves them.

        Read as text from site-packages because this module replaces ``rembg``
        in sys.modules with a mock for every other test here.
        """
        import re  # noqa: PLC0415
        import sysconfig  # noqa: PLC0415

        sessions = Path(sysconfig.get_paths()["purelib"]) / "rembg" / "sessions"
        if not sessions.is_dir():
            pytest.skip("rembg not installed")
        published = set()
        for source in sessions.glob("*.py"):
            text = source.read_text(encoding="utf-8")
            published.update(re.findall(r"releases/download/v0\.0\.0/([^\"']+\.onnx)", text))
        for model, filename in WEIGHTS_FILES.items():
            assert filename in published, f"{model}: {filename} is not in the installed rembg"


class TestAdvancedFields:
    def test_only_the_preset_and_paths_are_in_the_basic_form(self):
        specs = fields_from_parser(get_parser())
        basic = {s.dest for s in specs if not s.advanced}
        assert basic == {"source", "output", "preset", "all_presets"}

    def test_model_and_matting_are_advanced(self):
        specs = {s.dest: s for s in fields_from_parser(get_parser())}
        for dest in ("model", "alpha_matting", "bgcolor", "only_mask"):
            assert specs[dest].advanced is True, dest

    def test_defaults_are_unchanged_when_nothing_is_touched(self):
        """Advanced fields are hidden, not removed — their defaults still apply."""
        args = get_parser().parse_args(["pic.png"])
        assert args.preset == DEFAULT_PRESET
        assert args.model is None
        assert settings_for(args.preset, model=args.model).model == DEFAULT_MODEL
        assert args.alpha_matting is False
        assert args.bgcolor is None
