"""Tests for scripts.telegram.preprocess."""

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts.telegram.preprocess import SCHEMA_VERSION, preprocess


def _write_export(path: Path, messages: list[dict], name: str = "Test") -> Path:
    path.write_text(
        json.dumps(
            {
                "name": name,
                "type": "personal_chat",
                "id": 42,
                "messages": messages,
            }
        ),
        encoding="utf-8",
    )
    return path


def _msg(year: int, **extras) -> dict:
    base = {
        "id": extras.pop("id", 1),
        "type": extras.pop("type", "message"),
        "date": f"{year}-03-27T17:55:18",
        "date_unixtime": "1459094118",
        "from": "Alice",
        "from_id": "user1",
        "text": "hello",
        "text_entities": [{"type": "plain", "text": "hello"}],
    }
    base.update(extras)
    return base


def _zip_contents(zip_path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(zip_path) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


class TestPreprocess:
    def test_writes_one_file_per_year(self, tmp_path: Path):
        export = _write_export(
            tmp_path / "result.json",
            [_msg(2016), _msg(2017), _msg(2017), _msg(2019)],
        )
        out = tmp_path / "processed.zip"

        preprocess(export, out)

        contents = _zip_contents(out)
        assert "messages_2016.json" in contents
        assert "messages_2017.json" in contents
        assert "messages_2019.json" in contents
        assert "messages_2018.json" not in contents
        assert "manifest.json" in contents

    def test_messages_are_trimmed_and_keys_renamed(self, tmp_path: Path):
        export = _write_export(tmp_path / "result.json", [_msg(2020, id=99)])
        out = tmp_path / "processed.zip"

        preprocess(export, out)

        msgs = json.loads(_zip_contents(out)["messages_2020.json"])
        assert len(msgs) == 1
        m = msgs[0]
        assert m == {
            "t": "message",
            "d": "2020-03-27T17:55:18",
            "f": "Alice",
            "e": [{"type": "plain", "text": "hello"}],
        }

    def test_optional_fields_kept_with_short_keys(self, tmp_path: Path):
        export = _write_export(
            tmp_path / "result.json",
            [
                _msg(
                    2020,
                    reply_to_message_id=10,
                    forwarded_from="Other",
                    media_type="video_message",
                )
            ],
        )
        out = tmp_path / "processed.zip"

        preprocess(export, out)

        m = json.loads(_zip_contents(out)["messages_2020.json"])[0]
        assert m["r"] == 10
        assert m["fwd"] == "Other"
        assert m["m"] == "video_message"

    def test_service_messages_dropped_by_default(self, tmp_path: Path):
        export = _write_export(
            tmp_path / "result.json",
            [_msg(2020, type="message"), _msg(2020, type="service")],
        )
        out = tmp_path / "processed.zip"

        preprocess(export, out)

        msgs = json.loads(_zip_contents(out)["messages_2020.json"])
        assert len(msgs) == 1
        assert msgs[0]["t"] == "message"

    def test_service_messages_kept_when_flag_set(self, tmp_path: Path):
        export = _write_export(
            tmp_path / "result.json",
            [_msg(2020, type="message"), _msg(2020, type="service")],
        )
        out = tmp_path / "processed.zip"

        preprocess(export, out, keep_service=True)

        msgs = json.loads(_zip_contents(out)["messages_2020.json"])
        assert len(msgs) == 2

    def test_manifest_has_expected_fields(self, tmp_path: Path):
        export = _write_export(
            tmp_path / "result.json",
            [_msg(2016), _msg(2016), _msg(2017)],
        )
        out = tmp_path / "processed.zip"

        preprocess(export, out)

        manifest = json.loads(_zip_contents(out)["manifest.json"])
        assert manifest["source_name"] == "result.json"
        assert manifest["schema_version"] == SCHEMA_VERSION
        assert manifest["total_messages"] == 3
        assert manifest["per_year_counts"] == {"2016": 2, "2017": 1}
        assert manifest["keep_service"] is False
        assert "field_map" in manifest

        sha_expected = hashlib.sha256(export.read_bytes()).hexdigest()
        assert manifest["source_sha256"] == sha_expected

    def test_field_map_round_trip(self, tmp_path: Path):
        export = _write_export(tmp_path / "result.json", [_msg(2020)])
        out = tmp_path / "processed.zip"

        preprocess(export, out)

        manifest = json.loads(_zip_contents(out)["manifest.json"])
        msg = json.loads(_zip_contents(out)["messages_2020.json"])[0]
        # Every short key in the message has a mapping in the manifest.
        for short_key in msg:
            assert short_key in manifest["field_map"], f"missing field_map entry for {short_key!r}"

    def test_missing_source_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            preprocess(tmp_path / "nope.json", tmp_path / "out.zip")

    def test_skipped_no_date_counted(self, tmp_path: Path):
        export = _write_export(
            tmp_path / "result.json",
            [_msg(2020), {"type": "message", "from": "Bob", "text_entities": []}],
        )
        out = tmp_path / "processed.zip"

        preprocess(export, out)

        manifest = json.loads(_zip_contents(out)["manifest.json"])
        assert manifest["skipped_no_date"] == 1
        assert manifest["total_messages"] == 1

    def test_handles_50_messages_across_three_years(self, tmp_path: Path):
        msgs = []
        for year in (2020, 2021, 2022):
            for i in range(17):
                msgs.append(_msg(year, id=i + year * 100))
        msgs = msgs[:50]
        export = _write_export(tmp_path / "result.json", msgs)
        out = tmp_path / "processed.zip"

        preprocess(export, out)

        manifest = json.loads(_zip_contents(out)["manifest.json"])
        assert manifest["total_messages"] == 50
        assert set(manifest["per_year_counts"]) == {"2020", "2021", "2022"}
