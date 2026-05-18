"""Shared synthetic-fixture builder for telegram tests.

The real reference export lives gitignored under
``tests/telegram/fixtures/chat_export/result.json``; CI relies on the synthetic
fixture built here. The fixture is materialized to disk under ``tmp_path``
per-test so the script's streaming JSON parser sees a real file, exactly as the
production path would.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

PARTNER_NAME = "Bob"
PARTNER_ID = "user2002"
SELF_NAME = "Alice"
SELF_ID = "user1001"


def _ts(d: datetime) -> dict[str, str]:
    return {"date": d.isoformat(timespec="seconds"), "date_unixtime": str(int(d.timestamp()))}


def _msg(
    mid: int,
    when: datetime,
    sender_id: str,
    sender_name: str,
    text: str,
    *,
    entities: list[dict] | None = None,
    extra: dict | None = None,
) -> dict:
    entities = entities if entities is not None else [{"type": "plain", "text": text}] if text else []
    msg = {
        "id": mid,
        "type": "message",
        **_ts(when),
        "from": sender_name,
        "from_id": sender_id,
        "text": text,
        "text_entities": entities,
    }
    if extra:
        msg.update(extra)
    return msg


def build_synthetic_chat() -> dict:
    """Return a dict identical in shape to a Telegram personal-chat export."""
    messages: list[dict] = []
    mid = 1

    def add(when: datetime, sender_id: str, sender_name: str, text: str, **kw) -> None:
        nonlocal mid
        messages.append(_msg(mid, when, sender_id, sender_name, text, **kw))
        mid += 1

    # --- 2024-01-15..22: opening run, partner sends first ---
    base = datetime(2024, 1, 15, 10, 0)
    add(base, PARTNER_ID, PARTNER_NAME, "Hello there friend")
    add(base + timedelta(minutes=2), SELF_ID, SELF_NAME, "Hi Bob, how are you")
    add(base + timedelta(minutes=10), PARTNER_ID, PARTNER_NAME, "Quite well honestly")
    add(base + timedelta(minutes=11), PARTNER_ID, PARTNER_NAME, "Double texting straight away")
    add(base + timedelta(minutes=20), SELF_ID, SELF_NAME, "Lol classic")
    add(base + timedelta(days=1, hours=2), PARTNER_ID, PARTNER_NAME, "Another day another chat")
    add(base + timedelta(days=1, hours=3), SELF_ID, SELF_NAME, "Привет, всё хорошо")
    add(base + timedelta(days=2), PARTNER_ID, PARTNER_NAME, "Going well thanks")

    # service message — should be filtered
    messages.append(
        {
            "id": mid,
            "type": "service",
            **_ts(base + timedelta(days=2, hours=1)),
            "actor": SELF_NAME,
            "actor_id": SELF_ID,
            "action": "phone_call",
        }
    )
    mid += 1

    # --- 2024-06-10..11: short conversation with a sticker and a photo ---
    summer = datetime(2024, 6, 10, 19, 30)
    add(summer, SELF_ID, SELF_NAME, "Look at this photo", extra={"photo": "photos/photo_1.jpg"})
    add(
        summer + timedelta(minutes=1),
        PARTNER_ID,
        PARTNER_NAME,
        "",
        extra={
            "media_type": "sticker",
            "sticker_emoji": "😂",
        },
    )
    add(
        summer + timedelta(minutes=5),
        SELF_ID,
        SELF_NAME,
        "Check this out https://youtube.com/watch?v=abc",
        entities=[
            {"type": "plain", "text": "Check this out "},
            {"type": "link", "text": "https://youtube.com/watch?v=abc"},
        ],
    )
    add(
        summer + timedelta(minutes=10),
        PARTNER_ID,
        PARTNER_NAME,
        "And this https://reddit.com/r/aww",
        entities=[
            {"type": "plain", "text": "And this "},
            {"type": "link", "text": "https://reddit.com/r/aww"},
        ],
    )

    # --- 2024-12-25..27: holiday burst ---
    holiday = datetime(2024, 12, 25, 9, 0)
    for i in range(5):
        add(holiday + timedelta(days=i // 3, hours=i), SELF_ID, SELF_NAME, f"Holiday vibe {i} ❤️")
        add(holiday + timedelta(days=i // 3, hours=i, minutes=5), PARTNER_ID, PARTNER_NAME, f"Merry one {i} 😂")

    # --- 2025 conversations sprinkled across the year ---
    spring = datetime(2025, 3, 14, 18, 0)
    add(
        spring,
        SELF_ID,
        SELF_NAME,
        "https://twitter.com/foo/status/1",
        entities=[{"type": "link", "text": "https://twitter.com/foo/status/1"}],
    )
    add(spring + timedelta(minutes=30), PARTNER_ID, PARTNER_NAME, "Saw it, lol")
    add(
        spring + timedelta(hours=1),
        SELF_ID,
        SELF_NAME,
        "Also https://tiktok.com/@bar/video/2",
        entities=[
            {"type": "plain", "text": "Also "},
            {"type": "link", "text": "https://tiktok.com/@bar/video/2"},
        ],
    )

    # 2025-08-01..07: hot streak (every day at least one msg)
    streak_start = datetime(2025, 8, 1, 12, 0)
    for d in range(7):
        when = streak_start + timedelta(days=d)
        add(when, SELF_ID, SELF_NAME, f"Streak day {d} reporting in ✨")
        add(when + timedelta(minutes=30), PARTNER_ID, PARTNER_NAME, f"Acknowledged day {d}")

    # 2025-08-15..09-10: silence gap (27 days, no messages)
    # 2025-09-10: short ping
    add(datetime(2025, 9, 10, 14, 0), PARTNER_ID, PARTNER_NAME, "Hey, you alive?")
    add(datetime(2025, 9, 10, 14, 30), SELF_ID, SELF_NAME, "Yes still here")

    # forwarded message
    add(
        datetime(2025, 10, 5, 22, 0),
        PARTNER_ID,
        PARTNER_NAME,
        "Forwarded clip — look",
        extra={"forwarded_from": "Some Channel"},
    )

    # --- 2026 messages: YTD ---
    ytd = datetime(2026, 1, 5, 11, 0)
    add(ytd, SELF_ID, SELF_NAME, "Happy new year Bob")
    add(ytd + timedelta(minutes=15), PARTNER_ID, PARTNER_NAME, "And to you 🎉")
    add(ytd + timedelta(days=10), SELF_ID, SELF_NAME, "Reading a book today")
    add(ytd + timedelta(days=10, minutes=10), SELF_ID, SELF_NAME, "Actually quite enjoying it")
    add(ytd + timedelta(days=10, minutes=20), SELF_ID, SELF_NAME, "Recommend strongly")
    add(ytd + timedelta(days=10, hours=2), PARTNER_ID, PARTNER_NAME, "Cool which one")

    march = datetime(2026, 3, 10, 20, 0)
    add(
        march,
        SELF_ID,
        SELF_NAME,
        "Look ❤️ here https://youtube.com/watch?v=xyz",
        entities=[
            {"type": "plain", "text": "Look ❤️ here "},
            {"type": "link", "text": "https://youtube.com/watch?v=xyz"},
        ],
    )
    add(
        march + timedelta(minutes=1),
        PARTNER_ID,
        PARTNER_NAME,
        "",
        extra={
            "media_type": "sticker",
            "sticker_emoji": "🤔",
        },
    )
    add(march + timedelta(minutes=5), SELF_ID, SELF_NAME, "Lol")

    # cross-session reply: alice messages at 10:00, bob responds at 19:00 next day
    add(datetime(2026, 4, 1, 10, 0), SELF_ID, SELF_NAME, "Hey when you free this week")
    add(datetime(2026, 4, 2, 19, 0), PARTNER_ID, PARTNER_NAME, "How about Friday")
    add(datetime(2026, 4, 2, 19, 5), SELF_ID, SELF_NAME, "Friday works")

    # recent activity
    add(datetime(2026, 5, 15, 9, 0), PARTNER_ID, PARTNER_NAME, "Did you see the news today")
    add(datetime(2026, 5, 15, 9, 10), SELF_ID, SELF_NAME, "Skimmed it")

    return {
        "name": PARTNER_NAME,
        "type": "personal_chat",
        "id": 1234567,
        "messages": messages,
    }


@pytest.fixture
def synthetic_chat_dict() -> dict:
    return build_synthetic_chat()


@pytest.fixture
def synthetic_chat_path(tmp_path: Path, synthetic_chat_dict: dict) -> Path:
    path = tmp_path / "result.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(synthetic_chat_dict, f, ensure_ascii=False)
    return path


@pytest.fixture
def make_chat_export(tmp_path: Path) -> Callable[[dict], Path]:
    """Factory for materializing custom chat-export dicts to disk."""

    def _factory(data: dict, name: str = "result.json") -> Path:
        path = tmp_path / name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return path

    return _factory


REAL_EXPORT_PATH = Path(__file__).parent / "fixtures" / "chat_export" / "result.json"


@pytest.fixture
def real_export_path() -> Path:
    if not REAL_EXPORT_PATH.exists():
        pytest.skip(f"real export not present at {REAL_EXPORT_PATH} (skipped on CI / fresh clones)")
    return REAL_EXPORT_PATH
