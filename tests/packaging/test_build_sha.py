"""Tests for packaging.build_sha — the commit hash a frozen build carries."""

from pathlib import Path
import subprocess
import sys

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
# packaging/ is not a package (the specs import from it by path), so mirror
# what they and test_entrypoint do.
sys.path.insert(0, str(_REPO_ROOT / "packaging"))
import build_sha as module  # noqa: E402
from build_sha import BUILD_SHA_FILENAME, build_sha, write_build_sha  # noqa: E402


def _fake_git(stdout: str, returncode: int = 0):  # noqa: ANN202
    def _run(*_args, **_kwargs) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")

    return _run


class TestBuildSha:
    def test_uses_git_when_it_answers(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(module.subprocess, "run", _fake_git("abc1234\n"))
        monkeypatch.setenv("GITHUB_SHA", "ffffffffffffffff")
        assert build_sha(_REPO_ROOT) == "abc1234"

    def test_falls_back_to_the_actions_sha_when_git_fails(self, monkeypatch: pytest.MonkeyPatch):
        """A source tarball on CI has no .git, but Actions still knows the commit."""
        monkeypatch.setattr(module.subprocess, "run", _fake_git("", returncode=128))
        monkeypatch.setenv("GITHUB_SHA", "0123456789abcdef")
        assert build_sha(_REPO_ROOT) == "0123456"

    def test_falls_back_when_git_is_missing_entirely(self, monkeypatch: pytest.MonkeyPatch):
        def _no_git(*_args, **_kwargs) -> None:
            raise FileNotFoundError("git")

        monkeypatch.setattr(module.subprocess, "run", _no_git)
        monkeypatch.setenv("GITHUB_SHA", "deadbeefcafe")
        assert build_sha(_REPO_ROOT) == "deadbee"

    def test_empty_when_nothing_knows(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(module.subprocess, "run", _fake_git("", returncode=128))
        monkeypatch.delenv("GITHUB_SHA", raising=False)
        assert build_sha(_REPO_ROOT) == ""

    def test_reads_the_real_repository(self):
        """This checkout is a git repository, so the hash is a real short one."""
        sha = build_sha(_REPO_ROOT)
        assert sha, "expected git to answer inside the repository"
        assert all(c in "0123456789abcdef" for c in sha)


class TestWriteBuildSha:
    def test_writes_the_file_the_specs_bundle(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(module, "build_sha", lambda _root: "abc1234")
        path = write_build_sha(_REPO_ROOT, tmp_path / "work")
        assert path == tmp_path / "work" / BUILD_SHA_FILENAME
        assert path.read_text(encoding="utf-8") == "abc1234\n"

    def test_writes_an_empty_file_rather_than_failing_the_build(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """The datas entry must always point at a real file."""
        monkeypatch.setattr(module, "build_sha", lambda _root: "")
        path = write_build_sha(_REPO_ROOT, tmp_path)
        assert path.is_file()
        assert path.read_text(encoding="utf-8").strip() == ""
