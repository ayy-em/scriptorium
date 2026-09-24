"""Tests for the capability registry.

The probes themselves read the real machine, so these drive the mechanism —
caching, remedy classes, script mapping — with probes stubbed. What must not
regress is the reason this module exists: results that expire, so installing a
dependency does not need an app restart to be noticed.
"""

import os
from pathlib import Path
import sys

import pytest

from core import capabilities
from core.capabilities import (
    REMEDY_CONFIGURE,
    REMEDY_INSTALL,
    Capability,
    capability_name_for,
    for_script,
    invalidate,
    missing,
    model_weights_present,
    probe,
    probe_all,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test starts with no cached probe results."""
    invalidate()
    yield
    invalidate()


class TestRegistryShape:
    def test_every_capability_probes_to_something(self):
        assert all(isinstance(c.present, bool) for c in probe_all())

    def test_names_are_unique(self):
        names = [c.name for c in probe_all()]
        assert len(names) == len(set(names))

    def test_every_capability_explains_itself(self):
        """A banner with no "what breaks" and no "what to do" is just an alarm."""
        for c in probe_all():
            assert c.needed_for, c.name
            assert c.hint, c.name

    def test_an_unknown_name_is_none_rather_than_an_error(self):
        assert probe("pandocc") is None

    def test_known_names_resolve(self):
        assert probe("ffmpeg") is not None

    def test_the_openai_key_is_configured_not_installed(self):
        """It is not a binary, so "not found — brew install" would be nonsense."""
        assert probe("openai-key").remedy == REMEDY_CONFIGURE

    def test_binaries_are_install_remedies(self):
        assert probe("pandoc").remedy == REMEDY_INSTALL


@pytest.fixture
def stub_registry(monkeypatch):
    """Replace the registry with one entry whose probe the test controls."""

    def _install(fn):
        specs = (
            capabilities._Spec(
                name="stub",
                label="Stub",
                remedy=REMEDY_INSTALL,
                required=True,
                needed_for="testing",
                probe=fn,
                hints={"": "install the stub"},
            ),
        )
        monkeypatch.setattr(capabilities, "_SPECS", specs)
        monkeypatch.setattr(capabilities, "_BY_NAME", {s.name: s for s in specs})

    return _install


class TestCaching:
    def test_a_second_call_reuses_the_first_answer(self, stub_registry):
        calls = []
        stub_registry(lambda: calls.append(1) or True)
        probe("stub")
        probe("stub")
        assert len(calls) == 1

    def test_results_expire(self, monkeypatch, stub_registry):
        """The whole point: installing ffmpeg must not need an app restart."""
        answers = iter([False, True])
        stub_registry(lambda: next(answers))
        monkeypatch.setattr(capabilities, "CACHE_SECONDS", 0.0)
        assert probe("stub").present is False
        assert probe("stub").present is True

    def test_invalidate_drops_cached_answers(self, stub_registry):
        answers = iter([False, True])
        stub_registry(lambda: next(answers))
        assert probe("stub").present is False
        invalidate()
        assert probe("stub").present is True

    def test_a_raising_probe_counts_as_absent(self, stub_registry):
        """A broken probe must not take a page render down with it."""

        def _boom():
            raise OSError("nope")

        stub_registry(_boom)
        assert probe("stub").present is False


class TestMissing:
    def test_present_capabilities_are_not_reported(self, monkeypatch):
        monkeypatch.setattr(capabilities, "probe_all", lambda: (_cap("a", present=True),))
        assert missing() == ()

    def test_absent_required_capabilities_are_reported(self, monkeypatch):
        monkeypatch.setattr(capabilities, "probe_all", lambda: (_cap("a", present=False),))
        assert [c.name for c in missing()] == ["a"]

    def test_optional_capabilities_are_excluded_by_default(self, monkeypatch):
        """A missing gifsicle means a larger GIF, not a broken script."""
        monkeypatch.setattr(
            capabilities,
            "probe_all",
            lambda: (_cap("gifsicle", present=False, required=False),),
        )
        assert missing() == ()
        assert [c.name for c in missing(required_only=False)] == ["gifsicle"]


def _cap(name: str, *, present: bool, required: bool = True) -> Capability:
    """Build a Capability for the missing() filters."""
    return Capability(
        name=name,
        label=name,
        present=present,
        remedy=REMEDY_INSTALL,
        required=required,
        needed_for="testing",
        hint="do something",
    )


class TestScriptMapping:
    def test_a_theme_default_applies(self):
        assert capability_name_for("av.trim") == "ffmpeg"

    def test_a_script_can_depart_from_its_theme(self):
        assert capability_name_for("formats.convert_video") == "ffmpeg"
        assert capability_name_for("formats.convert_docs") == "pandoc"

    def test_a_script_needing_nothing_maps_to_none(self):
        assert capability_name_for("lora.validate") is None

    def test_make_gif_does_not_need_ffmpeg(self):
        """BACKLOG.md listed gif.* as an ffmpeg consumer; it assembles with PIL."""
        assert capability_name_for("gif.make_gif") is None

    def test_telegram_pdf_scripts_need_pango(self):
        assert capability_name_for("telegram.chat_analysis") == "pango"
        assert capability_name_for("telegram.group_analysis") == "pango"

    def test_telegram_scripts_without_pdf_output_do_not(self):
        assert capability_name_for("telegram.preprocess") is None

    def test_for_script_returns_a_probed_capability(self):
        assert for_script("av.trim").name == "ffmpeg"

    def test_for_script_is_none_when_nothing_is_needed(self):
        assert for_script("lora.validate") is None

    def test_remove_bg_is_not_in_the_static_registry(self):
        """Its dependency is per-model, so it goes through model_weights_present."""
        assert for_script("photo.remove_bg") is None


class TestInstallCommands:
    """A button only appears where one unattended command actually fixes it."""

    def test_winget_commands_never_prompt(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        command = probe("pandoc").command
        assert command[:2] == ("winget", "install")
        assert "--accept-source-agreements" in command
        assert "--accept-package-agreements" in command
        assert "--disable-interactivity" in command

    def test_pango_has_no_unattended_install_on_windows(self, monkeypatch):
        """MSYS2 plus pacman is not one command; the hint stays text."""
        monkeypatch.setattr(sys, "platform", "win32")
        assert probe("pango").command == ()
        assert probe("pango").hint

    def test_macos_uses_brew(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        assert probe("ffmpeg").command == ("brew", "install", "ffmpeg")

    def test_linux_has_no_command(self, monkeypatch):
        """Apt needs sudo, which a background process cannot supply."""
        monkeypatch.setattr(sys, "platform", "linux")
        assert probe("ffmpeg").command == ()

    def test_a_key_is_never_installable(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert probe("openai-key").command == ()


class TestRefreshEnvironment:
    def test_windows_prepends_the_registry_path_and_keeps_extras(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(capabilities, "_windows_registry_path", lambda: os.pathsep.join(["C:/new", "C:/old"]))
        monkeypatch.setenv("PATH", os.pathsep.join(["C:/old", "C:/launcher"]))
        capabilities.refresh_environment()
        assert os.environ["PATH"].split(os.pathsep) == ["C:/new", "C:/old", "C:/launcher"]

    def test_a_registry_failure_leaves_path_alone(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")

        def _boom():
            raise OSError("no registry")

        monkeypatch.setattr(capabilities, "_windows_registry_path", _boom)
        monkeypatch.setenv("PATH", "C:/only")
        capabilities.refresh_environment()
        assert os.environ["PATH"] == "C:/only"

    def test_other_platforms_only_drop_the_cache(self, monkeypatch, stub_registry):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("PATH", "/usr/bin")
        answers = iter([False, True])
        stub_registry(lambda: next(answers))
        assert probe("stub").present is False
        capabilities.refresh_environment()
        assert os.environ["PATH"] == "/usr/bin"
        assert probe("stub").present is True


class TestModelWeights:
    def test_absent_when_the_file_is_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(capabilities, "model_weights_dir", lambda: tmp_path)
        assert model_weights_present("u2net") is False

    def test_present_when_the_file_exists(self, monkeypatch, tmp_path):
        monkeypatch.setattr(capabilities, "model_weights_dir", lambda: tmp_path)
        (tmp_path / "u2net.onnx").touch()
        assert model_weights_present("u2net") is True

    def test_models_are_tracked_separately(self, monkeypatch, tmp_path):
        monkeypatch.setattr(capabilities, "model_weights_dir", lambda: tmp_path)
        (tmp_path / "u2net.onnx").touch()
        assert model_weights_present("u2net") is True
        assert model_weights_present("birefnet-general") is False

    def test_the_weights_dir_honours_u2net_home(self, monkeypatch, tmp_path):
        """The same variable rembg reads, so a relocated cache is followed."""
        monkeypatch.setenv("U2NET_HOME", str(tmp_path / "elsewhere"))
        assert capabilities.model_weights_dir() == Path(tmp_path / "elsewhere")
