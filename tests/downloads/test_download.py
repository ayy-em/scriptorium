"""Tests for scripts.downloads.download."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.downloads.download import download


def _ydl_mock(base_dir: Path, title: str = "My Video", ext: str = "mp4") -> MagicMock:
    fake_info = {"title": title, "ext": ext}
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value = mock_ydl
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.prepare_filename.return_value = str(base_dir / f"{title}.{ext}")
    return mock_ydl


def test_download_video_format_targets_mp4(tmp_path):
    with patch("yt_dlp.YoutubeDL", return_value=_ydl_mock(tmp_path)) as mock_cls:
        download("https://example.com/video", tmp_path)
    opts = mock_cls.call_args[0][0]
    assert "mp4" in opts["format"]
    assert opts["merge_output_format"] == "mp4"


def test_download_audio_format_targets_bestaudio(tmp_path):
    with patch("yt_dlp.YoutubeDL", return_value=_ydl_mock(tmp_path, ext="webm")) as mock_cls:
        download("https://example.com/video", tmp_path, audio_only=True)
    opts = mock_cls.call_args[0][0]
    assert "bestaudio" in opts["format"]


def test_download_audio_has_ffmpeg_extract_postprocessor(tmp_path):
    with patch("yt_dlp.YoutubeDL", return_value=_ydl_mock(tmp_path, ext="webm")) as mock_cls:
        download("https://example.com/video", tmp_path, audio_only=True)
    opts = mock_cls.call_args[0][0]
    pp_keys = [pp["key"] for pp in opts.get("postprocessors", [])]
    assert "FFmpegExtractAudio" in pp_keys


def test_download_video_returns_mp4_path(tmp_path):
    with patch("yt_dlp.YoutubeDL", return_value=_ydl_mock(tmp_path, title="clip")):
        result = download("https://example.com/video", tmp_path)
    assert result.suffix == ".mp4"


def test_download_audio_returns_mp3_path(tmp_path):
    with patch("yt_dlp.YoutubeDL", return_value=_ydl_mock(tmp_path, title="clip", ext="webm")):
        result = download("https://example.com/video", tmp_path, audio_only=True)
    assert result.suffix == ".mp3"


def test_download_custom_filename_appears_in_outtmpl(tmp_path):
    with patch("yt_dlp.YoutubeDL", return_value=_ydl_mock(tmp_path, title="my_file")) as mock_cls:
        download("https://example.com/video", tmp_path, filename="my_file")
    opts = mock_cls.call_args[0][0]
    assert "my_file" in opts["outtmpl"]
    assert "%(title)s" not in opts["outtmpl"]


def test_download_default_filename_uses_title_template(tmp_path):
    with patch("yt_dlp.YoutubeDL", return_value=_ydl_mock(tmp_path)) as mock_cls:
        download("https://example.com/video", tmp_path)
    opts = mock_cls.call_args[0][0]
    assert "%(title)s" in opts["outtmpl"]


def test_download_creates_output_directory(tmp_path):
    out_dir = tmp_path / "nested" / "outputs"
    with patch("yt_dlp.YoutubeDL", return_value=_ydl_mock(tmp_path)):
        download("https://example.com/video", out_dir)
    assert out_dir.is_dir()


def test_download_outtmpl_is_inside_outputs_dir(tmp_path):
    with patch("yt_dlp.YoutubeDL", return_value=_ydl_mock(tmp_path)) as mock_cls:
        download("https://example.com/video", tmp_path)
    opts = mock_cls.call_args[0][0]
    assert opts["outtmpl"].startswith(str(tmp_path))
