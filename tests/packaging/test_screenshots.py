"""Tests for packaging/screenshots.py — the parts that run without a browser."""

import json
from pathlib import Path
import sys

import pytest

Image = pytest.importorskip("PIL.Image")

_REPO_ROOT = Path(__file__).parent.parent.parent
# packaging/ is not a package; mirror test_build_sha.
sys.path.insert(0, str(_REPO_ROOT / "packaging"))
import screenshots as module  # noqa: E402

from core.history import _from_raw  # noqa: E402


class TestSeedHome:
    def test_history_rows_are_readable_by_the_app(self, tmp_path: Path) -> None:
        module._seed_home(tmp_path, "dark")
        raw = json.loads((tmp_path / "scriptorium" / "history.json").read_text(encoding="utf-8"))
        records = [_from_raw(r) for r in raw]
        assert records and all(r is not None for r in records)

    def test_config_carries_the_theme(self, tmp_path: Path) -> None:
        module._seed_home(tmp_path, "dark")
        config = json.loads((tmp_path / "scriptorium" / "config.json").read_text(encoding="utf-8"))
        assert config["theme"] == "dark"

    def test_reseeding_replaces_rather_than_appends(self, tmp_path: Path) -> None:
        module._seed_home(tmp_path, "light")
        first = (tmp_path / "scriptorium" / "history.json").read_text(encoding="utf-8")
        module._seed_home(tmp_path, "light")
        again = json.loads((tmp_path / "scriptorium" / "history.json").read_text(encoding="utf-8"))
        assert len(again) == len(json.loads(first))


class TestTidy:
    def test_removes_only_what_appeared(self, tmp_path: Path) -> None:
        keep = tmp_path / "keep.txt"
        keep.write_text("x")
        with module._tidy(tmp_path):
            (tmp_path / "new.txt").write_text("y")
            (tmp_path / "batch").mkdir()
            (tmp_path / "batch" / "clip.mp4").write_text("z")
        assert sorted(p.name for p in tmp_path.iterdir()) == ["keep.txt"]

    def test_tolerates_a_missing_directory(self, tmp_path: Path) -> None:
        with module._tidy(tmp_path / "absent"):
            pass


class TestCarousel:
    def test_writes_a_looping_animation_with_transitions(self, tmp_path: Path) -> None:
        frames = [Image.new("RGB", (64, 40), colour) for colour in ("red", "green", "blue")]
        target = tmp_path / "out" / "carousel.webp"
        module._carousel(frames, target)

        with Image.open(target) as im:
            assert im.is_animated
            assert im.n_frames == len(frames) * (module.TRANSITION_FRAMES + 1)
            assert im.info.get("loop") == 0
            assert im.size == (64, 40)


def test_slide_names_are_unique() -> None:
    names = [s.name for s in module.SLIDES]
    assert len(names) == len(set(names))
