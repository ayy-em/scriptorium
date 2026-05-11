"""Tests for scripts.av.to_anim."""

from unittest.mock import patch

import pytest

from scripts.av.to_anim import to_anim


def test_gif_calls_run_ffmpeg_twice(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path)
    assert mock_ff.call_count == 2


def test_webp_calls_run_ffmpeg_once(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fmt="webp")
    assert mock_ff.call_count == 1


def test_gif_first_pass_uses_palettegen(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path)
    first_call_args = mock_ff.call_args_list[0][0][0]
    vf_value = first_call_args[first_call_args.index("-vf") + 1]
    assert "palettegen" in vf_value


def test_gif_second_pass_uses_paletteuse(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path)
    second_call_args = mock_ff.call_args_list[1][0][0]
    fc_value = second_call_args[second_call_args.index("-filter_complex") + 1]
    assert "paletteuse" in fc_value


def test_webp_uses_libwebp_codec(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fmt="webp")
    args = mock_ff.call_args[0][0]
    assert "-vcodec" in args
    assert args[args.index("-vcodec") + 1] == "libwebp"


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
    assert "scale=480:-1" in vf_value


def test_no_width_omits_scale_filter(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path)
    first_call_args = mock_ff.call_args_list[0][0][0]
    vf_value = first_call_args[first_call_args.index("-vf") + 1]
    assert "scale" not in vf_value


def test_returns_gif_path_by_default(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg"):
        result = to_anim(src, "0", "5", tmp_path)
    assert result.suffix == ".gif"


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
        to_anim(src, "0", "5", tmp_path, loop=3)
    second_call_args = mock_ff.call_args_list[1][0][0]
    assert "-loop" in second_call_args
    assert second_call_args[second_call_args.index("-loop") + 1] == "3"


def test_webp_passes_loop_to_ffmpeg(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path, fmt="webp", loop=2)
    args = mock_ff.call_args[0][0]
    assert "-loop" in args
    assert args[args.index("-loop") + 1] == "2"


def test_default_loop_is_zero(tmp_path):
    src = tmp_path / "clip.mp4"
    src.touch()
    with patch("scripts.av.to_anim.run_ffmpeg") as mock_ff:
        to_anim(src, "0", "5", tmp_path)
    second_call_args = mock_ff.call_args_list[1][0][0]
    assert second_call_args[second_call_args.index("-loop") + 1] == "0"
