"""Tests for scripts.telegram.embed_messages."""

import json
from pathlib import Path
from unittest.mock import MagicMock
import zipfile

import pytest

from scripts.telegram.embed_messages import (
    DEFAULT_MODEL,
    MissingCredentialsError,
    _build_unit_text,
    _content_hash,
    _plain_text,
    embed_messages,
)


def _msg(year: int, sender: str, text: str, **extras) -> dict:
    base = {
        "t": "message",
        "d": f"{year}-03-27T17:55:18",
        "f": sender,
        "e": [{"type": "plain", "text": text}],
    }
    base.update(extras)
    return base


def _stub_client(dim: int = 4) -> MagicMock:
    """Return a fake OpenAI client whose embedding vectors are deterministic per call."""
    client = MagicMock()
    counter = {"i": 0}

    def fake_create(*, input, model):  # noqa: A002
        out = []
        for _ in input:
            counter["i"] += 1
            out.append(MagicMock(embedding=[float(counter["i"]) * 0.1] * dim))
        return MagicMock(data=out)

    client.embeddings.create.side_effect = fake_create
    return client


def _write_zip(tmp_path: Path, by_year: dict[int, list[dict]]) -> Path:
    path = tmp_path / "processed.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for year, messages in by_year.items():
            zf.writestr(f"messages_{year}.json", json.dumps(messages))
        zf.writestr("manifest.json", "{}")
    return path


class TestHelpers:
    def test_plain_text_flattens_entities(self):
        msg = {"e": [{"type": "plain", "text": "hi "}, {"type": "bold", "text": "there"}]}
        assert _plain_text(msg) == "hi there"

    def test_plain_text_handles_empty(self):
        assert _plain_text({}) == ""
        assert _plain_text({"e": None}) == ""

    def test_build_unit_text_includes_context_then_current(self):
        ctx = [_msg(2020, "Alice", "first"), _msg(2020, "Bob", "second")]
        current = _msg(2020, "Alice", "third")
        result = _build_unit_text(current, ctx)
        lines = result.split("\n")
        assert len(lines) == 3
        assert "first" in lines[0]
        assert "second" in lines[1]
        assert "third" in lines[2]

    def test_content_hash_is_stable(self):
        assert _content_hash("hello") == _content_hash("hello")
        assert _content_hash("hello") != _content_hash("HELLO")


class TestEmbedMessages:
    def test_writes_embeddings_jsonl_and_manifest(self, tmp_path: Path):
        source = _write_zip(tmp_path, {2020: [_msg(2020, "Alice", "hi"), _msg(2020, "Bob", "hey")]})
        out_dir = tmp_path / "embeddings"

        manifest_path = embed_messages(source, out_dir, client=_stub_client())

        assert manifest_path == out_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["total_units"] == 2
        assert manifest["model"] == DEFAULT_MODEL
        assert manifest["dimensions"] == 4

        lines = (out_dir / "embeddings.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["unit_id"] == 0
        assert first["from"] == "Alice"
        assert len(first["embedding"]) == 4

    def test_zip_messages_concatenated_in_year_order(self, tmp_path: Path):
        source = _write_zip(
            tmp_path,
            {
                2021: [_msg(2021, "Bob", "later")],
                2020: [_msg(2020, "Alice", "earlier")],
            },
        )
        out_dir = tmp_path / "out"

        embed_messages(source, out_dir, client=_stub_client())

        records = [json.loads(line) for line in (out_dir / "embeddings.jsonl").read_text().splitlines()]
        assert records[0]["text"] == "earlier"
        assert records[1]["text"] == "later"

    def test_window_includes_preceding_messages_only(self, tmp_path: Path):
        source = _write_zip(
            tmp_path,
            {2020: [_msg(2020, "Alice", str(i)) for i in range(5)]},
        )
        out_dir = tmp_path / "out"
        client = _stub_client()

        embed_messages(source, out_dir, window=2, client=client)

        calls = client.embeddings.create.call_args_list
        sent_inputs = [t for call in calls for t in call.kwargs["input"]]
        # 5 units total; unit 4 has context of units 2 and 3 + its own line.
        unit_4_text = sent_inputs[4]
        assert unit_4_text.count("\n") == 2  # 2 context lines + 1 current line = 2 newlines
        # First unit has no context (window starts before message 0).
        assert sent_inputs[0].count("\n") == 0

    def test_cache_avoids_re_embedding_identical_content(self, tmp_path: Path):
        source = _write_zip(tmp_path, {2020: [_msg(2020, "Alice", "same") for _ in range(3)]})
        out_dir = tmp_path / "out"
        client = _stub_client()

        embed_messages(source, out_dir, window=0, client=client)

        sent_inputs = [t for call in client.embeddings.create.call_args_list for t in call.kwargs["input"]]
        # All three messages are identical with window=0, so only one unique text is sent.
        assert len(sent_inputs) == 1

    def test_second_run_reuses_cache(self, tmp_path: Path):
        source = _write_zip(tmp_path, {2020: [_msg(2020, "Alice", "x")]})
        out_dir = tmp_path / "out"

        client1 = _stub_client()
        embed_messages(source, out_dir, client=client1)
        assert client1.embeddings.create.call_count == 1

        client2 = _stub_client()
        embed_messages(source, out_dir, client=client2)
        assert client2.embeddings.create.call_count == 0

    def test_accepts_single_json_source(self, tmp_path: Path):
        source = tmp_path / "messages_2020.json"
        source.write_text(json.dumps([_msg(2020, "Alice", "solo")]), encoding="utf-8")
        out_dir = tmp_path / "out"

        embed_messages(source, out_dir, client=_stub_client())

        records = [json.loads(line) for line in (out_dir / "embeddings.jsonl").read_text().splitlines()]
        assert len(records) == 1

    def test_missing_source_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            embed_messages(tmp_path / "nope.zip", tmp_path / "out", client=_stub_client())

    def test_negative_window_rejected(self, tmp_path: Path):
        source = _write_zip(tmp_path, {2020: [_msg(2020, "Alice", "x")]})
        with pytest.raises(ValueError, match="window"):
            embed_messages(source, tmp_path / "out", window=-1, client=_stub_client())

    def test_zero_batch_size_rejected(self, tmp_path: Path):
        source = _write_zip(tmp_path, {2020: [_msg(2020, "Alice", "x")]})
        with pytest.raises(ValueError, match="batch_size"):
            embed_messages(source, tmp_path / "out", batch_size=0, client=_stub_client())

    def test_no_client_no_api_key_raises_helpfully(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        source = _write_zip(tmp_path, {2020: [_msg(2020, "Alice", "x")]})
        with pytest.raises(MissingCredentialsError, match="OPENAI_API_KEY"):
            embed_messages(source, tmp_path / "out")

    def test_batch_size_splits_calls(self, tmp_path: Path):
        source = _write_zip(tmp_path, {2020: [_msg(2020, "Alice", f"m{i}") for i in range(7)]})
        out_dir = tmp_path / "out"
        client = _stub_client()

        embed_messages(source, out_dir, window=0, batch_size=3, client=client)

        # 7 unique texts, batch 3 → 3 calls (3, 3, 1)
        sizes = [len(call.kwargs["input"]) for call in client.embeddings.create.call_args_list]
        assert sizes == [3, 3, 1]
