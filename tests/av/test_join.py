"""Tests for scripts.av.join."""

from pathlib import Path
import time
from unittest.mock import patch

import pytest

from scripts.av.join import (
    _detect_trailing_black,
    _find_last_keyframe_before,
    _preprocess_file,
    _sort_files,
    join,
)

_VIDEO = {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "duration": "30.0"}
_AUDIO = {"codec_type": "audio", "codec_name": "aac"}
_STREAMS = [_VIDEO, _AUDIO]


def _make_files(directory: Path, count: int, suffix: str = ".mp4") -> list[Path]:
    files = []
    for i in range(count):
        f = directory / f"clip_{i:02d}{suffix}"
        f.touch()
        files.append(f)
    return files


# ---------------------------------------------------------------------------
# _sort_files
# ---------------------------------------------------------------------------


def test_sort_files_filename_is_case_insensitive(tmp_path):
    files = [tmp_path / n for n in ("C.mp4", "a.mp4", "B.mp4")]
    result = _sort_files(files, "filename")
    assert [f.name for f in result] == ["a.mp4", "B.mp4", "C.mp4"]


def test_sort_files_date_oldest_first(tmp_path):
    files = []
    for i in range(3):
        f = tmp_path / f"clip_{i}.mp4"
        f.touch()
        files.append(f)
        time.sleep(0.02)
    result = _sort_files(files, "date")
    assert result == files


def test_sort_files_random_contains_same_files(tmp_path):
    files = [tmp_path / f"clip_{i}.mp4" for i in range(5)]
    result = _sort_files(files, "random")
    assert set(result) == set(files)
    assert len(result) == len(files)


def test_sort_files_unknown_order_falls_back_to_filename(tmp_path):
    files = [tmp_path / n for n in ("z.mp4", "a.mp4")]
    result = _sort_files(files, "unknown_order")
    assert result[0].name == "a.mp4"


# ---------------------------------------------------------------------------
# _detect_trailing_black
# ---------------------------------------------------------------------------


def test_detect_trailing_black_returns_none_when_no_black(tmp_path):
    f = tmp_path / "clean.mp4"
    f.touch()
    with (
        patch("scripts.av.join.probe_streams", return_value=[_VIDEO]),
        patch("scripts.av.join.run_ffmpeg_stderr", return_value=""),
    ):
        assert _detect_trailing_black(f) is None


def test_detect_trailing_black_returns_none_for_mid_black(tmp_path):
    f = tmp_path / "mid.mp4"
    f.touch()
    stderr = "[blackdetect] black_start:5.0 black_end:5.5 black_duration:0.5\n"
    with (
        patch("scripts.av.join.probe_streams", return_value=[_VIDEO]),
        patch("scripts.av.join.run_ffmpeg_stderr", return_value=stderr),
    ):
        # black ends at 5.5s, far from duration 30s → not trailing
        assert _detect_trailing_black(f) is None


def test_detect_trailing_black_returns_start_for_trailing_black(tmp_path):
    f = tmp_path / "black_end.mp4"
    f.touch()
    stderr = "[blackdetect] black_start:29.5 black_end:30.1 black_duration:0.6\n"
    with (
        patch("scripts.av.join.probe_streams", return_value=[_VIDEO]),
        patch("scripts.av.join.run_ffmpeg_stderr", return_value=stderr),
    ):
        result = _detect_trailing_black(f)
    assert result == pytest.approx(29.5)


def test_detect_trailing_black_returns_none_for_audio_only(tmp_path):
    f = tmp_path / "audio.mp3"
    f.touch()
    with patch("scripts.av.join.probe_streams", return_value=[_AUDIO]):
        assert _detect_trailing_black(f) is None


# ---------------------------------------------------------------------------
# _find_last_keyframe_before
# ---------------------------------------------------------------------------


def test_find_last_keyframe_before_returns_largest_below_t(tmp_path):
    f = tmp_path / "v.mp4"
    f.touch()
    frames = {
        "frames": [
            {"best_effort_timestamp_time": "10.0"},
            {"best_effort_timestamp_time": "12.0"},
            {"best_effort_timestamp_time": "29.0"},
            {"best_effort_timestamp_time": "29.5"},  # >= t=29.5 → excluded
        ]
    }
    with patch("scripts.av.join.run_ffprobe", return_value=frames):
        result = _find_last_keyframe_before(f, 29.5)
    assert result == pytest.approx(29.0)


def test_find_last_keyframe_before_returns_none_when_no_frames(tmp_path):
    f = tmp_path / "v.mp4"
    f.touch()
    with patch("scripts.av.join.run_ffprobe", return_value={"frames": []}):
        assert _find_last_keyframe_before(f, 10.0) is None


# ---------------------------------------------------------------------------
# _preprocess_file
# ---------------------------------------------------------------------------


def test_preprocess_returns_original_for_video_only_no_black(tmp_path):
    """Video-only files with no trailing black need no processing."""
    f = tmp_path / "silent.mp4"
    f.touch()
    video_only = [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "duration": "10.0"}]
    with (
        patch("scripts.av.join.probe_streams", return_value=video_only),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
    ):
        result = _preprocess_file(f, tmp_path / "work", 0)
    assert result == f


def test_preprocess_creates_temp_file_when_audio_present(tmp_path):
    f = tmp_path / "clip.mp4"
    f.touch()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    with (
        patch("scripts.av.join.probe_streams", return_value=_STREAMS),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        result = _preprocess_file(f, work_dir, 0)
    assert result != f
    assert result.suffix == ".mp4"
    mock_ff.assert_called_once()
    call_args = mock_ff.call_args[0][0]
    assert "loudnorm" in " ".join(call_args)
    assert "-c:a" in call_args


def test_preprocess_trims_when_trailing_black_detected(tmp_path):
    f = tmp_path / "clip.mp4"
    f.touch()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    with (
        patch("scripts.av.join.probe_streams", return_value=_STREAMS),
        patch("scripts.av.join._detect_trailing_black", return_value=29.5),
        patch("scripts.av.join._find_last_keyframe_before", return_value=28.0),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        _preprocess_file(f, work_dir, 0)
    call_args = mock_ff.call_args[0][0]
    assert "-to" in call_args
    to_idx = call_args.index("-to")
    assert float(call_args[to_idx + 1]) == pytest.approx(28.0)


# ---------------------------------------------------------------------------
# join() — integration-level (mocked ffmpeg/ffprobe)
# ---------------------------------------------------------------------------


def test_join_raises_when_inputs_empty(tmp_path):
    with pytest.raises(FileNotFoundError):
        join(tmp_path, tmp_path / "out.mp4")


def test_join_raises_when_single_file(tmp_path):
    _make_files(tmp_path, 1)
    with pytest.raises(ValueError, match="Only one file"):
        join(tmp_path, tmp_path / "out.mp4")


def test_join_raises_on_video_codec_mismatch(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out.mp4"
    streams_a = [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}]
    streams_b = [{"codec_type": "video", "codec_name": "vp9", "width": 1920, "height": 1080}]
    with (
        patch("scripts.av.join.probe_streams", side_effect=[streams_a, streams_b]),
        pytest.raises(RuntimeError, match="incompatible"),
    ):
        join(tmp_path, out)


def test_join_raises_on_resolution_mismatch(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out.mp4"
    streams_a = [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}]
    streams_b = [{"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720}]
    with (
        patch("scripts.av.join.probe_streams", side_effect=[streams_a, streams_b]),
        pytest.raises(RuntimeError, match="incompatible"),
    ):
        join(tmp_path, out)


def test_join_tolerates_audio_codec_mismatch(tmp_path):
    """Audio codec mismatches are resolved by normalisation, not rejected."""
    _make_files(tmp_path, 2)
    out = tmp_path / "out" / "joined.mp4"
    streams_a = [_VIDEO, {"codec_type": "audio", "codec_name": "aac"}]
    streams_b = [_VIDEO, {"codec_type": "audio", "codec_name": "mp3"}]
    # probe_streams: 2 calls for _assert_compatible + 2 for _preprocess_file
    side_effects = [streams_a, streams_b, streams_a, streams_b]
    with (
        patch("scripts.av.join.probe_streams", side_effect=side_effects),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg"),
    ):
        join(tmp_path, out)  # must not raise


def test_join_moves_inputs_to_processed(tmp_path):
    files = _make_files(tmp_path, 2)
    out = tmp_path / "out" / "joined.mp4"
    side_effects = [_STREAMS, _STREAMS, _STREAMS, _STREAMS]
    with (
        patch("scripts.av.join.probe_streams", side_effect=side_effects),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg"),
    ):
        join(tmp_path, out)
    processed = tmp_path / "processed"
    assert processed.is_dir()
    for f in files:
        assert (processed / f.name).exists()
        assert not f.exists()


def test_join_returns_output_path(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out" / "joined.mp4"
    side_effects = [_STREAMS, _STREAMS, _STREAMS, _STREAMS]
    with (
        patch("scripts.av.join.probe_streams", side_effect=side_effects),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg"),
    ):
        result = join(tmp_path, out)
    assert result == out


def test_join_passes_concat_demuxer_args_to_ffmpeg(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out" / "joined.mp4"
    side_effects = [_STREAMS, _STREAMS, _STREAMS, _STREAMS]
    with (
        patch("scripts.av.join.probe_streams", side_effect=side_effects),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        join(tmp_path, out)
    # Last run_ffmpeg call is the final concat
    concat_args = mock_ff.call_args_list[-1][0][0]
    assert "-f" in concat_args
    assert "concat" in concat_args
    assert "-c" in concat_args
    assert "copy" in concat_args


def test_join_respects_order_random(tmp_path):
    """order=random should still produce a joined output without error."""
    _make_files(tmp_path, 3)
    out = tmp_path / "out" / "joined.mp4"
    side_effects = [_STREAMS] * 6  # 3 for _assert_compatible + 3 for _preprocess_file
    with (
        patch("scripts.av.join.probe_streams", side_effect=side_effects),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg"),
    ):
        result = join(tmp_path, out, order="random")
    assert result == out
