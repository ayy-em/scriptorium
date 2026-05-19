"""Tests for scripts.lora.export_captions."""

import json
from pathlib import Path

import pytest

from scripts.lora.export_captions import export


def _write_caption(d: Path, name: str, text: str) -> None:
    (d / name).write_text(text, encoding="utf-8")


class TestExport:
    def test_writes_file_when_output_given(self, tmp_path: Path):
        _write_caption(tmp_path, "img_001.txt", "a cat")
        _write_caption(tmp_path, "img_002.txt", "a dog")
        out = tmp_path / "out" / "captions.json"

        export(tmp_path, out)

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data == {"img_001.txt": "a cat", "img_002.txt": "a dog"}

    def test_strips_trailing_whitespace(self, tmp_path: Path):
        _write_caption(tmp_path, "img_001.txt", "  a cat\n")
        out = tmp_path / "captions.json"

        export(tmp_path, out)

        assert json.loads(out.read_text(encoding="utf-8"))["img_001.txt"] == "a cat"

    def test_prints_to_stdout_when_no_output(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        _write_caption(tmp_path, "img_001.txt", "a cat")

        export(tmp_path, None)

        out = capsys.readouterr().out
        assert json.loads(out) == {"img_001.txt": "a cat"}

    def test_empty_directory_writes_empty_object(self, tmp_path: Path):
        out = tmp_path / "captions.json"
        export(tmp_path, out)
        assert json.loads(out.read_text(encoding="utf-8")) == {}

    def test_missing_directory_exits_with_error(self, tmp_path: Path):
        with pytest.raises(SystemExit) as excinfo:
            export(tmp_path / "does-not-exist", None)
        assert excinfo.value.code == 1

    def test_creates_parent_dir(self, tmp_path: Path):
        _write_caption(tmp_path, "img_001.txt", "a cat")
        out = tmp_path / "nested" / "deep" / "captions.json"

        export(tmp_path, out)

        assert out.exists()
