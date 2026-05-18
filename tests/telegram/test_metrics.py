"""Tests for scripts.telegram._metrics."""

from datetime import datetime, timedelta

from scripts.telegram._metrics import (
    _compute_double_text,
    _compute_initiation_share,
    _compute_reply_latency,
    _compute_streaks,
    _normalize_domain,
    _split_sessions,
    build_analytics,
)
from scripts.telegram._parsing import ChatMetadata, Message, Participant, load_chat

NOW = datetime(2026, 5, 19, 12, 0, 0)
SELF = "user1001"
PARTNER = "user2002"


def _msg(when: datetime, uid: str, text: str = "hi there everyone") -> Message:
    return Message(
        date=when,
        from_id=uid,
        sender_name="Alice" if uid == SELF else "Bob",
        text=text,
        text_entities=[{"type": "plain", "text": text}],
    )


def _meta() -> ChatMetadata:
    return ChatMetadata(
        name="Bob",
        chat_type="personal_chat",
        chat_id=1,
        participants=(
            Participant(SELF, "Alice", is_self=True),
            Participant(PARTNER, "Bob", is_self=False),
        ),
    )


class TestSessionDetection:
    def test_split_at_four_hour_gap(self):
        base = datetime(2025, 1, 1, 10, 0)
        msgs = [
            _msg(base, SELF),
            _msg(base + timedelta(hours=3, minutes=59), PARTNER),  # same session
            _msg(base + timedelta(hours=8, minutes=1), SELF),  # new session (>4h)
        ]
        sessions = _split_sessions(msgs)
        assert len(sessions) == 2
        assert len(sessions[0]) == 2
        assert len(sessions[1]) == 1

    def test_exactly_four_hours_is_same_session(self):
        base = datetime(2025, 1, 1, 10, 0)
        msgs = [_msg(base, SELF), _msg(base + timedelta(hours=4), PARTNER)]
        sessions = _split_sessions(msgs)
        assert len(sessions) == 1


class TestInitiationShare:
    def test_counts_session_initiators(self):
        sessions = [
            [_msg(datetime(2025, 1, 1), SELF)],
            [_msg(datetime(2025, 1, 2), PARTNER)],
            [_msg(datetime(2025, 1, 3), SELF)],
        ]
        out = _compute_initiation_share(sessions, [SELF, PARTNER])
        assert out[SELF] == round(2 / 3, 4)
        assert out[PARTNER] == round(1 / 3, 4)
        assert out["sessions_total"] == 3


class TestReplyLatency:
    def test_credits_responder_for_run_end(self):
        base = datetime(2025, 1, 1, 10, 0)
        session = [
            _msg(base, SELF),
            _msg(base + timedelta(minutes=5), SELF),
            _msg(base + timedelta(minutes=10), PARTNER),  # B replies — credit B with 5min
            _msg(base + timedelta(minutes=12), PARTNER),
            _msg(base + timedelta(minutes=20), SELF),  # A replies — credit A with 8min
        ]
        out = _compute_reply_latency([session], [SELF, PARTNER])
        assert out[PARTNER]["samples"] == 1
        assert out[PARTNER]["mean"] == 300.0
        assert out[SELF]["samples"] == 1
        assert out[SELF]["mean"] == 480.0

    def test_unreplied_run_discarded(self):
        base = datetime(2025, 1, 1, 10, 0)
        session = [
            _msg(base, SELF),
            _msg(base + timedelta(minutes=1), SELF),
        ]  # never replied
        out = _compute_reply_latency([session], [SELF, PARTNER])
        assert out[PARTNER]["samples"] == 0


class TestDoubleText:
    def test_run_of_three_yields_two_double_texts(self):
        base = datetime(2025, 1, 1, 10, 0)
        session = [
            _msg(base, SELF),
            _msg(base + timedelta(minutes=1), SELF),
            _msg(base + timedelta(minutes=2), SELF),
            _msg(base + timedelta(minutes=3), PARTNER),
        ]
        out = _compute_double_text([session], [SELF, PARTNER])
        assert out[SELF]["count"] == 2
        assert out[PARTNER]["count"] == 0
        assert out[SELF]["share"] == 1.0


class TestStreaks:
    def test_silence_gap(self):
        msgs = [
            _msg(datetime(2025, 1, 1), SELF),
            _msg(datetime(2025, 1, 11), PARTNER),  # 9-day silence (Jan 2-10)
            _msg(datetime(2025, 1, 12), SELF),
        ]
        out = _compute_streaks(msgs)
        assert out["longest_silence"]["days"] == 9
        assert out["longest_silence"]["start"] == "2025-01-02"
        assert out["longest_silence"]["end"] == "2025-01-10"

    def test_hot_streak(self):
        msgs = [_msg(datetime(2025, 1, 1) + timedelta(days=d), SELF) for d in range(5)]
        out = _compute_streaks(msgs)
        assert out["longest_streak"]["days"] == 5
        assert out["longest_streak"]["start"] == "2025-01-01"
        assert out["longest_streak"]["end"] == "2025-01-05"


class TestNormalizeDomain:
    def test_strips_www(self):
        assert _normalize_domain("https://www.youtube.com/watch?v=abc") == "youtube.com"

    def test_lowercases(self):
        assert _normalize_domain("https://Reddit.com/r/aww") == "reddit.com"

    def test_handles_missing_scheme(self):
        assert _normalize_domain("youtube.com/foo") == "youtube.com"


class TestBuildAnalytics:
    def test_full_pipeline_against_fixture(self, synthetic_chat_path):
        meta, messages = load_chat(synthetic_chat_path)
        analytics = build_analytics(meta, messages, now=NOW)

        assert analytics["schema_version"] == 1
        assert analytics["source"]["chat_name"] == "Bob"
        assert analytics["totals"]["messages_all_time"] == len(messages)
        assert analytics["totals"]["messages_ytd"] > 0
        assert analytics["totals"]["date_range"]["start"] == "2024-01-15"

        # share sums approximately to 1
        total_share = sum(analytics["share_by_user"].values())
        assert abs(total_share - 1.0) < 1e-3

        # monthly volume has the current year and at least one prior
        assert "2026" in analytics["monthly_volume"]
        assert "2024" in analytics["monthly_volume"]
        assert len(analytics["monthly_volume"]["2026"]) == 12

        # heatmap shape
        hm = analytics["activity_heatmap"]
        assert len(hm["days"]) == 7
        assert len(hm["matrix"]) == 7
        assert all(len(row) == 24 for row in hm["matrix"])
        total_cells = sum(sum(row) for row in hm["matrix"])
        assert total_cells == len(messages)

        # links picked up
        assert analytics["external_links"]["by_domain"].get("youtube.com", 0) >= 2
        assert "reddit.com" in analytics["external_links"]["by_domain"]
        assert "twitter.com" in analytics["external_links"]["by_domain"]
        assert "tiktok.com" in analytics["external_links"]["by_domain"]

        # emojis and stickers detected
        assert any(e["emoji"] == "❤️" for e in analytics["top_emojis"][SELF])
        assert any(s["sticker_emoji"] == "😂" for s in analytics["top_stickers"][PARTNER])

        # vocabulary richness ratios sit between 0 and 1
        for uid in [SELF, PARTNER]:
            ratio = analytics["vocabulary_richness"][uid]["ratio"]
            assert 0.0 <= ratio <= 1.0

        # streaks populated
        assert analytics["streaks"]["longest_silence"]["days"] > 0
        assert analytics["streaks"]["longest_streak"]["days"] > 0

        # initiation share has the sessions_total field
        assert "sessions_total" in analytics["initiation_share"]
        assert analytics["initiation_share"]["sessions_total"] > 0
