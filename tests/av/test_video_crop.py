"""Tests for scripts.av.video_crop."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.av.video_crop import crop


FAKE_STREAMS = [{"codec_type": "video", "width": 1920, "height": 1080}]


def test_crop_builds_correct_ffmpeg_command(tmp_path):
    out = tmp_path / "out.mp4"
    with (
        patch("scripts.av.video_crop.probe_streams", return_value=FAKE_STREAMS),
        patch("scripts.av.video_crop.run_ffmpeg") as mock_ff,
    ):
        crop(Path("in.mp4"), out, top=100, right=200, bottom=100, left=200)
    mock_ff.assert_called_once_with(
        ["-i", "in.mp4", "-vf", "crop=1520:880:200:100", str(out)]
    )


def test_crop_asymmetric_values(tmp_path):
    out = tmp_path / "out.mp4"
    with (
        patch("scripts.av.video_crop.probe_streams", return_value=FAKE_STREAMS),
        patch("scripts.av.video_crop.run_ffmpeg") as mock_ff,
    ):
        crop(Path("in.mp4"), out, top=0, right=0, bottom=80, left=0)
    args = mock_ff.call_args[0][0]
    assert "crop=1920:1000:0:0" in args


def test_crop_raises_when_all_zeros():
    with pytest.raises(ValueError, match="nothing to crop"):
        crop(Path("in.mp4"), Path("out.mp4"), top=0, right=0, bottom=0, left=0)


def test_crop_raises_on_negative_value():
    with pytest.raises(ValueError, match="non-negative"):
        crop(Path("in.mp4"), Path("out.mp4"), top=-10, right=0, bottom=0, left=0)


def test_crop_raises_when_horizontal_exceeds_width():
    with (
        patch("scripts.av.video_crop.probe_streams", return_value=FAKE_STREAMS),
    ):
        with pytest.raises(ValueError, match="exceeds source width"):
            crop(Path("in.mp4"), Path("out.mp4"), top=0, right=1000, bottom=0, left=1000)


def test_crop_raises_when_vertical_exceeds_height():
    with (
        patch("scripts.av.video_crop.probe_streams", return_value=FAKE_STREAMS),
    ):
        with pytest.raises(ValueError, match="exceeds source height"):
            crop(Path("in.mp4"), Path("out.mp4"), top=600, right=0, bottom=600, left=0)


def test_crop_raises_when_no_video_stream():
    audio_only = [{"codec_type": "audio", "codec_name": "aac"}]
    with patch("scripts.av.video_crop.probe_streams", return_value=audio_only):
        with pytest.raises(ValueError, match="No video stream"):
            crop(Path("in.mp3"), Path("out.mp3"), top=10, right=10, bottom=10, left=10)
