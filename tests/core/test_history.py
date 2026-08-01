"""Tests for run history persistence."""

import json

import pytest

from core import history
from core.history import RunRecord


@pytest.fixture(autouse=True)
def temp_history(tmp_path, monkeypatch):
    """Point the history file at a temp path for every test in this module."""
    path = tmp_path / "history.json"
    monkeypatch.setattr(history, "_HISTORY_PATH", path)
    return path


def _record(run_id="abc123", key="av.filmstrip", status=history.SUCCESS, **kw):
    defaults = {
        "started_at": "2026-07-28T02:31:05",
        "elapsed": 1.5,
        "exit_code": 0,
        "argv": ["clip.mp4", "--grid", "3x3"],
        "params": {"source": "clip.mp4", "grid": "3x3"},
    }
    defaults.update(kw)
    return RunRecord(run_id=run_id, key=key, status=status, **defaults)


class TestRunRecord:
    def test_splits_the_key_into_theme_and_script(self):
        r = _record(key="av.filmstrip")
        assert r.theme == "av"
        assert r.script_name == "filmstrip"

    def test_key_without_a_dot_degrades_gracefully(self):
        r = _record(key="orphan")
        assert r.theme == "orphan"
        assert r.script_name == "orphan"

    def test_is_immutable(self):
        with pytest.raises(AttributeError):
            _record().status = history.ERROR


class TestLoad:
    def test_missing_file_is_empty(self):
        assert history.load() == []

    def test_corrupt_json_is_empty_not_an_error(self, temp_history):
        temp_history.write_text("{not json", encoding="utf-8")
        assert history.load() == []

    def test_non_list_payload_is_empty(self, temp_history):
        temp_history.write_text('{"runs": []}', encoding="utf-8")
        assert history.load() == []

    def test_one_bad_entry_does_not_discard_the_good_ones(self, temp_history):
        good = {
            "run_id": "ok",
            "key": "av.trim",
            "status": "success",
            "started_at": "2026-07-28T01:00:00",
            "elapsed": 1.0,
            "exit_code": 0,
            "argv": [],
            "params": {},
        }
        temp_history.write_text(json.dumps([{"missing": "fields"}, good]), encoding="utf-8")
        loaded = history.load()
        assert len(loaded) == 1
        assert loaded[0].run_id == "ok"

    def test_skips_non_dict_entries(self, temp_history):
        temp_history.write_text(json.dumps(["nope", 42]), encoding="utf-8")
        assert history.load() == []


class TestAppend:
    def test_stores_and_reads_back(self):
        history.append(_record())
        loaded = history.load()
        assert len(loaded) == 1
        assert loaded[0] == _record()

    def test_newest_first(self):
        history.append(_record(run_id="first"))
        history.append(_record(run_id="second"))
        assert [r.run_id for r in history.load()] == ["second", "first"]

    def test_round_trips_argv_and_params(self):
        history.append(_record(argv=["a b", "--x", "1"], params={"src": "a b"}))
        loaded = history.load()[0]
        assert loaded.argv == ["a b", "--x", "1"]
        assert loaded.params == {"src": "a b"}

    def test_creates_the_parent_directory(self, tmp_path, monkeypatch):
        nested = tmp_path / "deep" / "nested" / "history.json"
        monkeypatch.setattr(history, "_HISTORY_PATH", nested)
        history.append(_record())
        assert nested.exists()

    def test_caps_at_max_entries(self):
        for i in range(history.MAX_ENTRIES + 25):
            history.append(_record(run_id=f"r{i}"))
        loaded = history.load()
        assert len(loaded) == history.MAX_ENTRIES
        # The newest survives, the oldest is gone.
        assert loaded[0].run_id == f"r{history.MAX_ENTRIES + 24}"
        assert all(r.run_id != "r0" for r in loaded)


class TestGetAndClear:
    def test_get_finds_a_record(self):
        history.append(_record(run_id="wanted"))
        history.append(_record(run_id="other"))
        assert history.get("wanted").run_id == "wanted"

    def test_get_returns_none_when_absent(self):
        assert history.get("nope") is None

    def test_clear_empties_the_history(self):
        history.append(_record())
        history.clear()
        assert history.load() == []

    def test_clear_on_empty_history_is_fine(self):
        history.clear()
        assert history.load() == []


class TestStatuses:
    @pytest.mark.parametrize("status", [history.SUCCESS, history.ERROR, history.CANCELLED])
    def test_every_status_round_trips(self, status):
        history.append(_record(run_id=status, status=status))
        assert history.get(status).status == status

    def test_cancelled_run_keeps_its_exit_code(self):
        history.append(_record(status=history.CANCELLED, exit_code=1))
        assert history.load()[0].exit_code == 1

    def test_exit_code_may_be_absent(self):
        history.append(_record(exit_code=None))
        assert history.load()[0].exit_code is None


def test_history_path_points_at_the_configured_file(temp_history):
    assert history.history_path() == temp_history


class TestBatchId:
    """Groups the records of one per-file fan-out without a second record type."""

    def test_roundtrips(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.history._HISTORY_PATH", tmp_path / "history.json")
        for i in range(3):
            history.append(
                RunRecord(
                    run_id=f"r{i}",
                    key="av.trim",
                    status="success",
                    started_at="2026-08-02T00:00:00",
                    elapsed=1.0,
                    batch_id="b1",
                )
            )
        assert {r.batch_id for r in history.load()} == {"b1"}

    def test_defaults_to_empty_for_a_single_run(self):
        assert (
            RunRecord(
                run_id="r",
                key="av.trim",
                status="success",
                started_at="2026-08-02T00:00:00",
                elapsed=1.0,
            ).batch_id
            == ""
        )

    def test_records_written_before_the_field_existed_still_load(self, tmp_path, monkeypatch):
        path = tmp_path / "history.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "run_id": "old",
                        "key": "av.trim",
                        "status": "success",
                        "started_at": "2026-07-01T00:00:00",
                        "elapsed": 2.0,
                    }
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr("core.history._HISTORY_PATH", path)
        record = history.load()[0]
        assert record.batch_id == ""
        assert record.outputs == []
