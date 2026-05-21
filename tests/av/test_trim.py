"""Tests for scripts.av.trim."""

from pathlib import Path
from unittest.mock import patch

from scripts.av.trim import _resolve_output, trim


def test_trim_with_start_and_end(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.trim.run_ffmpeg") as mock_ff:
        trim(Path("in.mp4"), out, start="00:01:00", end="00:02:00")
    mock_ff.assert_called_once_with(["-i", "in.mp4", "-ss", "00:01:00", "-to", "00:02:00", "-c", "copy", str(out)])


def test_trim_without_end_omits_to_flag(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.trim.run_ffmpeg") as mock_ff:
        trim(Path("in.mp4"), out, start="00:03")
    args = mock_ff.call_args[0][0]
    assert "-ss" in args
    assert args[args.index("-ss") + 1] == "00:03"
    assert "-to" not in args


def test_trim_accepts_mm_ss_format(tmp_path):
    out = tmp_path / "out.mp4"
    with patch("scripts.av.trim.run_ffmpeg") as mock_ff:
        trim(Path("in.mp4"), out, start="1:03", end="5:04")
    args = mock_ff.call_args[0][0]
    assert args[args.index("-ss") + 1] == "1:03"
    assert args[args.index("-to") + 1] == "5:04"


def test_resolve_output_defaults_to_trim_subdir(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.av.trim.av_outputs_dir", lambda: tmp_path)
    result = _resolve_output(None, Path("clip.mp4"))
    assert result == tmp_path / "trim" / "clip_trimmed.mp4"


def test_resolve_output_bare_name_resolves_to_trim_subdir(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.av.trim.av_outputs_dir", lambda: tmp_path)
    result = _resolve_output(Path("custom.mp4"), Path("clip.mp4"))
    assert result == tmp_path / "trim" / "custom.mp4"


def test_resolve_output_pathy_arg_is_passed_through(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.av.trim.av_outputs_dir", lambda: tmp_path)
    target = tmp_path / "elsewhere" / "out.mp4"
    result = _resolve_output(target, Path("clip.mp4"))
    assert result == target
