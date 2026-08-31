"""Tests for scripts.av.join."""

from pathlib import Path
import time
from unittest.mock import patch

import pytest

from scripts.av.join import (
    _detect_trailing_black,
    _find_last_keyframe_before,
    _JoinProfile,
    _parse_frame_rate,
    _preprocess_file,
    _resolve_profile,
    _sort_files,
    _temp_suffix,
    _video_filter,
    join,
)

_VIDEO = {
    "codec_type": "video",
    "codec_name": "h264",
    "width": 1920,
    "height": 1080,
    "pix_fmt": "yuv420p",
    "sample_aspect_ratio": "1:1",
    "avg_frame_rate": "30/1",
    "duration": "30.0",
}
_AUDIO = {"codec_type": "audio", "codec_name": "aac"}
_STREAMS = [_VIDEO, _AUDIO]


def _video(**overrides) -> dict:
    """Return a video stream dict with selected fields overridden."""
    return {**_VIDEO, **overrides}


def _profile(**overrides) -> _JoinProfile:
    """Return a join profile with selected fields overridden."""
    base = {
        "reencode_video": False,
        "width": 1920,
        "height": 1080,
        "frame_rate": "30/1",
        "has_video": True,
        "has_audio": True,
        "quality": "high",
    }
    return _JoinProfile(**{**base, **overrides})


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
# _parse_frame_rate
# ---------------------------------------------------------------------------


def test_parse_frame_rate_reads_a_fraction():
    assert _parse_frame_rate("30000/1001") == pytest.approx(29.97, abs=0.01)


def test_parse_frame_rate_reads_a_bare_number():
    assert _parse_frame_rate("25") == pytest.approx(25.0)


def test_parse_frame_rate_treats_unreadable_values_as_zero():
    assert _parse_frame_rate(None) == 0.0
    assert _parse_frame_rate("0/0") == 0.0
    assert _parse_frame_rate("N/A") == 0.0


# ---------------------------------------------------------------------------
# _resolve_profile
# ---------------------------------------------------------------------------


def test_resolve_profile_skips_reencode_for_identical_files(tmp_path):
    files = _make_files(tmp_path, 2)
    streams = {f: [_VIDEO, _AUDIO] for f in files}
    profile = _resolve_profile(files, streams, "high")
    assert profile.reencode_video is False
    assert profile.has_video is True
    assert profile.has_audio is True


def test_resolve_profile_targets_largest_resolution(tmp_path):
    small, large = _make_files(tmp_path, 2)
    streams = {
        small: [_video(width=1280, height=720)],
        large: [_video(width=3840, height=2160)],
    }
    profile = _resolve_profile([small, large], streams, "high")
    assert profile.reencode_video is True
    assert (profile.width, profile.height) == (3840, 2160)


def test_resolve_profile_targets_highest_frame_rate(tmp_path):
    slow, fast = _make_files(tmp_path, 2)
    streams = {
        slow: [_video(avg_frame_rate="24/1")],
        fast: [_video(avg_frame_rate="60/1")],
    }
    profile = _resolve_profile([slow, fast], streams, "high")
    assert profile.reencode_video is True
    assert profile.frame_rate == "60/1"


def test_resolve_profile_reencodes_on_pixel_format_mismatch(tmp_path):
    a, b = _make_files(tmp_path, 2)
    streams = {a: [_video(pix_fmt="yuv420p")], b: [_video(pix_fmt="yuv422p")]}
    assert _resolve_profile([a, b], streams, "high").reencode_video is True


def test_resolve_profile_reencodes_on_codec_mismatch(tmp_path):
    a, b = _make_files(tmp_path, 2)
    streams = {a: [_video(codec_name="h264")], b: [_video(codec_name="hevc")]}
    assert _resolve_profile([a, b], streams, "high").reencode_video is True


def test_resolve_profile_ignores_audio_codec_mismatch(tmp_path):
    """Audio is re-encoded to AAC every run, so its codec is not an axis."""
    a, b = _make_files(tmp_path, 2)
    streams = {
        a: [_VIDEO, {"codec_type": "audio", "codec_name": "aac"}],
        b: [_VIDEO, {"codec_type": "audio", "codec_name": "mp3"}],
    }
    assert _resolve_profile([a, b], streams, "high").reencode_video is False


def test_resolve_profile_flags_audio_when_only_some_files_have_it(tmp_path):
    silent, loud = _make_files(tmp_path, 2)
    streams = {silent: [_VIDEO], loud: [_VIDEO, _AUDIO]}
    profile = _resolve_profile([silent, loud], streams, "high")
    assert profile.has_audio is True
    assert profile.reencode_video is False


def test_resolve_profile_for_audio_only_inputs(tmp_path):
    files = _make_files(tmp_path, 2, suffix=".mp3")
    streams = {f: [_AUDIO] for f in files}
    profile = _resolve_profile(files, streams, "high")
    assert profile.has_video is False
    assert profile.reencode_video is False
    assert profile.width is None


def test_resolve_profile_rejects_mixed_audio_and_video(tmp_path):
    video = tmp_path / "clip.mp4"
    audio = tmp_path / "track.mp3"
    for f in (video, audio):
        f.touch()
    streams = {video: [_VIDEO, _AUDIO], audio: [_AUDIO]}
    with pytest.raises(RuntimeError, match="no video stream"):
        _resolve_profile([video, audio], streams, "high")


def test_resolve_profile_names_the_offending_file_in_the_error(tmp_path):
    video = tmp_path / "clip.mp4"
    audio = tmp_path / "track.mp3"
    for f in (video, audio):
        f.touch()
    streams = {video: [_VIDEO], audio: [_AUDIO]}
    with pytest.raises(RuntimeError, match="track.mp3"):
        _resolve_profile([video, audio], streams, "high")


# ---------------------------------------------------------------------------
# _video_filter / _temp_suffix
# ---------------------------------------------------------------------------


def test_video_filter_scales_and_pads_to_the_target():
    result = _video_filter(_profile(width=1920, height=1080))
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in result
    assert "pad=1920:1080" in result
    assert "setsar=1" in result


def test_temp_suffix_is_audio_container_without_video():
    assert _temp_suffix(None, _profile(has_video=False)) == ".m4a"


def test_temp_suffix_is_mp4_when_reencoding():
    assert _temp_suffix(_video(codec_name="vp9"), _profile(reencode_video=True)) == ".mp4"


def test_temp_suffix_is_mp4_for_copied_mp4_codecs():
    assert _temp_suffix(_video(codec_name="h264"), _profile()) == ".mp4"


def test_temp_suffix_falls_back_to_matroska_for_other_codecs():
    """AAC audio cannot be muxed alongside a copied VP9 stream in MP4."""
    assert _temp_suffix(_video(codec_name="vp9"), _profile()) == ".mkv"


# ---------------------------------------------------------------------------
# _detect_trailing_black
# ---------------------------------------------------------------------------


def test_detect_trailing_black_returns_none_when_no_black(tmp_path):
    f = tmp_path / "clean.mp4"
    f.touch()
    with patch("scripts.av.join.run_ffmpeg_stderr", return_value=""):
        assert _detect_trailing_black(f, [_VIDEO]) is None


def test_detect_trailing_black_returns_none_for_mid_black(tmp_path):
    f = tmp_path / "mid.mp4"
    f.touch()
    stderr = "[blackdetect] black_start:5.0 black_end:5.5 black_duration:0.5\n"
    with patch("scripts.av.join.run_ffmpeg_stderr", return_value=stderr):
        # black ends at 5.5s, far from duration 30s → not trailing
        assert _detect_trailing_black(f, [_VIDEO]) is None


def test_detect_trailing_black_returns_start_for_trailing_black(tmp_path):
    f = tmp_path / "black_end.mp4"
    f.touch()
    stderr = "[blackdetect] black_start:29.5 black_end:30.1 black_duration:0.6\n"
    with patch("scripts.av.join.run_ffmpeg_stderr", return_value=stderr):
        result = _detect_trailing_black(f, [_VIDEO])
    assert result == pytest.approx(29.5)


def test_detect_trailing_black_returns_none_for_audio_only(tmp_path):
    f = tmp_path / "audio.mp3"
    f.touch()
    assert _detect_trailing_black(f, [_AUDIO]) is None


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
    """A matching, silent, cleanly-ending file needs no processing at all."""
    f = tmp_path / "silent.mp4"
    f.touch()
    with patch("scripts.av.join._detect_trailing_black", return_value=None):
        result = _preprocess_file(f, [_VIDEO], tmp_path / "work", 0, _profile(has_audio=False))
    assert result == f


def test_preprocess_creates_temp_file_when_audio_present(tmp_path):
    f = tmp_path / "clip.mp4"
    f.touch()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    with (
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        result = _preprocess_file(f, _STREAMS, work_dir, 0, _profile())
    assert result != f
    assert result.suffix == ".mp4"
    mock_ff.assert_called_once()
    call_args = mock_ff.call_args[0][0]
    assert "loudnorm" in " ".join(call_args)
    assert "-c:a" in call_args
    assert "-c:v" in call_args
    assert "copy" in call_args


def test_preprocess_trims_to_keyframe_when_copying(tmp_path):
    f = tmp_path / "clip.mp4"
    f.touch()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    with (
        patch("scripts.av.join._detect_trailing_black", return_value=29.5),
        patch("scripts.av.join._find_last_keyframe_before", return_value=28.0),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        _preprocess_file(f, _STREAMS, work_dir, 0, _profile())
    call_args = mock_ff.call_args[0][0]
    to_idx = call_args.index("-to")
    assert float(call_args[to_idx + 1]) == pytest.approx(28.0)


def test_preprocess_trims_exactly_when_reencoding(tmp_path):
    """A re-encode is not bound to keyframes, so no black is left behind."""
    f = tmp_path / "clip.mp4"
    f.touch()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    with (
        patch("scripts.av.join._detect_trailing_black", return_value=29.5),
        patch("scripts.av.join._find_last_keyframe_before") as mock_kf,
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        _preprocess_file(f, _STREAMS, work_dir, 0, _profile(reencode_video=True))
    call_args = mock_ff.call_args[0][0]
    to_idx = call_args.index("-to")
    assert float(call_args[to_idx + 1]) == pytest.approx(29.5)
    mock_kf.assert_not_called()


def test_preprocess_reencodes_video_to_the_profile(tmp_path):
    f = tmp_path / "clip.mp4"
    f.touch()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    with (
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        _preprocess_file(f, _STREAMS, work_dir, 0, _profile(reencode_video=True))
    call_args = mock_ff.call_args[0][0]
    assert "libx264" in call_args
    assert "copy" not in call_args
    assert "yuv420p" in call_args
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in " ".join(call_args)
    r_idx = call_args.index("-r")
    assert call_args[r_idx + 1] == "30/1"


def test_preprocess_reencodes_even_a_silent_clean_file_when_profile_requires_it(tmp_path):
    f = tmp_path / "silent.mp4"
    f.touch()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    with (
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        result = _preprocess_file(f, [_VIDEO], work_dir, 0, _profile(reencode_video=True, has_audio=False))
    assert result != f
    assert "libx264" in mock_ff.call_args[0][0]
    assert "-an" in mock_ff.call_args[0][0]


def test_preprocess_adds_silent_audio_when_others_have_it(tmp_path):
    """The concat demuxer needs every file to carry the same streams."""
    f = tmp_path / "silent.mp4"
    f.touch()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    with (
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        result = _preprocess_file(f, [_VIDEO], work_dir, 0, _profile(has_audio=True))
    assert result != f
    call_args = mock_ff.call_args[0][0]
    joined = " ".join(call_args)
    assert "anullsrc" in joined
    assert "-shortest" in call_args
    assert "-c:a" in call_args
    assert "loudnorm" not in joined


def test_preprocess_uses_the_quality_preset_bitrate(tmp_path):
    f = tmp_path / "clip.mp4"
    f.touch()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    with (
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        _preprocess_file(f, _STREAMS, work_dir, 0, _profile(quality="low"))
    call_args = mock_ff.call_args[0][0]
    assert call_args[call_args.index("-b:a") + 1] == "96k"


def test_preprocess_uses_the_quality_preset_crf(tmp_path):
    f = tmp_path / "clip.mp4"
    f.touch()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    with (
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        _preprocess_file(f, _STREAMS, work_dir, 0, _profile(reencode_video=True, quality="max"))
    call_args = mock_ff.call_args[0][0]
    assert call_args[call_args.index("-crf") + 1] == "0"


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


def test_join_raises_on_unknown_quality(tmp_path):
    _make_files(tmp_path, 2)
    with pytest.raises(ValueError, match="Unknown quality"):
        join(tmp_path, tmp_path / "out.mp4", quality="pristine")


def test_join_reencodes_on_video_codec_mismatch(tmp_path):
    """A codec mismatch is now resolved by re-encoding, not rejected."""
    _make_files(tmp_path, 2)
    out = tmp_path / "out" / "joined.mp4"
    streams_a = [_video(codec_name="h264")]
    streams_b = [_video(codec_name="vp9")]
    with (
        patch("scripts.av.join.probe_streams", side_effect=[streams_a, streams_b]),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        assert join(tmp_path, out) == out
    preprocess_calls = mock_ff.call_args_list[:-1]
    assert len(preprocess_calls) == 2
    for call in preprocess_calls:
        assert "libx264" in call[0][0]


def test_join_reencodes_on_resolution_mismatch(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out" / "joined.mp4"
    streams_a = [_video(width=1920, height=1080)]
    streams_b = [_video(width=1280, height=720)]
    with (
        patch("scripts.av.join.probe_streams", side_effect=[streams_a, streams_b]),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        join(tmp_path, out)
    scaled = " ".join(mock_ff.call_args_list[0][0][0])
    assert "scale=1920:1080" in scaled


def test_join_keeps_the_stream_copy_path_for_matching_files(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out" / "joined.mp4"
    with (
        patch("scripts.av.join.probe_streams", side_effect=[_STREAMS, _STREAMS]),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        join(tmp_path, out)
    for call in mock_ff.call_args_list:
        assert "libx264" not in call[0][0]


def test_join_tolerates_audio_codec_mismatch(tmp_path):
    """Audio codec mismatches are resolved by normalisation, not rejected."""
    _make_files(tmp_path, 2)
    out = tmp_path / "out" / "joined.mp4"
    streams_a = [_VIDEO, {"codec_type": "audio", "codec_name": "aac"}]
    streams_b = [_VIDEO, {"codec_type": "audio", "codec_name": "mp3"}]
    with (
        patch("scripts.av.join.probe_streams", side_effect=[streams_a, streams_b]),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg"),
    ):
        join(tmp_path, out)  # must not raise


def test_join_rejects_audio_only_file_among_videos(tmp_path):
    (tmp_path / "clip.mp4").touch()
    (tmp_path / "track.mp3").touch()
    out = tmp_path / "out" / "joined.mp4"
    with (
        patch("scripts.av.join.probe_streams", side_effect=[_STREAMS, [_AUDIO]]),
        pytest.raises(RuntimeError, match="no video stream"),
    ):
        join(tmp_path, out)


def test_join_moves_inputs_to_processed(tmp_path):
    files = _make_files(tmp_path, 2)
    out = tmp_path / "out" / "joined.mp4"
    with (
        patch("scripts.av.join.probe_streams", side_effect=[_STREAMS, _STREAMS]),
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
    with (
        patch("scripts.av.join.probe_streams", side_effect=[_STREAMS, _STREAMS]),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg"),
    ):
        result = join(tmp_path, out)
    assert result == out


def test_join_passes_concat_demuxer_args_to_ffmpeg(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out" / "joined.mp4"
    with (
        patch("scripts.av.join.probe_streams", side_effect=[_STREAMS, _STREAMS]),
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
    with (
        patch("scripts.av.join.probe_streams", side_effect=[_STREAMS] * 3),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg"),
    ):
        result = join(tmp_path, out, order="random")
    assert result == out


def test_join_threads_quality_through_to_preprocessing(tmp_path):
    _make_files(tmp_path, 2)
    out = tmp_path / "out" / "joined.mp4"
    with (
        patch("scripts.av.join.probe_streams", side_effect=[_STREAMS, _STREAMS]),
        patch("scripts.av.join._detect_trailing_black", return_value=None),
        patch("scripts.av.join.run_ffmpeg") as mock_ff,
    ):
        join(tmp_path, out, quality="low")
    first_call = mock_ff.call_args_list[0][0][0]
    assert first_call[first_call.index("-b:a") + 1] == "96k"
