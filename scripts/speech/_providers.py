"""Transcription provider abstraction (kept light so the only Python dep at import time is stdlib)."""

import os
from pathlib import Path
from typing import Protocol

OPENAI = "openai"
DEFAULT_PROVIDER = OPENAI
SUPPORTED_PROVIDERS = (OPENAI,)


class TranscriptionProvider(Protocol):
    """Speech-to-text provider contract."""

    name: str

    def transcribe(self, audio_path: Path) -> str:
        """Return the transcribed text for a given audio file."""
        ...


class MissingCredentialsError(RuntimeError):
    """Raised when a provider is selected but its API key is not configured."""


class OpenAIProvider:
    """OpenAI Whisper-backed transcription provider."""

    name = OPENAI
    _MODEL = "whisper-1"
    _ENV_VAR = "OPENAI_API_KEY"

    def transcribe(self, audio_path: Path) -> str:
        api_key = os.environ.get(self._ENV_VAR, "").strip()
        if not api_key:
            raise MissingCredentialsError(
                f"OpenAI provider requires the {self._ENV_VAR} environment variable to be set. "
                f"Export your API key (e.g. `export {self._ENV_VAR}=sk-...`) before running."
            )
        from openai import OpenAI  # noqa: PLC0415

        client = OpenAI(api_key=api_key)
        with audio_path.open("rb") as fh:
            response = client.audio.transcriptions.create(model=self._MODEL, file=fh)
        return response.text


def get_provider(name: str) -> TranscriptionProvider:
    """Return a provider instance by name, raising ValueError on unknown names."""
    if name == OPENAI:
        return OpenAIProvider()
    raise ValueError(f"Unknown transcription provider {name!r}. Supported: {', '.join(SUPPORTED_PROVIDERS)}")
