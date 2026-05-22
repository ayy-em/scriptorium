"""Tests for the Telegram group chat analysis pipeline."""

from collections import Counter
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from scripts.telegram._group_metrics import build_group_analytics, group_word_counts
from scripts.telegram._group_parsing import InvalidExportError, load_group_chat

USERS = {
    "user_a": "Alice",
    "user_b": "Bob",
    "user_c": "Charlie",
    "user_d": "Diana",
    "user_e": "Eve",
    "user_bot": "HelperBot",
}


def _ts(d: datetime) -> dict[str, str]:
    return {"date": d.isoformat(timespec="seconds"), "date_unixtime": str(int(d.timestamp()))}


def _msg(
    mid: int,
    when: datetime,
    sender_id: str,
    text: str,
    *,
    entities: list[dict] | None = None,
    reply_to: int | None = None,
    media_type: str | None = None,
    sticker_emoji: str | None = None,
    forwarded_from: str | None = None,
) -> dict:
    sender_name = USERS.get(sender_id, sender_id)
    entities = entities if entities is not None else [{"type": "plain", "text": text}] if text else []
    msg: dict = {
        "id": mid,
        "type": "message",
        **_ts(when),
        "from": sender_name,
        "from_id": sender_id,
        "text": text,
        "text_entities": entities,
    }
    if reply_to is not None:
        msg["reply_to_message_id"] = reply_to
    if media_type:
        msg["media_type"] = media_type
    if sticker_emoji:
        msg["sticker_emoji"] = sticker_emoji
    if forwarded_from:
        msg["forwarded_from"] = forwarded_from
    return msg


def _build_group_export(messages: list[dict], name: str = "Test Group") -> dict:
    return {"name": name, "type": "private_supergroup", "id": 999, "messages": messages}


def _write_export(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "result.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return path


# ---- Parsing tests ----


class TestGroupParsing:
    def test_load_group_chat_basic(self, tmp_path):
        base = datetime(2024, 1, 15, 10, 0)
        msgs = [
            _msg(1, base, "user_a", "Hello everyone"),
            _msg(2, base + timedelta(minutes=1), "user_b", "Hi Alice"),
            _msg(3, base + timedelta(minutes=2), "user_c", "Hey there"),
        ]
        path = _write_export(tmp_path, _build_group_export(msgs))

        metadata, messages, sender_lookup, bot_ids = load_group_chat(path)
        assert metadata.name == "Test Group"
        assert metadata.chat_type == "private_supergroup"
        assert len(messages) == 3
        assert len(sender_lookup) == 3
        assert sender_lookup["user_a"] == "Alice"
        assert not bot_ids

    def test_rejects_personal_chat(self, tmp_path):
        data = {"name": "Bob", "type": "personal_chat", "id": 123, "messages": []}
        path = _write_export(tmp_path, data)

        with pytest.raises(InvalidExportError, match="Unsupported"):
            load_group_chat(path)

    def test_skips_service_messages(self, tmp_path):
        base = datetime(2024, 1, 15, 10, 0)
        msgs = [
            _msg(1, base, "user_a", "Hello"),
            {
                "id": 2,
                "type": "service",
                **_ts(base + timedelta(minutes=1)),
                "actor": "Alice",
                "actor_id": "user_a",
                "action": "pin_message",
                "text": "",
                "text_entities": [],
            },
            _msg(3, base + timedelta(minutes=2), "user_b", "World"),
        ]
        path = _write_export(tmp_path, _build_group_export(msgs))

        _, messages, _, _ = load_group_chat(path)
        assert len(messages) == 2

    def test_extracts_reply_to(self, tmp_path):
        base = datetime(2024, 1, 15, 10, 0)
        msgs = [
            _msg(1, base, "user_a", "Original message"),
            _msg(2, base + timedelta(minutes=1), "user_b", "Reply here", reply_to=1),
        ]
        path = _write_export(tmp_path, _build_group_export(msgs))

        _, messages, _, _ = load_group_chat(path)
        assert messages[0].reply_to_message_id is None
        assert messages[1].reply_to_message_id == 1

    def test_detects_bot_ids(self, tmp_path):
        base = datetime(2024, 1, 15, 10, 0)
        msgs = [
            _msg(1, base, "user_a", "Hello"),
            _msg(2, base + timedelta(minutes=1), "user_bot", "Bot reply"),
        ]
        path = _write_export(tmp_path, _build_group_export(msgs))

        _, _, _, bot_ids = load_group_chat(path)
        assert "user_bot" in bot_ids
        assert "user_a" not in bot_ids


# ---- Metrics tests ----


def _build_test_analytics(tmp_path, msg_share_threshold=1, count_bots=True):
    """Build analytics from a synthetic group chat for testing."""
    base = datetime(2024, 6, 1, 10, 0)
    mid = 1
    msgs = []

    for i in range(20):
        msgs.append(_msg(mid, base + timedelta(hours=i), "user_a", f"Alice message {i}"))
        mid += 1

    for i in range(15):
        msgs.append(_msg(mid, base + timedelta(hours=i, minutes=30), "user_b", f"Bob message {i}", reply_to=i + 1))
        mid += 1

    for i in range(8):
        msgs.append(_msg(mid, base + timedelta(hours=i, minutes=45), "user_c", f"Charlie message {i}"))
        mid += 1

    for i in range(3):
        msgs.append(_msg(mid, base + timedelta(hours=i, minutes=50), "user_d", f"Diana message {i}"))
        mid += 1

    path = _write_export(tmp_path, _build_group_export(msgs))

    metadata, messages, sender_lookup, bot_ids = load_group_chat(path)
    return build_group_analytics(
        metadata,
        messages,
        sender_lookup,
        msg_share_threshold=msg_share_threshold,
        count_bots=count_bots,
        bot_ids=bot_ids,
        now=datetime(2024, 6, 10, 12, 0),
    )


class TestGroupMetrics:
    def test_totals(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        assert analytics["totals"]["messages_all_time"] == 46
        assert analytics["totals"]["total_members_spotted"] == 4

    def test_display_names_resolved(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        mc = analytics["user_archetypes"]["main_character"]
        assert mc["display_name"] == "Alice"

    def test_share_threshold_filter(self, tmp_path):
        analytics = _build_test_analytics(tmp_path, msg_share_threshold=20)
        active_ids = {p["id"] for p in analytics["participants"]}
        assert "user_d" not in active_ids
        assert "user_c" not in active_ids
        assert "user_a" in active_ids
        assert "user_b" in active_ids

    def test_share_sums_to_one(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        total = sum(analytics["share_by_user"].values())
        assert abs(total - 1.0) < 0.01

    def test_monthly_volume_structure(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        assert "2024" in analytics["monthly_volume"]
        assert len(analytics["monthly_volume"]["2024"]) == 12

    def test_heatmap_shape(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        matrix = analytics["activity_heatmap"]["matrix"]
        assert len(matrix) == 7
        assert all(len(row) == 24 for row in matrix)

    def test_reply_matrix_counts(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        matrix = analytics["reply_matrix"]
        assert isinstance(matrix, dict)

    def test_burst_dynamics(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        bursts = analytics["burst_dynamics"]
        assert bursts["total_bursts"] >= 1
        assert isinstance(bursts["starters"], list)
        assert isinstance(bursts["killers"], list)
        if bursts["starters"]:
            assert "user_id" in bursts["starters"][0]
            assert "rate_per_k" in bursts["starters"][0]
            assert "count" not in bursts["starters"][0]
        if bursts["killers"]:
            assert "rate_per_k" in bursts["killers"][0]
            assert "count" not in bursts["killers"][0]

    def test_profanity_structure(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        prof = analytics["profanity_analytics"]
        assert "sailor_award" in prof
        assert "classy_citizen" in prof
        assert "user_rates" in prof
        fb = prof["bilingual_firebrand"]
        assert "en_pct" in fb
        assert "ru_pct" in fb

    def test_heatmap_peak_fields(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        peak = analytics["activity_heatmap"]["peak"]
        assert "day_full" in peak
        assert peak["day_full"].endswith("s")
        assert "pct_above_avg" in peak
        assert isinstance(peak["pct_above_avg"], float)

    def test_voice_award_structure(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        va = analytics["voice_award"]
        assert "user_id" in va
        assert "avg_seconds" in va
        assert "count" in va

    def test_streaks_structure(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        streaks = analytics["streaks"]
        assert "hot_streak" in streaks
        assert "dry_spell" in streaks
        assert streaks["hot_streak"]["days"] >= 1
        assert streaks["hot_streak"]["start"] is not None

    def test_favorite_words_structure(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        fav = analytics["favorite_words"]
        assert isinstance(fav, list)

    def test_essayist_no_false_winner(self, tmp_path):
        """Essayist should be None when no messages exceed 50 words."""
        analytics = _build_test_analytics(tmp_path)
        essayist = analytics["user_archetypes"]["essayist"]
        assert essayist["user_id"] is None
        assert essayist["count"] == 0


# ---- Bot exclusion tests ----


class TestBotExclusion:
    def test_bots_excluded_by_default(self, tmp_path):
        base = datetime(2024, 6, 1, 10, 0)
        mid = 1
        msgs = []
        for i in range(10):
            msgs.append(_msg(mid, base + timedelta(hours=i), "user_a", f"Human msg {i}"))
            mid += 1
        for i in range(10):
            msgs.append(_msg(mid, base + timedelta(hours=i, minutes=10), "user_bot", f"Bot msg {i}"))
            mid += 1

        path = _write_export(tmp_path, _build_group_export(msgs))
        metadata, messages, sender_lookup, bot_ids = load_group_chat(path)

        analytics = build_group_analytics(
            metadata,
            messages,
            sender_lookup,
            msg_share_threshold=1,
            count_bots=False,
            bot_ids=bot_ids,
            now=datetime(2024, 6, 10, 12, 0),
        )
        active_ids = {p["id"] for p in analytics["participants"]}
        assert "user_bot" not in active_ids
        assert "user_a" in active_ids

    def test_bots_included_with_flag(self, tmp_path):
        base = datetime(2024, 6, 1, 10, 0)
        mid = 1
        msgs = []
        for i in range(10):
            msgs.append(_msg(mid, base + timedelta(hours=i), "user_a", f"Human msg {i}"))
            mid += 1
        for i in range(10):
            msgs.append(_msg(mid, base + timedelta(hours=i, minutes=10), "user_bot", f"Bot msg {i}"))
            mid += 1

        path = _write_export(tmp_path, _build_group_export(msgs))
        metadata, messages, sender_lookup, bot_ids = load_group_chat(path)

        analytics = build_group_analytics(
            metadata,
            messages,
            sender_lookup,
            msg_share_threshold=1,
            count_bots=True,
            bot_ids=bot_ids,
            now=datetime(2024, 6, 10, 12, 0),
        )
        active_ids = {p["id"] for p in analytics["participants"]}
        assert "user_bot" in active_ids


# ---- Archetype tests ----


class TestArchetypes:
    def test_main_character(self, tmp_path):
        analytics = _build_test_analytics(tmp_path)
        mc = analytics["user_archetypes"]["main_character"]
        assert mc["user_id"] == "user_a"

    def test_ghost_finds_inactive_below_threshold(self, tmp_path):
        """Ghost should find users below the share threshold who stopped posting."""
        mid = 1
        msgs = []
        for i in range(5):
            msgs.append(_msg(mid, datetime(2024, 1, 1, 10, 0) + timedelta(days=i), "user_d", f"Diana early {i}"))
            mid += 1
        for i in range(200):
            msgs.append(_msg(mid, datetime(2024, 5, 1, 10, 0) + timedelta(hours=i), "user_a", f"Alice msg {i}"))
            mid += 1
        for i in range(100):
            msgs.append(_msg(mid, datetime(2024, 5, 1, 12, 0) + timedelta(hours=i), "user_b", f"Bob msg {i}"))
            mid += 1

        path = _write_export(tmp_path, _build_group_export(msgs))
        metadata, messages, sender_lookup, bot_ids = load_group_chat(path)
        analytics = build_group_analytics(
            metadata,
            messages,
            sender_lookup,
            msg_share_threshold=1,
            now=datetime(2024, 5, 15, 12, 0),
        )
        ghost = analytics["user_archetypes"]["ghost"]
        assert ghost["user_id"] == "user_d"
        assert ghost["days_absent"] > 60

    def test_mr_autism_detection(self, tmp_path):
        base = datetime(2024, 6, 1, 10, 0)
        mid = 1
        msgs = []
        for i in range(10):
            msgs.append(_msg(mid, base + timedelta(minutes=i), "user_a", f"Solo message {i}"))
            mid += 1
        msgs.append(_msg(mid, base + timedelta(minutes=20), "user_b", "Finally someone responds"))
        mid += 1
        for i in range(5):
            msgs.append(_msg(mid, base + timedelta(hours=1, minutes=i), "user_b", f"Bob msg {i}"))
            mid += 1

        path = _write_export(tmp_path, _build_group_export(msgs))

        metadata, messages, sender_lookup, bot_ids = load_group_chat(path)
        analytics = build_group_analytics(
            metadata,
            messages,
            sender_lookup,
            msg_share_threshold=1,
            now=datetime(2024, 6, 10, 12, 0),
        )
        assert analytics["user_archetypes"]["mr_autism"]["user_id"] == "user_a"
        assert analytics["user_archetypes"]["mr_autism"]["streak_count"] >= 1


# ---- Word counts ----


class TestWordCounts:
    def test_group_word_counts(self, tmp_path):
        base = datetime(2024, 6, 1, 10, 0)
        msgs = [
            _msg(1, base, "user_a", "Hello world testing something interesting"),
            _msg(2, base + timedelta(minutes=1), "user_b", "Another interesting testing message here"),
        ]
        path = _write_export(tmp_path, _build_group_export(msgs))

        _, messages, _, _ = load_group_chat(path)
        counts, per_user = group_word_counts(messages, ["user_a", "user_b"])
        assert isinstance(counts, Counter)
        assert counts["testing"] == 2
        assert counts["interesting"] == 2
        assert isinstance(per_user, dict)
        assert "user_a" in per_user
        assert "user_b" in per_user


# ---- Streak tests ----


class TestStreaks:
    def test_consecutive_days_streak(self, tmp_path):
        base = datetime(2024, 6, 1, 10, 0)
        mid = 1
        msgs = []
        for day in range(7):
            msgs.append(_msg(mid, base + timedelta(days=day), "user_a", f"Day {day}"))
            mid += 1
        msgs.append(_msg(mid, base + timedelta(days=10), "user_a", "After gap"))
        mid += 1

        path = _write_export(tmp_path, _build_group_export(msgs))
        metadata, messages, sender_lookup, bot_ids = load_group_chat(path)
        analytics = build_group_analytics(
            metadata,
            messages,
            sender_lookup,
            msg_share_threshold=1,
            now=datetime(2024, 6, 20, 12, 0),
        )
        assert analytics["streaks"]["hot_streak"]["days"] == 7
        assert analytics["streaks"]["dry_spell"]["days"] == 3
