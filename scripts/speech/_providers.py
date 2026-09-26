"""Speech-to-text providers, resolved through the shared provider registry.

The contract stays here because it is about audio in, text out. Which
provider to use and where its key comes from is ``core.providers``' job, so
this module holds no credential code of its own.
"""

from pathlib import Path
from typing import Protocol

from core import providers
from core.providers import AUTO, FEATURE_STT, MissingCredentialsError

DEFAULT_PROVIDER = AUTO
SUPPORTED_PROVIDERS = (AUTO, *(provider.id for provider in providers.supporting(FEATURE_STT)))

__all__ = [
    "DEFAULT_PROVIDER",
    "SUPPORTED_PROVIDERS",
    "MissingCredentialsError",
    "OpenAIProvider",
    "TranscriptionProvider",
    "get_provider",
]


class TranscriptionProvider(Protocol):
    """Speech-to-text provider contract."""

    name: str

    def transcribe(self, audio_path: Path) -> str:
        """Return the transcribed text for a given audio file."""
        ...


class OpenAIProvider:
    """OpenAI Whisper-backed transcription provider."""

    name = "openai"
    _MODEL = "whisper-1"

    def transcribe(self, audio_path: Path) -> str:
        """Send one audio file to Whisper and return its transcript.

        Args:
            audio_path: The audio file.

        Returns:
            The transcript text.

        Raises:
            MissingCredentialsError: When no OpenAI key is configured.
        """
        key = providers.api_key(self.name)
        from openai import OpenAI  # noqa: PLC0415

        client = OpenAI(api_key=key)
        with audio_path.open("rb") as fh:
            response = client.audio.transcriptions.create(model=self._MODEL, file=fh)
        return response.text


_IMPLEMENTATIONS: dict[str, type[TranscriptionProvider]] = {
    OpenAIProvider.name: OpenAIProvider,
}


def get_provider(name: str = AUTO) -> TranscriptionProvider:
    """Return a transcription provider by name, or the preferred one for ``auto``.

    Args:
        name: A provider id, or ``auto`` to follow Settings.

    Returns:
        A provider instance whose key is configured.

    Raises:
        ValueError: On an unknown provider id.
        UnsupportedFeatureError: When the named provider cannot transcribe.
        MissingCredentialsError: When no suitable provider has a key.
    """
    provider = providers.resolve(FEATURE_STT, name)
    return _IMPLEMENTATIONS[provider.id]()
