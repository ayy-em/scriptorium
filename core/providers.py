"""One registry for every LLM provider a script may call.

Before this module each script that talked to an API read its own environment
variable, raised its own "key missing" error and named its own provider on the
command line. ``speech.transcribe`` and ``telegram.embed_messages`` both did
it for OpenAI, differently. The next scripts to arrive — OCR, text to speech —
would have made it four copies, each needing its own field in Settings → Keys.

A ``Provider`` here says what a provider is called, which environment variable
holds its key, which features it can serve and what the key unlocks. Everything
else derives from that: ``core.capabilities`` turns each entry into a
configure-remedy capability, which is what puts a field in Settings → Keys, and
scripts ask ``resolve()`` for a provider rather than reading the environment.

Credentials themselves stay where ``core.env`` keeps them. This module never
stores a key; it only knows where to look.
"""

from dataclasses import dataclass
import os

from core.env import load_env

FEATURE_CHAT = "chat"
FEATURE_VISION = "vision"
FEATURE_STT = "stt"
FEATURE_TTS = "tts"
FEATURE_EMBEDDINGS = "embeddings"

FEATURES = (FEATURE_CHAT, FEATURE_VISION, FEATURE_STT, FEATURE_TTS, FEATURE_EMBEDDINGS)

#: The value a script's ``--provider`` flag takes to mean "whatever Settings says".
AUTO = "auto"


class MissingCredentialsError(RuntimeError):
    """Raised when a provider is wanted but its API key is not configured."""


class UnsupportedFeatureError(ValueError):
    """Raised when a provider is asked for a feature it does not serve."""


@dataclass(frozen=True)
class Provider:
    """One API provider and what it can do.

    Attributes:
        id: Stable identifier used in config, on the command line and as the
            capability name's stem, e.g. ``"openai"``.
        label: Display name.
        env_var: The environment variable that holds the API key.
        features: The features this provider serves, from ``FEATURES``.
        key_needed_for: Plain-language "what the key unlocks", shown next to
            the field in Settings → Keys.
        key_required: Whether a missing key belongs in the sidebar banner. A
            provider with no shipped consumer yet must not nag everyone.
    """

    id: str
    label: str
    env_var: str
    features: frozenset[str]
    key_needed_for: str
    key_required: bool = True

    @property
    def capability_name(self) -> str:
        """Return the name of the capability that represents this key.

        Returns:
            ``"<id>-key"``, e.g. ``"openai-key"``.
        """
        return f"{self.id}-key"

    def supports(self, feature: str) -> bool:
        """Report whether this provider serves a feature.

        Args:
            feature: One of ``FEATURES``.

        Returns:
            True when the provider can be used for it.
        """
        return feature in self.features


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        id="openai",
        label="OpenAI",
        env_var="OPENAI_API_KEY",
        features=frozenset({FEATURE_CHAT, FEATURE_VISION, FEATURE_STT, FEATURE_TTS, FEATURE_EMBEDDINGS}),
        key_needed_for="Speech transcription and Telegram message embeddings",
    ),
    Provider(
        id="anthropic",
        label="Anthropic",
        env_var="ANTHROPIC_API_KEY",
        features=frozenset({FEATURE_CHAT, FEATURE_VISION}),
        key_needed_for="Nothing shipped yet — photo.ocr will be the first script to use it",
        key_required=False,
    ),
)

DEFAULT_PROVIDER_ID = PROVIDERS[0].id

_BY_ID = {provider.id: provider for provider in PROVIDERS}


def get(provider_id: str) -> Provider:
    """Look a provider up by id.

    Args:
        provider_id: A provider id such as ``"openai"``.

    Returns:
        The provider.

    Raises:
        ValueError: When no provider has that id.
    """
    provider = _BY_ID.get(provider_id)
    if provider is None:
        known = ", ".join(_BY_ID)
        raise ValueError(f"Unknown provider {provider_id!r}. Known providers: {known}")
    return provider


def supporting(feature: str) -> tuple[Provider, ...]:
    """Return the providers that serve a feature, in registry order.

    Args:
        feature: One of ``FEATURES``.

    Returns:
        The capable providers; empty when none serves the feature.
    """
    return tuple(provider for provider in PROVIDERS if provider.supports(feature))


def is_configured(provider_id: str) -> bool:
    """Report whether a provider's key is set.

    Loads the ``.env`` files first so a CLI caller and the webapp agree.

    Args:
        provider_id: A provider id.

    Returns:
        True when the key is set to something non-blank.
    """
    load_env()
    return bool(os.environ.get(get(provider_id).env_var, "").strip())


def api_key(provider_id: str) -> str:
    """Return a provider's API key.

    Args:
        provider_id: A provider id.

    Returns:
        The key, stripped.

    Raises:
        MissingCredentialsError: When the key is not set, with the remedy in
            the message because that message is what the user sees.
    """
    provider = get(provider_id)
    load_env()
    key = os.environ.get(provider.env_var, "").strip()
    if not key:
        raise MissingCredentialsError(
            f"{provider.label} needs an API key. Paste it under Settings → Keys, "
            f"or set {provider.env_var} in your .env file."
        )
    return key


def preferred_provider_id() -> str:
    """Return the provider the user chose in Settings.

    Imported lazily because ``core.config`` validates its stored value
    against this registry, and the two modules must not import each other at
    load time.

    Returns:
        A provider id that exists in the registry.
    """
    from core.config import load  # noqa: PLC0415

    return load().preferred_provider


def resolve(feature: str, requested: str = AUTO) -> Provider:
    """Pick the provider a script should use for a feature.

    ``AUTO`` means the preferred provider from Settings when it serves the
    feature and has a key, otherwise the first capable provider that has one.
    A named provider is checked for the feature and the key and returned as is.

    Args:
        feature: One of ``FEATURES``.
        requested: A provider id, or ``AUTO``.

    Returns:
        A provider that serves the feature and has a key.

    Raises:
        ValueError: When ``requested`` names no known provider.
        UnsupportedFeatureError: When the named provider does not serve the
            feature, or no provider does.
        MissingCredentialsError: When no suitable provider has a key.
    """
    capable = supporting(feature)
    if not capable:
        raise UnsupportedFeatureError(f"No provider serves {feature!r}")

    if requested != AUTO:
        provider = get(requested)
        if not provider.supports(feature):
            names = ", ".join(candidate.id for candidate in capable)
            raise UnsupportedFeatureError(f"{provider.label} does not support {feature}. Use one of: {names}")
        api_key(provider.id)
        return provider

    preferred = _BY_ID.get(preferred_provider_id())
    if preferred is not None and preferred.supports(feature) and is_configured(preferred.id):
        return preferred
    for provider in capable:
        if is_configured(provider.id):
            return provider

    labels = ", ".join(candidate.label for candidate in capable)
    raise MissingCredentialsError(
        f"No provider with an API key can do {feature}. Add a key for one of {labels} under Settings → Keys."
    )
