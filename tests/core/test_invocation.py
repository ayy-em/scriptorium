"""Tests for core.invocation and the path resolution that keys off it.

The web UI and a person at a terminal want opposite things from a relative
path, and both arrive as the same argv. These cover the marker that tells them
apart, and the two resolvers that read it.
"""

from pathlib import Path

from core.invocation import CALLER_ENV_VAR, is_webapp_run, webapp_spawn_env
from core.outputs import resolve_output, resolve_output_dir
from core.paths import resolve_input


class TestIsWebappRun:
    def test_false_without_the_marker(self, monkeypatch):
        monkeypatch.delenv(CALLER_ENV_VAR, raising=False)
        assert is_webapp_run() is False

    def test_true_with_the_marker(self, monkeypatch):
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        assert is_webapp_run() is True

    def test_an_unrelated_value_is_not_the_webapp(self, monkeypatch):
        monkeypatch.setenv(CALLER_ENV_VAR, "something-else")
        assert is_webapp_run() is False


class TestWebappSpawnEnv:
    def test_marks_the_caller(self):
        assert webapp_spawn_env()[CALLER_ENV_VAR] == "webapp"

    def test_preserves_the_rest_of_the_environment(self, monkeypatch):
        """A bare marker dict would strip PATH and break the subprocess."""
        monkeypatch.setenv("SCRIPTORIUM_TEST_CANARY", "kept")
        assert webapp_spawn_env()["SCRIPTORIUM_TEST_CANARY"] == "kept"


class TestResolveInput:
    """A bare filename is the only ambiguous case; everything else is literal."""

    def test_bare_filename_from_the_cli_stays_relative(self, monkeypatch):
        monkeypatch.delenv(CALLER_ENV_VAR, raising=False)
        assert resolve_input(Path("clip.mp4"), "av") == Path("clip.mp4")

    def test_bare_filename_from_the_webapp_goes_to_inputs(self, monkeypatch, tmp_path):
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        monkeypatch.setattr("core.paths.inputs_dir", lambda theme: tmp_path)
        assert resolve_input(Path("clip.mp4"), "av") == tmp_path / "clip.mp4"

    def test_dot_slash_cannot_force_the_cwd(self, monkeypatch, tmp_path):
        """Path drops the leading './' at construction, so it cannot be honoured.

        Worth pinning: it is the obvious thing to reach for, and it silently
        does nothing. Escaping the inputs dir needs a real directory part.
        """
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        monkeypatch.setattr("core.paths.inputs_dir", lambda theme: tmp_path)
        assert resolve_input(Path("./clip.mp4"), "av") == tmp_path / "clip.mp4"

    def test_nested_relative_path_is_untouched(self, monkeypatch):
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        assert resolve_input(Path("sub/clip.mp4"), "av") == Path("sub/clip.mp4")

    def test_absolute_path_is_untouched(self, monkeypatch, tmp_path):
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        target = tmp_path / "clip.mp4"
        assert resolve_input(target, "av") == target


class TestOutputsFollowTheCaller:
    def test_cli_default_is_the_current_directory(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CALLER_ENV_VAR, raising=False)
        monkeypatch.chdir(tmp_path)
        assert resolve_output(None, theme="av", ext=".mp4").parent == tmp_path

    def test_webapp_default_is_the_managed_outputs_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv(CALLER_ENV_VAR, "webapp")
        managed = tmp_path / "managed"
        monkeypatch.setattr("core.outputs.outputs_dir", lambda theme: managed)
        assert resolve_output(None, theme="av", ext=".mp4").parent == managed

    def test_cli_bare_output_name_lands_in_the_current_directory(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CALLER_ENV_VAR, raising=False)
        monkeypatch.chdir(tmp_path)
        got = resolve_output("clip.mp4", theme="av", ext=".mp4")
        assert got == tmp_path / "clip.mp4"

    def test_cli_output_dir_default_is_the_current_directory(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CALLER_ENV_VAR, raising=False)
        monkeypatch.chdir(tmp_path)
        assert resolve_output_dir(None, theme="formats") == tmp_path

    def test_an_explicit_path_beats_the_caller_either_way(self, monkeypatch, tmp_path):
        explicit = tmp_path / "chosen" / "out.mp4"
        for caller in ("webapp", None):
            if caller:
                monkeypatch.setenv(CALLER_ENV_VAR, caller)
            else:
                monkeypatch.delenv(CALLER_ENV_VAR, raising=False)
            assert resolve_output(str(explicit), theme="av", ext=".mp4") == explicit
            explicit.unlink(missing_ok=True)
