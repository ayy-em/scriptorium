"""Tests for scripts.speech._providers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config import UserConfig
from core.providers import UnsupportedFeatureError
from scripts.speech._providers import (
    DEFAULT_PROVIDER,
    SUPPORTED_PROVIDERS,
    MissingCredentialsError,
    OpenAIProvider,
    get_provider,
)


@pytest.fixture(autouse=True)
def _isolated_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("core.env.user_env_path", lambda: tmp_path / "user.env")
    monkeypatch.setattr("core.env._repo_root", lambda: tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("core.config.load", UserConfig)


class TestRegistry:
    def test_default_follows_settings(self):
        assert DEFAULT_PROVIDER == "auto"

    def test_choices_are_auto_plus_the_stt_capable_providers(self):
        assert SUPPORTED_PROVIDERS == ("auto", "openai")

    def test_get_provider_returns_openai_instance(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert isinstance(get_provider("openai"), OpenAIProvider)

    def test_auto_resolves_to_a_configured_stt_provider(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert isinstance(get_provider("auto"), OpenAIProvider)

    def test_auto_without_any_key_raises_with_the_remedy(self):
        with pytest.raises(MissingCredentialsError, match="Settings → Keys"):
            get_provider("auto")

    def test_get_provider_raises_on_unknown(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonesuch")

    def test_provider_without_stt_is_refused(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        with pytest.raises(UnsupportedFeatureError):
            get_provider("anthropic")


class TestOpenAIProvider:
    def test_raises_when_api_key_missing(self, tmp_path: Path):
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
