"""Guards on the PyInstaller specs.

These are the only tests that can catch a packaging regression without running a
build: the frozen app fails *silently* when a script's imports are missing,
because ``core.registry.discover`` skips any module that will not import. That
is how ``photo.remove_bg`` and six others disappeared from the v0.5.2 builds.
"""

from pathlib import Path

import pytest

SPECS = ["scriptorium.spec", "scriptorium-win.spec", "scriptorium-linux.spec"]


def _spec(name: str) -> str:
    return (Path(__file__).parent.parent.parent / "packaging" / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", SPECS)
class TestScriptDiscovery:
    def test_collects_script_submodules(self, name):
        """A hand-maintained module list drifts; collect_submodules cannot."""
        assert 'collect_submodules("scripts")' in _spec(name)

    def test_collects_core_submodules(self, name):
        assert 'collect_submodules("core")' in _spec(name)

    def test_does_not_hand_list_individual_scripts(self, name):
        """Re-introducing a literal list is the regression this guards against."""
        spec = _spec(name)
        hand_listed = [
            line.strip()
            for line in spec.splitlines()
            # Three dotted parts means a concrete script module, e.g. scripts.av.trim.
            if line.strip().startswith('"scripts.') and line.strip().count(".") >= 2
        ]
        assert hand_listed == [], f"{name} hand-lists {hand_listed}"


@pytest.mark.parametrize("name", SPECS)
class TestNativeDependencies:
    def test_collects_rembg(self, name):
        """photo.remove_bg imports rembg, which static analysis cannot see."""
        assert '_collect("rembg")' in _spec(name)

    def test_collects_onnxruntime(self, name):
        """Rembg's inference backend, likewise invisible to static analysis."""
        assert '_collect("onnxruntime")' in _spec(name)

    def test_missing_optional_dependency_does_not_break_the_build(self, name):
        """_collect swallows a missing package so a build never dies on an extra."""
        spec = _spec(name)
        assert "def _collect(" in spec
        assert "except Exception" in spec


class TestWindowsNativeWindow:
    def test_collects_pythonnet_for_pywebview(self):
        """Guard the pywebview native-window dependency chain.

        Without pythonnet/clr, pywebview raises "Failed to initialize
        Python.Runtime.dll" and the app silently drops to the Chromium tier.
        """
        spec = _spec("scriptorium-win.spec")
        assert '_collect("clr_loader")' in spec
        assert '_collect("pythonnet")' in spec


@pytest.mark.parametrize("name", SPECS)
def test_bundles_pyproject_for_version_lookup(name):
    """core.paths.read_version reads pyproject.toml out of the bundle."""
    assert "pyproject.toml" in _spec(name)


@pytest.mark.parametrize("name", SPECS)
def test_bundles_static_and_templates(name):
    spec = _spec(name)
    assert "webapp/static" in spec
    assert "webapp/templates" in spec
