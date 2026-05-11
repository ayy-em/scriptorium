"""Tests for scripts.av.to_anim."""

from unittest.mock import patch

import pytest

from scripts.av.to_anim import _cap_scale_filter, to_anim

# ---------------------------------------------------------------------------
# _cap_scale_filter unit tests (pure logic, no I/O)
# ---------------------------------------------------------------------------


def test_cap_scale_filter_landscape_oversized_downscales():
    assert _cap_scale_filter(3840, 2160, None) == "scale=1920:-2:flags=lanczos"


def test_cap_scale_filter_landscape_fits_returns_none():
    assert _cap_scale_filter(1280, 720, None) is None


def test_cap_scale_filter_portrait_oversized_downscales():
    result = _cap_scale_filter(1080, 1920, None)
    assert result is not None
    assert "scale=" in result
    assert ":-2:flags=lanczos" in result


def test_cap_scale_filter_portrait_fits_returns_none():
    assert _cap_scale_filter(720, 1280, None) is None


def test_cap_scale_filter_user_width_honoured():
    # 1280x720 fits within landscape cap but user wants 480px wide
    result = _cap_scale_filter(1280, 720, 480)
    assert result == "scale=480:-2:flags=lanczos"


def test_cap_scale_filter_user_width_capped_by_landscape_limit():
    # User asks for 2000px but landscape cap is 1920
    result = _cap_scale_filter(3840, 2160, 2000)
    assert result is not None
    w = int(result.split("scale=")[1].split(":")[0])
    assert w <= 1920


def test_cap_scale_filter_output_width_is_even():
    # Source that would produce a fractional width after scaling
    result = _cap_scale_filter(1921, 1081, None)
    assert result is not None
    w = int(result.split("scale=")[1].split(":")[0])
    assert w % 2 == 0


# ---------------------------------------------------------------------------
# to_anim integration tests (run_ffmpeg mocked; probe_streams mocked for scale)
# ---------------------------------------------------------------------------


def _patch_probe(w: int, h: int):
    return patch(
        "scripts.av.to_anim.probe_streams",
        return_value=[{"codec_type": "video", "width": w, "height": h}],
    )


def test_gif_calls_run_ffmpeg_twice(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fmt="gif")
    assert mock_ff.call_count == 2


def test_webp_calls_run_ffmpeg_once(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fmt="webp")
    assert mock_ff.call_count == 1


def test_gif_first_pass_uses_palettegen_stats_mode_diff(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fmt="gif")
    first_call_args = mock_ff.call_args_list[0][0][0]
    vf_value = first_call_args[first_call_args.index("-vf") + 1]
    assert "palettegen=stats_mode=diff" in vf_value


def test_gif_second_pass_uses_paletteuse(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fmt="gif")
    second_call_args = mock_ff.call_args_list[1][0][0]
    fc_value = second_call_args[second_call_args.index("-filter_complex") + 1]
    assert "paletteuse" in fc_value


def test_webp_uses_libwebp_codec(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fmt="webp")
    args = mock_ff.call_args[0][0]
    assert args[args.index("-vcodec") + 1] == "libwebp"


def test_webp_has_quality_and_compression_settings(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fmt="webp")
    args = mock_ff.call_args[0][0]
    assert "-quality" in args
    assert "-compression_level" in args


def test_fps_appears_in_filter(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fps=10)
    first_call_args = mock_ff.call_args_list[0][0][0]
    vf_value = first_call_args[first_call_args.index("-vf") + 1]
    assert "fps=10" in vf_value


def test_width_adds_scale_filter(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, width=480)
    first_call_args = mock_ff.call_args_list[0][0][0]
    vf_value = first_call_args[first_call_args.index("-vf") + 1]
    assert "scale=480:-2" in vf_value


def test_oversized_source_is_scaled_down(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with _patch_probe(3840, 2160), patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path)
    first_call_args = mock_ff.call_args_list[0][0][0]
    vf_value = first_call_args[first_call_args.index("-vf") + 1]
    assert "scale=1920:-2" in vf_value


def test_within_cap_source_has_no_scale_filter(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with _patch_probe(1280, 720), patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path)
    first_call_args = mock_ff.call_args_list[0][0][0]
    vf_value = first_call_args[first_call_args.index("-vf") + 1]
    assert "scale" not in vf_value


def test_no_width_and_probe_fails_omits_scale(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.probe_streams", side_effect=Exception("ffprobe unavailable")):
        with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
            to_anim(src, "0", "5", tmp_path)
    first_call_args = mock_ff.call_args_list[0][0][0]
    vf_value = first_call_args[first_call_args.index("-vf") + 1]
    assert "scale" not in vf_value


def test_returns_webp_path_by_default(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg"):
        result = to_anim(src, "0", "5", tmp_path)
    assert result.suffix == ".webp"


def test_returns_webp_path_for_webp_format(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg"):
        result = to_anim(src, "0", "5", tmp_path, fmt="webp")
    assert result.suffix == ".webp"


def test_custom_filename_used_in_output(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg"):
        result = to_anim(src, "0", "5", tmp_path, filename="out")
    assert result.stem == "out"


def test_default_filename_uses_source_stem(tmp_path):
    src = tmp_path / "myvideo.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg"):
        result = to_anim(src, "0", "5", tmp_path)
    assert result.stem == "myvideo"


def test_creates_output_directory(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    out_dir = tmp_path / "nested" / "outputs"
    with patch("scripts.av.to_anim.run_ffmpeg"):
        to_anim(src, "0", "5", out_dir)
    assert out_dir.is_dir()


def test_raises_on_unknown_format(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with pytest.raises(ValueError, match="Unknown format"):
        to_anim(src, "0", "5", tmp_path, fmt="avi")


def test_timestamps_passed_to_ffmpeg(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "00:00:10", "00:00:20", tmp_path)
    first_call_args = mock_ff.call_args_list[0][0][0]
    assert "00:00:10" in first_call_args
    assert "00:00:20" in first_call_args


def test_speed_adds_setpts_filter(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, speed=2.0)
    first_call_args = mock_ff.call_args_list[0][0][0]
    vf_value = first_call_args[first_call_args.index("-vf") + 1]
    assert "setpts=0.5*PTS" in vf_value


def test_speed_setpts_comes_before_fps(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, speed=2.0)
    first_call_args = mock_ff.call_args_list[0][0][0]
    vf_value = first_call_args[first_call_args.index("-vf") + 1]
    assert vf_value.index("setpts") < vf_value.index("fps")


def test_default_speed_omits_setpts(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path)
    first_call_args = mock_ff.call_args_list[0][0][0]
    vf_value = first_call_args[first_call_args.index("-vf") + 1]
    assert "setpts" not in vf_value


def test_invalid_speed_raises(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with pytest.raises(ValueError, match="speed"):
        to_anim(src, "0", "5", tmp_path, speed=0.0)


def test_gif_passes_loop_to_ffmpeg(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fmt="gif", loop=3)
    second_call_args = mock_ff.call_args_list[1][0][0]
    assert second_call_args[second_call_args.index("-loop") + 1] == "3"


def test_webp_passes_loop_to_ffmpeg(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fmt="webp", loop=2)
    args = mock_ff.call_args[0][0]
    assert args[args.index("-loop") + 1] == "2"


def test_default_loop_is_zero(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fmt="gif")
    second_call_args = mock_ff.call_args_list[1][0][0]
    assert second_call_args[second_call_args.index("-loop") + 1] == "0"
