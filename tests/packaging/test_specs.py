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

    def test_does_not_exclude_unittest(self, name):
        """Scipy needs stdlib unittest at import time, via numpy.

        scipy pulls in array_api_compat, which runs ``from numpy import *``.
        ``testing`` is in numpy's ``__all__``, so that fires numpy's lazy
        ``__getattr__`` into ``numpy/testing/__init__.py``, whose first line is
        ``from unittest import TestCase``. Excluding unittest therefore breaks
        photo.remove_bg (rembg -> pymatting -> scipy) in the built app only.
        """
        assert '"unittest"' not in _spec(name)

    def test_collects_numpy_testing(self, name):
        """Only reachable through numpy's lazy __getattr__, so declare it."""
        assert '"numpy.testing"' in _spec(name)

    def test_copies_rembg_dependency_metadata(self, name):
        """Pymatting reads its own dist-info at import time, unguarded.

        ``pymatting/__init__.py`` ends with
        ``importlib.metadata.version(__name__)``. rembg wraps its own lookup in
        ``PackageNotFoundError``; pymatting does not, so a bundle missing the
        dist-info fails photo.remove_bg at run time. Recursive covers the whole
        graph instead of waiting for the next dependency to do the same.
        """
        spec = _spec(name)
        assert "copy_metadata" in spec
        assert "recursive=True" in spec
        assert '_metadata("rembg")' in spec


class TestWindowsHasNoNativeWindow:
    """Windows ships without pywebview, deliberately.

    The WinForms backend imports clr, which raises "Failed to initialize
    Python.Runtime.dll" in every frozen build — bundling clr_loader and
    pythonnet was tried and verified not to help. Chromium --app is the
    supported tier there, so the whole stack is left out of the bundle.
    """

    def test_does_not_bundle_the_pythonnet_stack(self):
        spec = _spec("scriptorium-win.spec")
        assert '_collect("clr_loader")' not in spec
        assert '_collect("pythonnet")' not in spec

    def test_excludes_webview_and_clr(self):
        spec = _spec("scriptorium-win.spec")
        for name in ('"webview"', '"clr"', '"clr_loader"', '"pythonnet"'):
            assert name in spec, f"{name} should be in the Windows excludes"

    def test_other_platforms_still_collect_pywebview(self):
        """MacOS and Linux use tier 1 for real; only Windows opts out."""
        for name in ("scriptorium.spec", "scriptorium-linux.spec"):
            assert '"webview"' in _spec(name), name


@pytest.mark.parametrize("name", SPECS)
def test_bundles_pyproject_for_version_lookup(name):
    """core.paths.read_version reads pyproject.toml out of the bundle."""
    assert "pyproject.toml" in _spec(name)


@pytest.mark.parametrize("name", SPECS)
def test_bundles_static_and_templates(name):
    spec = _spec(name)
    assert "webapp/static" in spec
    assert "webapp/templates" in spec
