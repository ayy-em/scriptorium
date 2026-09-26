"""Tests for the shared LLM provider registry.

The registry is the one place a provider is declared, so what must hold is
that everything else follows from an entry: its key capability, its place in
Settings, and how ``resolve()`` picks it for a script.
"""

from pathlib import Path

import pytest

from core import capabilities, providers
from core.config import UserConfig
from core.providers import (
    AUTO,
    FEATURE_EMBEDDINGS,
    FEATURE_STT,
    FEATURE_TTS,
    FEATURE_VISION,
    PROVIDERS,
    MissingCredentialsError,
    UnsupportedFeatureError,
    api_key,
    get,
    is_configured,
    resolve,
    supporting,
)


@pytest.fixture(autouse=True)
def _isolated_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """No key from the developer's real .env files or shell leaks into a test."""
    monkeypatch.setattr("core.env.user_env_path", lambda: tmp_path / "user.env")
    monkeypatch.setattr("core.env._repo_root", lambda: tmp_path)
    for provider in PROVIDERS:
        monkeypatch.delenv(provider.env_var, raising=False)
    capabilities.invalidate()
    yield
    capabilities.invalidate()


def _prefer(monkeypatch: pytest.MonkeyPatch, provider_id: str) -> None:
    monkeypatch.setattr("core.config.load", lambda: UserConfig(preferred_provider=provider_id))


class TestRegistry:
    def test_ids_are_unique(self):
        ids = [provider.id for provider in PROVIDERS]
        assert len(ids) == len(set(ids))

    def test_openai_is_the_default_and_serves_every_feature(self):
        assert providers.DEFAULT_PROVIDER_ID == "openai"
        assert get("openai").features == frozenset(providers.FEATURES)

    def test_anthropic_has_no_shipped_consumer_so_its_key_is_optional(self):
        assert get("anthropic").key_required is False

    def test_unknown_id_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get("nonesuch")

    def test_supporting_filters_by_feature(self):
        assert [provider.id for provider in supporting(FEATURE_STT)] == ["openai"]
        assert {provider.id for provider in supporting(FEATURE_VISION)} == {"openai", "anthropic"}

    def test_every_provider_becomes_a_key_capability(self):
        """Registering a provider is the whole job; Settings → Keys follows."""
        for provider in PROVIDERS:
            capability = capabilities.probe(provider.capability_name)
            assert capability is not None, provider.id
            assert capability.remedy == capabilities.REMEDY_CONFIGURE
            assert capability.env_var == provider.env_var
            assert capability.required is provider.key_required
            assert capability.secret is True


class TestCredentials:
    def test_is_configured_reads_the_environment(self, monkeypatch: pytest.MonkeyPatch):
        assert is_configured("openai") is False
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert is_configured("openai") is True

    def test_blank_key_counts_as_missing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENAI_API_KEY", "   ")
        assert is_configured("openai") is False

    def test_api_key_reads_the_user_env_file(self, tmp_path: Path):
        (tmp_path / "user.env").write_text("ANTHROPIC_API_KEY=sk-ant-file\n", encoding="utf-8")
        assert api_key("anthropic") == "sk-ant-file"

    def test_missing_key_names_the_remedy(self):
        with pytest.raises(MissingCredentialsError, match="Settings → Keys") as excinfo:
            api_key("openai")
        assert "OPENAI_API_KEY" in str(excinfo.value)


class TestResolve:
    def test_auto_uses_the_preferred_provider_when_it_has_a_key(self, monkeypatch: pytest.MonkeyPatch):
        _prefer(monkeypatch, "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
        assert resolve(FEATURE_VISION).id == "anthropic"

    def test_auto_skips_a_preferred_provider_without_a_key(self, monkeypatch: pytest.MonkeyPatch):
        _prefer(monkeypatch, "anthropic")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
        assert resolve(FEATURE_VISION).id == "openai"

    def test_auto_skips_a_preferred_provider_that_lacks_the_feature(self, monkeypatch: pytest.MonkeyPatch):
        _prefer(monkeypatch, "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
        assert resolve(FEATURE_STT).id == "openai"

    def test_auto_with_no_keys_says_which_providers_would_do(self, monkeypatch: pytest.MonkeyPatch):
        _prefer(monkeypatch, "openai")
        with pytest.raises(MissingCredentialsError, match="OpenAI"):
            resolve(FEATURE_EMBEDDINGS)

    def test_named_provider_is_returned_when_configured(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
        assert resolve(FEATURE_TTS, "openai").id == "openai"

    def test_named_provider_without_a_key_raises(self):
        with pytest.raises(MissingCredentialsError, match="OpenAI"):
            resolve(FEATURE_TTS, "openai")

    def test_named_provider_without_the_feature_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        with pytest.raises(UnsupportedFeatureError, match="does not support stt"):
            resolve(FEATURE_STT, "anthropic")

    def test_unknown_named_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            resolve(FEATURE_STT, "nonesuch")

    def test_feature_nobody_serves_raises(self):
        with pytest.raises(UnsupportedFeatureError, match="No provider serves"):
            resolve("telepathy", AUTO)
