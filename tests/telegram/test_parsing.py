"""Tests for scripts.telegram._parsing."""

from datetime import datetime

import pytest

from scripts.telegram._parsing import InvalidExportError, _flatten_entities, load_chat


class TestLoadChat:
    def test_metadata_extracted(self, synthetic_chat_path):
        meta, _ = load_chat(synthetic_chat_path)
        assert meta.name == "Bob"
        assert meta.chat_type == "personal_chat"
        assert meta.chat_id == 1234567

    def test_participants_self_and_partner(self, synthetic_chat_path):
        meta, _ = load_chat(synthetic_chat_path)
        ids = {p.id for p in meta.participants}
        assert ids == {"user1001", "user2002"}
        self_p = next(p for p in meta.participants if p.is_self)
        partner_p = next(p for p in meta.participants if not p.is_self)
        assert self_p.display_name == "Alice"
        assert partner_p.display_name == "Bob"

    def test_service_messages_filtered(self, synthetic_chat_path):
        _, messages = load_chat(synthetic_chat_path)
        assert all(m.text is not None for m in messages)
        assert not any(getattr(m, "type", "message") == "service" for m in messages)

    def test_dates_parsed(self, synthetic_chat_path):
        _, messages = load_chat(synthetic_chat_path)
        assert all(isinstance(m.date, datetime) for m in messages)
        assert messages[0].date < messages[-1].date or len(messages) == 1

    def test_rejects_non_personal_chat(self, make_chat_export):
        bad = {"name": "Group", "type": "private_group", "id": 1, "messages": []}
        path = make_chat_export(bad)
        with pytest.raises(InvalidExportError, match="Unsupported chat type"):
            load_chat(path)

    def test_rejects_three_participants(self, make_chat_export):
        msgs = [
            {
                "id": i,
                "type": "message",
                "date": f"2025-01-0{i + 1}T10:00:00",
                "date_unixtime": "0",
                "from": f"User{i}",
                "from_id": f"user{i}",
                "text": "hi",
                "text_entities": [{"type": "plain", "text": "hi"}],
            }
            for i in range(3)
        ]
        bad = {"name": "User0", "type": "personal_chat", "id": 1, "messages": msgs}
        path = make_chat_export(bad)
        with pytest.raises(InvalidExportError, match="more than 2 distinct senders"):
            load_chat(path)

    def test_rejects_missing_keys(self, make_chat_export):
        bad = {"name": "Bob", "messages": []}
        path = make_chat_export(bad)
        with pytest.raises(InvalidExportError, match="missing required top-level keys"):
            load_chat(path)

    def test_participant_ids_always_come_from_messages(self, make_chat_export):
        """Regression: production bug where the second sender was silently dropped.

        Both participant IDs must come from real ``from_id`` values in messages;
        ``"unknown"`` must never appear when two distinct senders exist, even if
        the root ``name`` doesn't exactly match either display name.
        """
        msgs = [
            {
                "id": 1,
                "type": "message",
                "date": "2025-01-01T10:00:00",
                "date_unixtime": "0",
                "from": "J M",
                "from_id": "user_jm",
                "text": "hi",
                "text_entities": [{"type": "plain", "text": "hi"}],
            },
            {
                "id": 2,
                "type": "message",
                "date": "2025-01-01T10:05:00",
                "date_unixtime": "0",
                "from": "Ira Sergeevna",  # display has extra suffix vs root name "Ira"
                "from_id": "user_ira",
                "text": "hello",
                "text_entities": [{"type": "plain", "text": "hello"}],
            },
        ]
        data = {"name": "Ira", "type": "personal_chat", "id": 999, "messages": msgs}
        path = make_chat_export(data)
        meta, _ = load_chat(path)
        ids = {p.id for p in meta.participants}
        assert ids == {"user_jm", "user_ira"}
        assert "unknown" not in ids
        # Substring match picks "Ira Sergeevna" as the partner.
        partner = next(p for p in meta.participants if not p.is_self)
        assert partner.id == "user_ira"

    def test_partner_id_falls_back_to_first_sender_when_no_name_match(self, make_chat_export):
        msgs = [
            {
                "id": 1,
                "type": "message",
                "date": "2025-01-01T10:00:00",
                "date_unixtime": "0",
                "from": "Alpha",
                "from_id": "user_alpha",
                "text": "hi",
                "text_entities": [{"type": "plain", "text": "hi"}],
            },
            {
                "id": 2,
                "type": "message",
                "date": "2025-01-01T10:05:00",
                "date_unixtime": "0",
                "from": "Beta",
                "from_id": "user_beta",
                "text": "hello",
                "text_entities": [{"type": "plain", "text": "hello"}],
            },
        ]
        data = {"name": "Totally Different", "type": "personal_chat", "id": 1, "messages": msgs}
        path = make_chat_export(data)
        meta, _ = load_chat(path)
        partner = next(p for p in meta.participants if not p.is_self)
        # Fallback rule: first-appearing sender = partner.
        assert partner.id == "user_alpha"


class TestFlattenEntities:
    def test_concatenates_text_fragments(self):
        entities = [
            {"type": "plain", "text": "Hi "},
            {"type": "bold", "text": "there"},
            {"type": "plain", "text": "!"},
        ]
        assert _flatten_entities(entities) == "Hi there!"

    def test_empty(self):
        assert _flatten_entities([]) == ""
