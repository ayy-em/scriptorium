"""Tests for scripts.speech._providers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.speech._providers import (
    DEFAULT_PROVIDER,
    SUPPORTED_PROVIDERS,
    MissingCredentialsError,
    OpenAIProvider,
    get_provider,
)


class TestRegistry:
    def test_default_is_openai(self):
        assert DEFAULT_PROVIDER == "openai"

    def test_openai_is_supported(self):
        assert "openai" in SUPPORTED_PROVIDERS

    def test_get_provider_returns_openai_instance(self):
        provider = get_provider("openai")
        assert isinstance(provider, OpenAIProvider)

    def test_get_provider_raises_on_unknown(self):
        with pytest.raises(ValueError, match="Unknown transcription provider"):
            get_provider("nonesuch")


class TestOpenAIProvider:
    def test_raises_when_api_key_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"")

        with pytest.raises(MissingCredentialsError, match="OPENAI_API_KEY"):
            OpenAIProvider().transcribe(audio)

    def test_raises_when_api_key_blank(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("OPENAI_API_KEY", "   ")
        audio = tmp_path / "a.mp3"
        audio.write_bytes(b"")

        with pytest.raises(MissingCredentialsError):
            OpenAIProvider().transcribe(audio)

    def test_calls_openai_with_whisper_model(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        audio = tmp_path / "clip.m4a"
        audio.write_bytes(b"fake-audio-bytes")

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = MagicMock(text="hello world")

        with patch("openai.OpenAI", return_value=mock_client) as mock_class:
            result = OpenAIProvider().transcribe(audio)

        mock_class.assert_called_once_with(api_key="sk-test")
        kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert kwargs["model"] == "whisper-1"
        assert hasattr(kwargs["file"], "read")
        assert result == "hello world"
