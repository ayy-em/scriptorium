"""Tests for scripts.av.volume."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.av.volume import adjust_volume


def test_adjust_volume_raises_when_no_filters_given():
    with pytest.raises(ValueError, match="At least one"):
        adjust_volume(Path("in.mp4"), Path("out.mp4"))


def test_adjust_volume_amplify_builds_volume_filter(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.volume.run_ffmpeg") as mock_ff:
        adjust_volume(Path("in.mp4"), out, amplify_db=6.0)
    args = mock_ff.call_args[0][0]
    af_chain = args[args.index("-af") + 1]
    assert "volume=6.0dB" in af_chain


def test_adjust_volume_normalize_adds_loudnorm(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.volume.run_ffmpeg") as mock_ff:
        adjust_volume(Path("in.mp4"), out, normalize=True)
    args = mock_ff.call_args[0][0]
    af_chain = args[args.index("-af") + 1]
    assert "loudnorm" in af_chain


def test_adjust_volume_normalize_prints_rerun_reminder(tmp_path, capsys):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.volume.run_ffmpeg"):
        adjust_volume(Path("in.mp4"), out, normalize=True)
    captured = capsys.readouterr()
    assert "loudnorm" in captured.out
    assert "again" in captured.out


def test_adjust_volume_no_normalize_prints_no_reminder(tmp_path, capsys):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.volume.run_ffmpeg"):
        adjust_volume(Path("in.mp4"), out, amplify_db=3.0)
    captured = capsys.readouterr()
    assert "loudnorm" not in captured.out


def test_adjust_volume_filter_order_is_fixed(tmp_path):
    out = tmp_path / "out.mp4"
    with (
        patch("scripts.av.volume.run_ffmpeg") as mock_ff,
        patch("scripts.av.volume._get_duration", return_value=60.0),
    ):
        adjust_volume(Path("in.mp4"), out, normalize=True, amplify_db=3.0, fade_in=2.0, fade_out=3.0)
    args = mock_ff.call_args[0][0]
    chain = args[args.index("-af") + 1]
    assert chain.index("volume=") < chain.index("loudnorm")
    assert chain.index("loudnorm") < chain.index("afade=t=in")
    assert chain.index("afade=t=in") < chain.index("afade=t=out")


def test_adjust_volume_fade_out_computes_start_from_duration(tmp_path):
    out = tmp_path / "out.mp4"
    with (
        patch("scripts.av.volume.run_ffmpeg") as mock_ff,
        patch("scripts.av.volume._get_duration", return_value=120.0),
    ):
        adjust_volume(Path("in.mp4"), out, fade_out=5.0)
    args = mock_ff.call_args[0][0]
    af_chain = args[args.index("-af") + 1]
    assert "afade=t=out:st=115.000:d=5.0" in af_chain


def test_adjust_volume_fade_in_does_not_call_get_duration(tmp_path):
    out = tmp_path / "out.mp4"
    with (
        patch("scripts.av.volume.run_ffmpeg"),
        patch("scripts.av.volume._get_duration") as mock_dur,
    ):
        adjust_volume(Path("in.mp4"), out, fade_in=2.0)
    mock_dur.assert_not_called()
