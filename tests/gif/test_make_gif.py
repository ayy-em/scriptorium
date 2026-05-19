"""Tests for scripts.gif.make_gif."""

from pathlib import Path

from PIL import Image
import pytest

from scripts.gif.make_gif import _find_frames, generate


def _draw_frame(directory: Path, name: str, color: tuple[int, int, int], size: tuple[int, int] = (32, 24)) -> Path:
    img = Image.new("RGB", size, color)
    path = directory / name
    img.save(path)
    return path


class TestFindFrames:
    def test_returns_image_files_only(self, tmp_path: Path):
        _draw_frame(tmp_path, "a.png", (255, 0, 0))
        _draw_frame(tmp_path, "b.jpg", (0, 255, 0))
        (tmp_path / "notes.txt").write_text("ignore me")

        result = _find_frames(tmp_path)

        assert [p.name for p in result] == ["a.png", "b.jpg"]

    def test_is_sorted(self, tmp_path: Path):
        _draw_frame(tmp_path, "c.png", (0, 0, 255))
        _draw_frame(tmp_path, "a.png", (255, 0, 0))
        _draw_frame(tmp_path, "b.png", (0, 255, 0))

        result = _find_frames(tmp_path)

        assert [p.name for p in result] == ["a.png", "b.png", "c.png"]


class TestGenerate:
    def test_creates_animated_gif(self, tmp_path: Path):
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        _draw_frame(frames_dir, "01.png", (255, 0, 0))
        _draw_frame(frames_dir, "02.png", (0, 255, 0))
        _draw_frame(frames_dir, "03.png", (0, 0, 255))
        output = tmp_path / "out.gif"

        result = generate(frames_dir, output)

        assert result == output
        with Image.open(output) as gif:
            assert gif.n_frames == 3
            assert gif.format == "GIF"

    def test_fps_controls_duration(self, tmp_path: Path):
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        _draw_frame(frames_dir, "01.png", (255, 0, 0))
        _draw_frame(frames_dir, "02.png", (0, 255, 0))
        output = tmp_path / "out.gif"

        generate(frames_dir, output, fps=4)

        with Image.open(output) as gif:
            assert gif.info["duration"] == 250  # 1000ms / 4fps

    def test_resizes_when_width_given(self, tmp_path: Path):
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        _draw_frame(frames_dir, "01.png", (255, 0, 0), size=(100, 50))
        _draw_frame(frames_dir, "02.png", (0, 255, 0), size=(100, 50))
        output = tmp_path / "out.gif"

        generate(frames_dir, output, width=40)

        with Image.open(output) as gif:
            assert gif.size == (40, 20)

    def test_loop_count_is_set(self, tmp_path: Path):
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        _draw_frame(frames_dir, "01.png", (255, 0, 0))
        output = tmp_path / "out.gif"

        generate(frames_dir, output, loop=3)

        with Image.open(output) as gif:
            assert gif.info.get("loop") == 3

    def test_missing_source_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="source directory"):
            generate(tmp_path / "ghost", tmp_path / "out.gif")

    def test_empty_directory_raises(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError, match="no images"):
            generate(empty, tmp_path / "out.gif")

    def test_zero_fps_rejected(self, tmp_path: Path):
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        _draw_frame(frames_dir, "01.png", (255, 0, 0))
        with pytest.raises(ValueError, match="fps must be positive"):
            generate(frames_dir, tmp_path / "out.gif", fps=0)

    def test_negative_width_rejected(self, tmp_path: Path):
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        _draw_frame(frames_dir, "01.png", (255, 0, 0))
        with pytest.raises(ValueError, match="width must be positive"):
            generate(frames_dir, tmp_path / "out.gif", width=-10)

    def test_creates_parent_dirs(self, tmp_path: Path):
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        _draw_frame(frames_dir, "01.png", (255, 0, 0))
        output = tmp_path / "deep" / "nested" / "out.gif"

        generate(frames_dir, output)

        assert output.exists()
