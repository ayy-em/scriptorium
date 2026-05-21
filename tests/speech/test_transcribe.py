"""Tests for scripts.speech.transcribe."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.speech.transcribe import _render, transcribe


def _stub_provider(text: str = "hi there") -> MagicMock:
    provider = MagicMock()
    provider.transcribe.return_value = text
    return provider


def _audio(tmp_path: Path, name: str = "clip.mp3") -> Path:
    p = tmp_path / name
    p.write_bytes(b"fake")
    return p


class TestRender:
    def test_txt_returns_raw_text(self):
        assert _render("hello", "txt", "x.mp3") == "hello"

    def test_md_adds_title(self):
        out = _render("hello", "md", "clip.mp3")
        assert out.startswith("# Transcript: clip.mp3")
        assert "hello" in out

    def test_rtf_wraps_in_rtf_header(self):
        out = _render("hello", "rtf", "x.mp3")
        assert out.startswith("{\\rtf1")
        assert out.endswith("}")
        assert "hello" in out

    def test_rtf_escapes_special_chars(self):
        out = _render("a{b}c\\d", "rtf", "x.mp3")
        assert "a\\{b\\}c\\\\d" in out

    def test_rtf_replaces_newlines_with_par(self):
        out = _render("line1\nline2", "rtf", "x.mp3")
        assert "\\par" in out

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="unsupported"):
            _render("hi", "docx", "x.mp3")


class TestTranscribe:
    def test_writes_txt_file(self, tmp_path: Path):
        audio = _audio(tmp_path)
        out = tmp_path / "out" / "transcript.txt"

        result = transcribe(audio, out, provider=_stub_provider("the dog ran"), fmt="txt")

        assert result == out
        assert out.read_text(encoding="utf-8") == "the dog ran"

    def test_writes_md_file(self, tmp_path: Path):
        audio = _audio(tmp_path, "meeting.m4a")
        out = tmp_path / "transcript.md"

        transcribe(audio, out, provider=_stub_provider("notes"), fmt="md")

        content = out.read_text(encoding="utf-8")
        assert "# Transcript: meeting.m4a" in content
        assert "notes" in content

    def test_writes_rtf_file(self, tmp_path: Path):
        audio = _audio(tmp_path)
        out = tmp_path / "transcript.rtf"

        transcribe(audio, out, provider=_stub_provider("hello"), fmt="rtf")

        content = out.read_text(encoding="utf-8")
        assert content.startswith("{\\rtf1")

    def test_missing_audio_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            transcribe(tmp_path / "missing.mp3", tmp_path / "out.txt", provider=_stub_provider(), fmt="txt")

    def test_unknown_format_raises(self, tmp_path: Path):
        with pytest.raises(ValueError):
            transcribe(_audio(tmp_path), tmp_path / "out.docx", provider=_stub_provider(), fmt="docx")

    def test_creates_parent_dirs(self, tmp_path: Path):
        audio = _audio(tmp_path)
        out = tmp_path / "deep" / "nested" / "transcript.txt"

        transcribe(audio, out, provider=_stub_provider("yo"), fmt="txt")

        assert out.exists()
