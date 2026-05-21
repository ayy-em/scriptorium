"""Tests for scripts.lora.import_captions."""

import json
from pathlib import Path

import pytest

from scripts.lora.import_captions import import_captions


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


class TestImportCaptions:
    def test_writes_files_to_output_dir(self, tmp_path: Path):
        src = tmp_path / "captions.json"
        _write_json(src, {"img_001.txt": "a cat", "img_002.txt": "a dog"})
        out_dir = tmp_path / "out"

        import_captions(src, out_dir)

        assert (out_dir / "img_001.txt").read_text(encoding="utf-8") == "a cat"
        assert (out_dir / "img_002.txt").read_text(encoding="utf-8") == "a dog"

    def test_missing_source_exits(self, tmp_path: Path):
        with pytest.raises(SystemExit) as excinfo:
            import_captions(tmp_path / "missing.json", tmp_path / "out")
        assert excinfo.value.code == 1

    def test_malformed_json_exits(self, tmp_path: Path):
        src = tmp_path / "bad.json"
        src.write_text("{not valid", encoding="utf-8")

        with pytest.raises(SystemExit) as excinfo:
            import_captions(src, tmp_path / "out")
        assert excinfo.value.code == 1

    def test_non_object_json_exits(self, tmp_path: Path):
        src = tmp_path / "arr.json"
        _write_json(src, ["a", "b"])

        with pytest.raises(SystemExit) as excinfo:
            import_captions(src, tmp_path / "out")
        assert excinfo.value.code == 1

    def test_invalid_key_format_exits(self, tmp_path: Path):
        src = tmp_path / "bad_keys.json"
        _write_json(src, {"photo_1.txt": "a cat"})

        with pytest.raises(SystemExit) as excinfo:
            import_captions(src, tmp_path / "out")
        assert excinfo.value.code == 1

    def test_non_string_value_exits(self, tmp_path: Path):
        src = tmp_path / "bad_vals.json"
        _write_json(src, {"img_001.txt": 42})

        with pytest.raises(SystemExit) as excinfo:
            import_captions(src, tmp_path / "out")
        assert excinfo.value.code == 1

    def test_non_consecutive_numbering_exits(self, tmp_path: Path):
        src = tmp_path / "gappy.json"
        _write_json(src, {"img_001.txt": "a", "img_003.txt": "c"})

        with pytest.raises(SystemExit) as excinfo:
            import_captions(src, tmp_path / "out")
        assert excinfo.value.code == 1
