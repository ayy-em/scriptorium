"""Compute the group_analytics dict from parsed group-chat messages."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
import re
from statistics import mean
from typing import Any

import emoji

from scripts.telegram._group_parsing import GroupMessage, GroupMetadata
from scripts.telegram._profanity_en import ENGLISH_PROFANITY
from scripts.telegram._profanity_ru import RUSSIAN_PROFANITY
from scripts.telegram._stopwords_en import ENGLISH_STOPWORDS
from scripts.telegram._stopwords_ru import RUSSIAN_STOPWORDS

SESSION_GAP = timedelta(hours=4)
WORD_RE = re.compile(r"\b\w+\b", flags=re.UNICODE)
LINK_ENTITY_TYPES = {"link", "text_link", "url"}
LONG_MESSAGE_WORD_THRESHOLD = 50
MIN_WORD_LEN = 4
MIN_TEXT_MESSAGE_CHARS = 3
GHOST_THRESHOLD_DAYS = 60
TOP_N_OPENER_WORDS = 5
TOP_N_DOMAINS = 10
MR_AUTISM_STREAK_MIN = 5
MACHINE_GUN_WINDOW_SECONDS = 10
CLASSY_CITIZEN_MIN_WORDS = 100
DEFAULT_MSG_SHARE_THRESHOLD = 1
MIDNIGHT_HOUR_END = 5
FAVORITE_WORD_MIN_COUNT = 5
FAVORITE_WORD_MIN_FREQ = 0.001
PROFANITY_WORDS = ENGLISH_PROFANITY | RUSSIAN_PROFANITY
STOPWORDS: frozenset[str] = ENGLISH_STOPWORDS | RUSSIAN_STOPWORDS


def _fill_display_names(obj: Any, lookup: dict[str, str]) -> None:
    """Walk the analytics dict and resolve every display_name from the sender lookup."""
    if isinstance(obj, dict):
        if "user_id" in obj and "display_name" in obj and obj["display_name"] is None:
            obj["display_name"] = lookup.get(obj["user_id"], obj["user_id"])
        for v in obj.values():
            _fill_display_names(v, lookup)
    elif isinstance(obj, list):
        for item in obj:
            _fill_display_names(item, lookup)


def build_group_analytics(
    metadata: GroupMetadata,
    messages: list[GroupMessage],
    sender_lookup: dict[str, str],
    *,
    msg_share_threshold: int = DEFAULT_MSG_SHARE_THRESHOLD,
    count_bots: bool = False,
    bot_ids: set[str] | None = None,
    now: datetime | None = None,
    source_file_name: str = "",
    source_sha256: str = "",
) -> dict[str, Any]:
    """Compute the full group analytics dictionary.

    Args:
        metadata: Parsed group metadata.
        messages: All parsed messages.
        sender_lookup: Mapping of user IDs to display names.
        msg_share_threshold: Minimum percentage of total messages a user must
            have sent to be included in the analysis (default: 1%).
        count_bots: If False (default), exclude detected bot accounts.
        bot_ids: Set of from_id values detected as bots.
        now: Override for the current time (used in tests).
        source_file_name: Original filename for provenance.
        source_sha256: SHA-256 of the source file for provenance.
    """
    now = now or datetime.now()
    messages = sorted(messages, key=lambda m: m.date)

    excluded_ids = (bot_ids or set()) if not count_bots else set()

    total_senders = len(sender_lookup)
    total_messages = len(messages)
    user_msg_counts = Counter(m.from_id for m in messages)
    min_count = int(total_messages * msg_share_threshold / 100)
    active_ids = [uid for uid, c in user_msg_counts.items() if c >= max(min_count, 1) and uid not in excluded_ids]
    active_set = set(active_ids)
    filtered = [m for m in messages if m.from_id in active_set]

    totals = _compute_totals(messages, filtered, total_senders, active_ids, now)
    monthly = _compute_monthly_volume(filtered, now.year)
    heatmap = _compute_heatmap(filtered)
    share = _compute_share(filtered, active_ids)

    sessions = _split_sessions(filtered)

    profanity = _compute_profanity(filtered, active_ids)
    voice_award = _compute_voice_award(filtered, active_ids)
    archetypes = _compute_archetypes(messages, filtered, active_ids, user_msg_counts, excluded_ids, now)

    msg_by_id = {m.id: m for m in filtered}
    reply_matrix = _compute_reply_matrix(filtered, active_set, msg_by_id)
    interaction_awards = _compute_interaction_awards(reply_matrix, active_ids)

    bursts = _compute_burst_dynamics(sessions, active_ids, user_msg_counts)
    sentiment_flow = _compute_sentiment_flow(filtered)
    favorite_words = _compute_favorite_words(filtered, active_ids)
    streaks = _compute_streaks(messages)

    analytics = {
        "schema_version": 1,
        "generated_at": now.replace(microsecond=0).isoformat(),
        "source": {
            "file_name": source_file_name,
            "sha256": source_sha256,
            "group_name": metadata.name,
            "chat_type": metadata.chat_type,
            "chat_id": metadata.chat_id,
            "timezone_note": (
                "Timestamps are treated as the group's local time; Telegram exports do not encode a timezone."
            ),
        },
        "participants": [{"id": uid, "display_name": sender_lookup.get(uid, uid)} for uid in active_ids],
        "totals": totals,
        "share_by_user": share,
        "monthly_volume": monthly,
        "activity_heatmap": heatmap,
        "profanity_analytics": profanity,
        "voice_award": voice_award,
        "user_archetypes": archetypes,
        "reply_matrix": {sender: dict(targets) for sender, targets in reply_matrix.items()},
        "interaction_awards": interaction_awards,
        "burst_dynamics": bursts,
        "sentiment_flow": sentiment_flow,
        "favorite_words": favorite_words,
        "streaks": streaks,
    }
    _fill_display_names(analytics, sender_lookup)
    return analytics


def _compute_totals(
    all_msgs: list[GroupMessage],
    filtered: list[GroupMessage],
    total_senders: int,
    active_ids: list[str],
    now: datetime,
) -> dict[str, Any]:
    """Vital signs for the group."""
    if not all_msgs:
        return {
            "messages_all_time": 0,
            "active_members_count": 0,
            "total_members_spotted": 0,
            "days_of_activity": 0,
        }
    first = all_msgs[0].date.date()
    last = all_msgs[-1].date.date()
    days = (last - first).days + 1
    return {
        "messages_all_time": len(all_msgs),
        "active_members_count": len(active_ids),
        "total_members_spotted": total_senders,
        "days_of_activity": days,
        "date_range": {"start": first.isoformat(), "end": last.isoformat(), "days": days},
    }


def _compute_monthly_volume(messages: list[GroupMessage], current_year: int) -> dict[str, list[int]]:
    """Per-month message counts for every year present."""
    present_years = sorted({m.date.year for m in messages})
    out: dict[str, list[int]] = {}
    for y in present_years:
        buckets = [0] * 12
        for m in messages:
            if m.date.year == y:
                buckets[m.date.month - 1] += 1
        out[str(y)] = buckets
    return out


def _compute_heatmap(messages: list[GroupMessage]) -> dict[str, Any]:
    """7x24 aggregate activity heatmap."""
    days_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days_full = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]
    matrix = [[0] * 24 for _ in range(7)]
    for m in messages:
        matrix[m.date.weekday()][m.date.hour] += 1
    peak_d, peak_h, peak_c = 0, 0, 0
    for d in range(7):
        for h in range(24):
            if matrix[d][h] > peak_c:
                peak_d, peak_h, peak_c = d, h, matrix[d][h]
    total = sum(matrix[d][h] for d in range(7) for h in range(24))
    slot_count = 7 * 24
    avg_per_slot = total / slot_count if slot_count else 0
    peak_pct_above_avg = round((peak_c - avg_per_slot) / avg_per_slot * 100, 1) if avg_per_slot else 0.0
    insomnia_total = sum(matrix[d][h] for d in range(7) for h in range(0, 7))
    insomnia_pct = round(insomnia_total / total, 4) if total else 0.0
    return {
        "days": days_short,
        "matrix": matrix,
        "peak": {
            "day": days_short[peak_d],
            "day_full": days_full[peak_d],
            "hour": peak_h,
            "count": peak_c,
            "pct_above_avg": peak_pct_above_avg,
        },
        "insomnia_pct": insomnia_pct,
    }


def _compute_share(messages: list[GroupMessage], active_ids: list[str]) -> dict[str, float]:
    """Per-user message share among active users."""
    if not messages:
        return {}
    counts = Counter(m.from_id for m in messages)
    total = sum(counts[uid] for uid in active_ids)
    return {uid: round(counts.get(uid, 0) / total, 4) if total else 0.0 for uid in active_ids}


def _split_sessions(messages: list[GroupMessage]) -> list[list[GroupMessage]]:
    """Split message stream into conversation bursts separated by SESSION_GAP."""
    if not messages:
        return []
    sessions: list[list[GroupMessage]] = []
    current: list[GroupMessage] = [messages[0]]
    for prev, curr in zip(messages, messages[1:], strict=False):
        if curr.date - prev.date > SESSION_GAP:
            sessions.append(current)
            current = []
        current.append(curr)
    if current:
        sessions.append(current)
    return sessions


def _is_text_message(m: GroupMessage) -> bool:
    return m.sticker_emoji is None and len(m.text) > MIN_TEXT_MESSAGE_CHARS


def _strip_emoji(text: str) -> str:
    return emoji.replace_emoji(text, replace="")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in WORD_RE.findall(_strip_emoji(text)) if len(t) >= MIN_WORD_LEN]


def _all_words(text: str) -> list[str]:
    """Tokenize all words (no length filter) for profanity checking."""
    return [t.lower() for t in WORD_RE.findall(_strip_emoji(text))]


# ---- Profanity ----


def _compute_profanity(messages: list[GroupMessage], active_ids: list[str]) -> dict[str, Any]:
    """Per-user profanity rates and awards."""
    user_total_words: dict[str, int] = defaultdict(int)
    user_profane_words: dict[str, int] = defaultdict(int)
    user_en_profane: dict[str, int] = defaultdict(int)
    user_ru_profane: dict[str, int] = defaultdict(int)

    active_set = set(active_ids)
    for m in messages:
        if m.from_id not in active_set:
            continue
        if not _is_text_message(m):
            continue
        if m.forwarded_from_id is not None:
            continue
        words = _all_words(m.text)
        user_total_words[m.from_id] += len(words)
        for w in words:
            if w in PROFANITY_WORDS:
                user_profane_words[m.from_id] += 1
                if w in ENGLISH_PROFANITY:
                    user_en_profane[m.from_id] += 1
                if w in RUSSIAN_PROFANITY:
                    user_ru_profane[m.from_id] += 1

    user_rates: dict[str, dict[str, Any]] = {}
    for uid in active_ids:
        total = user_total_words.get(uid, 0)
        profane = user_profane_words.get(uid, 0)
        user_rates[uid] = {
            "total_words_checked": total,
            "profane_words_found": profane,
            "profanity_percentage": round(profane / total * 100, 2) if total else 0.0,
            "en_profane": user_en_profane.get(uid, 0),
            "ru_profane": user_ru_profane.get(uid, 0),
        }

    sailor = max(
        (uid for uid in active_ids if user_total_words.get(uid, 0) > 0),
        key=lambda u: user_rates[u]["profanity_percentage"],
        default=None,
    )
    classy = min(
        (uid for uid in active_ids if user_total_words.get(uid, 0) > CLASSY_CITIZEN_MIN_WORDS),
        key=lambda u: user_rates[u]["profanity_percentage"],
        default=None,
    )

    def _bilingual_balance(uid: str) -> float:
        """Return the balance ratio (0..0.5) — higher means more even EN/RU split."""
        en = user_en_profane.get(uid, 0)
        ru = user_ru_profane.get(uid, 0)
        total = en + ru
        return min(en, ru) / total if total else 0.0

    firebrand = max(
        (uid for uid in active_ids if user_en_profane.get(uid, 0) > 0 and user_ru_profane.get(uid, 0) > 0),
        key=_bilingual_balance,
        default=None,
    )

    fb_en = user_en_profane.get(firebrand, 0) if firebrand else 0
    fb_ru = user_ru_profane.get(firebrand, 0) if firebrand else 0
    fb_total = fb_en + fb_ru

    return {
        "user_rates": user_rates,
        "sailor_award": {
            "user_id": sailor,
            "display_name": None,
            "rate": user_rates[sailor]["profanity_percentage"] if sailor else 0.0,
        },
        "classy_citizen": {
            "user_id": classy,
            "display_name": None,
            "rate": user_rates[classy]["profanity_percentage"] if classy else 0.0,
        },
        "bilingual_firebrand": {
            "user_id": firebrand,
            "display_name": None,
            "en_count": fb_en,
            "ru_count": fb_ru,
            "en_pct": round(fb_en / fb_total * 100, 1) if fb_total else 0.0,
            "ru_pct": round(fb_ru / fb_total * 100, 1) if fb_total else 0.0,
        },
    }


def _compute_voice_award(messages: list[GroupMessage], active_ids: list[str]) -> dict[str, Any]:
    """1001 Nights: user with the highest average voice memo duration."""
    active_set = set(active_ids)
    user_durations: dict[str, list[int]] = defaultdict(list)
    for m in messages:
        if m.from_id not in active_set:
            continue
        if m.media_type in ("voice_message", "video_message") and m.duration_seconds is not None:
            user_durations[m.from_id].append(m.duration_seconds)
    if not user_durations:
        return {"user_id": None, "display_name": None, "avg_seconds": 0.0, "count": 0}
    winner = max(user_durations, key=lambda u: mean(user_durations[u]))
    return {
        "user_id": winner,
        "display_name": None,
        "avg_seconds": round(mean(user_durations[winner]), 1),
        "count": len(user_durations[winner]),
    }


# ---- Archetypes ----


def _compute_archetypes(
    all_messages: list[GroupMessage],
    messages: list[GroupMessage],
    active_ids: list[str],
    all_user_counts: Counter,
    excluded_ids: set[str],
    now: datetime,
) -> dict[str, Any]:
    """Compute all 7 behavioral archetypes for Page 6."""
    active_set = set(active_ids)

    ghost = _find_ghost(all_messages, all_user_counts, excluded_ids, now)
    main_character = _find_main_character(messages, active_ids)
    town_crier = _find_town_crier(messages, active_ids)
    mr_autism = _find_mr_autism(messages, active_ids)
    midnight_marauder = _find_midnight_marauder(messages, active_ids)
    machine_gun = _find_machine_gun(messages, active_ids)
    podcaster = _find_podcaster(messages, active_ids)
    essayist = _find_essayist(messages, active_ids)

    return {
        "ghost": ghost,
        "main_character": main_character,
        "town_crier": town_crier,
        "mr_autism": mr_autism,
        "midnight_marauder": midnight_marauder,
        "machine_gun": machine_gun,
        "podcaster": podcaster,
        "essayist": essayist,
    }


def _find_ghost(
    messages: list[GroupMessage],
    all_counts: Counter,
    excluded_ids: set[str],
    now: datetime,
) -> dict[str, Any]:
    """Highest all-time count among users absent for the last GHOST_THRESHOLD_DAYS."""
    cutoff = now - timedelta(days=GHOST_THRESHOLD_DAYS)
    recent_senders = {m.from_id for m in messages if m.date >= cutoff}
    all_senders = set(all_counts.keys()) - excluded_ids
    candidates = [uid for uid in all_senders if uid not in recent_senders and all_counts.get(uid, 0) > 0]
    if not candidates:
        return {"user_id": None, "display_name": None, "all_time_count": 0, "days_absent": 0}
    winner = max(candidates, key=lambda u: all_counts.get(u, 0))
    last_msg_date = max((m.date for m in messages if m.from_id == winner), default=now)
    return {
        "user_id": winner,
        "display_name": None,
        "all_time_count": all_counts.get(winner, 0),
        "days_absent": (now - last_msg_date).days,
    }


def _find_main_character(messages: list[GroupMessage], active_ids: list[str]) -> dict[str, Any]:
    """Highest overall message share."""
    counts = Counter(m.from_id for m in messages)
    total = sum(counts[uid] for uid in active_ids)
    if not total:
        return {"user_id": None, "display_name": None, "share": 0.0, "count": 0}
    winner = max(active_ids, key=lambda u: counts.get(u, 0))
    return {
        "user_id": winner,
        "display_name": None,
        "share": round(counts[winner] / total, 4),
        "count": counts[winner],
    }


def _find_town_crier(messages: list[GroupMessage], active_ids: list[str]) -> dict[str, Any]:
    """Highest percentage of links/media relative to text messages."""
    user_text: dict[str, int] = defaultdict(int)
    user_media_link: dict[str, int] = defaultdict(int)
    active_set = set(active_ids)
    for m in messages:
        if m.from_id not in active_set:
            continue
        user_text[m.from_id] += 1
        has_link = any(e.get("type") in LINK_ENTITY_TYPES for e in m.text_entities if isinstance(e, dict))
        if m.media_type or has_link:
            user_media_link[m.from_id] += 1
    winner = max(
        (uid for uid in active_ids if user_text.get(uid, 0) > 0),
        key=lambda u: user_media_link.get(u, 0) / user_text[u],
        default=None,
    )
    if not winner:
        return {"user_id": None, "display_name": None, "pct": 0.0}
    return {
        "user_id": winner,
        "display_name": None,
        "pct": round(user_media_link.get(winner, 0) / user_text[winner] * 100, 1),
    }


def _find_mr_autism(messages: list[GroupMessage], active_ids: list[str]) -> dict[str, Any]:
    """User who most often goes on 5+ consecutive messages without anyone responding."""
    streak_counts: dict[str, int] = defaultdict(int)
    active_set = set(active_ids)

    current_sender: str | None = None
    current_run = 0
    for m in messages:
        if m.from_id not in active_set:
            current_sender = None
            current_run = 0
            continue
        if m.from_id == current_sender:
            current_run += 1
            if current_run == MR_AUTISM_STREAK_MIN:
                streak_counts[m.from_id] += 1
            elif current_run > MR_AUTISM_STREAK_MIN:
                pass  # already counted the start of this streak
        else:
            current_sender = m.from_id
            current_run = 1

    winner = max(
        (uid for uid in active_ids if streak_counts.get(uid, 0) > 0),
        key=lambda u: streak_counts[u],
        default=None,
    )
    return {
        "user_id": winner,
        "display_name": None,
        "streak_count": streak_counts.get(winner, 0) if winner else 0,
    }


def _find_midnight_marauder(messages: list[GroupMessage], active_ids: list[str]) -> dict[str, Any]:
    """Highest percentage of messages sent between 00:00 and 04:59."""
    user_total: dict[str, int] = defaultdict(int)
    user_night: dict[str, int] = defaultdict(int)
    active_set = set(active_ids)
    for m in messages:
        if m.from_id not in active_set:
            continue
        user_total[m.from_id] += 1
        if 0 <= m.date.hour < MIDNIGHT_HOUR_END:
            user_night[m.from_id] += 1
    winner = max(
        (uid for uid in active_ids if user_total.get(uid, 0) > 0),
        key=lambda u: user_night.get(u, 0) / user_total[u],
        default=None,
    )
    if not winner:
        return {"user_id": None, "display_name": None, "pct": 0.0}
    return {
        "user_id": winner,
        "display_name": None,
        "pct": round(user_night.get(winner, 0) / user_total[winner] * 100, 1),
    }


def _find_machine_gun(messages: list[GroupMessage], active_ids: list[str]) -> dict[str, Any]:
    """Lowest avg char count × highest rapid-fire sequences, combined via multiplied rankings."""
    user_char_lengths: dict[str, list[int]] = defaultdict(list)
    user_rapid_sequences: dict[str, int] = defaultdict(int)
    active_set = set(active_ids)

    prev_msg: GroupMessage | None = None
    for m in messages:
        if m.from_id not in active_set:
            prev_msg = m
            continue
        if _is_text_message(m):
            user_char_lengths[m.from_id].append(len(m.text))
        if (
            prev_msg
            and prev_msg.from_id == m.from_id
            and prev_msg.from_id in active_set
            and (m.date - prev_msg.date).total_seconds() <= MACHINE_GUN_WINDOW_SECONDS
        ):
            user_rapid_sequences[m.from_id] += 1
        prev_msg = m

    candidates = [uid for uid in active_ids if user_char_lengths.get(uid) and user_rapid_sequences.get(uid, 0) > 0]
    if not candidates:
        return {"user_id": None, "display_name": None, "avg_chars": 0.0, "rapid_count": 0}

    avg_chars = {uid: mean(user_char_lengths[uid]) for uid in candidates}
    char_rank = _rank_ascending(candidates, lambda u: avg_chars[u])
    rapid_rank = _rank_descending(candidates, lambda u: user_rapid_sequences.get(u, 0))

    combined = {uid: char_rank[uid] * rapid_rank[uid] for uid in candidates}
    winner = min(combined, key=combined.get)
    return {
        "user_id": winner,
        "display_name": None,
        "avg_chars": round(avg_chars[winner], 1),
        "rapid_count": user_rapid_sequences.get(winner, 0),
    }


def _find_podcaster(messages: list[GroupMessage], active_ids: list[str]) -> dict[str, Any]:
    """Highest percentage of voice/video messages."""
    user_total: dict[str, int] = defaultdict(int)
    user_voice: dict[str, int] = defaultdict(int)
    active_set = set(active_ids)
    for m in messages:
        if m.from_id not in active_set:
            continue
        user_total[m.from_id] += 1
        if m.media_type in ("voice_message", "video_message"):
            user_voice[m.from_id] += 1
    winner = max(
        (uid for uid in active_ids if user_voice.get(uid, 0) > 0),
        key=lambda u: user_voice[u] / user_total[u],
        default=None,
    )
    if not winner:
        return {"user_id": None, "display_name": None, "pct": 0.0, "count": 0}
    return {
        "user_id": winner,
        "display_name": None,
        "pct": round(user_voice[winner] / user_total[winner] * 100, 1),
        "count": user_voice[winner],
    }


def _find_essayist(messages: list[GroupMessage], active_ids: list[str]) -> dict[str, Any]:
    """Highest density of messages crossing the 50-word threshold."""
    user_total: dict[str, int] = defaultdict(int)
    user_long: dict[str, int] = defaultdict(int)
    active_set = set(active_ids)
    for m in messages:
        if m.from_id not in active_set or not _is_text_message(m):
            continue
        if m.forwarded_from_id is not None:
            continue
        user_total[m.from_id] += 1
        if len(WORD_RE.findall(m.text)) > LONG_MESSAGE_WORD_THRESHOLD:
            user_long[m.from_id] += 1
    candidates = [uid for uid in active_ids if user_long.get(uid, 0) > 0]
    if not candidates:
        return {"user_id": None, "display_name": None, "pct": 0.0, "count": 0}
    winner = max(candidates, key=lambda u: user_long[u] / user_total[u])
    return {
        "user_id": winner,
        "display_name": None,
        "pct": round(user_long[winner] / user_total[winner] * 100, 1),
        "count": user_long[winner],
    }


def _rank_ascending(items: list[str], key_fn) -> dict[str, int]:
    """Rank items 1..N by key_fn ascending (lowest value = rank 1)."""
    ordered = sorted(items, key=key_fn)
    return {uid: rank + 1 for rank, uid in enumerate(ordered)}


def _rank_descending(items: list[str], key_fn) -> dict[str, int]:
    """Rank items 1..N by key_fn descending (highest value = rank 1)."""
    ordered = sorted(items, key=key_fn, reverse=True)
    return {uid: rank + 1 for rank, uid in enumerate(ordered)}


# ---- Reply matrix & interaction awards ----


def _compute_reply_matrix(
    messages: list[GroupMessage],
    active_set: set[str],
    msg_by_id: dict[int, GroupMessage],
) -> dict[str, Counter[str]]:
    """Build reply_matrix[sender][recipient] = count."""
    matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for m in messages:
        if m.reply_to_message_id is None or m.from_id not in active_set:
            continue
        original = msg_by_id.get(m.reply_to_message_id)
        if original is None or original.from_id not in active_set:
            continue
        if m.from_id == original.from_id:
            continue
        matrix[m.from_id][original.from_id] += 1
    return matrix


def _compute_interaction_awards(
    reply_matrix: dict[str, Counter[str]],
    active_ids: list[str],
) -> dict[str, Any]:
    """The Instigator and Echo Chamber awards from the reply network."""
    replies_received: Counter[str] = Counter()
    unique_repliers: dict[str, set[str]] = defaultdict(set)
    for sender, targets in reply_matrix.items():
        for recipient, count in targets.items():
            replies_received[recipient] += count
            unique_repliers[recipient].add(sender)

    instigator = max(
        (uid for uid in active_ids if uid in unique_repliers),
        key=lambda u: len(unique_repliers[u]),
        default=None,
    )

    user_total_replies: Counter[str] = Counter()
    for sender, targets in reply_matrix.items():
        user_total_replies[sender] += sum(targets.values())

    best_pair = None
    best_mutual_pct = 0.0
    active_set = set(active_ids)
    for a in active_ids:
        for b in active_ids:
            if a >= b:
                continue
            a_to_b = reply_matrix.get(a, Counter()).get(b, 0)
            b_to_a = reply_matrix.get(b, Counter()).get(a, 0)
            if a_to_b == 0 or b_to_a == 0:
                continue
            total_a = user_total_replies.get(a, 0)
            total_b = user_total_replies.get(b, 0)
            if total_a == 0 or total_b == 0:
                continue
            pct_a = a_to_b / total_a
            pct_b = b_to_a / total_b
            mutual_pct = (pct_a + pct_b) / 2
            if mutual_pct > best_mutual_pct:
                best_mutual_pct = mutual_pct
                best_pair = (a, b)

    return {
        "instigator": {
            "user_id": instigator,
            "display_name": None,
            "unique_repliers": len(unique_repliers.get(instigator, set())) if instigator else 0,
            "total_replies_received": replies_received.get(instigator, 0) if instigator else 0,
        },
        "echo_chamber": {
            "user_a": best_pair[0] if best_pair else None,
            "user_b": best_pair[1] if best_pair else None,
            "display_name_a": None,
            "display_name_b": None,
            "mutual_pct": round(best_mutual_pct * 100, 1),
        },
    }


# ---- Burst dynamics ----


def _compute_burst_dynamics(
    sessions: list[list[GroupMessage]],
    active_ids: list[str],
    user_msg_counts: Counter,
) -> dict[str, Any]:
    """Who starts and kills conversation bursts, ranked by per-message rate."""
    active_set = set(active_ids)
    starters: Counter[str] = Counter()
    killers: Counter[str] = Counter()
    starter_words: dict[str, Counter[str]] = defaultdict(Counter)

    for session in sessions:
        first = session[0]
        last = session[-1]
        if first.from_id in active_set:
            starters[first.from_id] += 1
            for tok in _tokenize(first.text):
                if tok not in STOPWORDS:
                    starter_words[first.from_id][tok] += 1
        if last.from_id in active_set:
            killers[last.from_id] += 1

    total = len(sessions)

    def _rate(uid: str, count: int) -> float:
        user_total = user_msg_counts.get(uid, 0)
        return count / user_total if user_total else 0.0

    top_starters = sorted(starters.items(), key=lambda x: _rate(x[0], x[1]), reverse=True)[:5]
    top_killers = sorted(killers.items(), key=lambda x: _rate(x[0], x[1]), reverse=True)[:5]

    return {
        "total_bursts": total,
        "starters": [
            {
                "user_id": uid,
                "count": count,
                "pct": round(count / total * 100, 1) if total else 0.0,
                "rate_per_k": round(_rate(uid, count) * 1000, 1),
                "top_words": [{"word": w, "count": c} for w, c in starter_words.get(uid, Counter()).most_common(3)],
            }
            for uid, count in top_starters
        ],
        "killers": [
            {
                "user_id": uid,
                "count": count,
                "pct": round(count / total * 100, 1) if total else 0.0,
                "rate_per_k": round(_rate(uid, count) * 1000, 1),
            }
            for uid, count in top_killers
        ],
    }


# ---- Sentiment flow ----


def _compute_sentiment_flow(messages: list[GroupMessage]) -> dict[str, dict[str, float]]:
    """Monthly (avg text length x message count) as a group engagement metric."""
    monthly_word_totals: dict[str, int] = defaultdict(int)
    monthly_msg_counts: dict[str, int] = defaultdict(int)

    for m in messages:
        if not _is_text_message(m):
            continue
        key = f"{m.date.year}-{m.date.month:02d}"
        word_count = len(WORD_RE.findall(m.text))
        monthly_word_totals[key] += word_count
        monthly_msg_counts[key] += 1

    result: dict[str, dict[str, float]] = {}
    for key in sorted(monthly_word_totals.keys()):
        count = monthly_msg_counts[key]
        avg_len = monthly_word_totals[key] / count if count else 0.0
        result[key] = {
            "avg_text_length": round(avg_len, 2),
            "message_count": count,
            "engagement_score": round(avg_len * count, 1),
        }
    return result


# ---- Favorite words ----


def _compute_favorite_words(
    messages: list[GroupMessage],
    active_ids: list[str],
) -> list[dict[str, Any]]:
    """Top-3 'signature words' per user — words they use disproportionately more than the group.

    Returns a list of ``{"user_id", "display_name", "words": [{"word", "count", "uniqueness"}]}``.
    """
    active_set = set(active_ids)
    user_word_counts: dict[str, Counter[str]] = defaultdict(Counter)
    user_total_words: dict[str, int] = defaultdict(int)
    global_word_counts: Counter[str] = Counter()

    for m in messages:
        if m.from_id not in active_set or not _is_text_message(m):
            continue
        if m.forwarded_from_id is not None:
            continue
        tokens = _tokenize(m.text)
        for tok in tokens:
            if tok not in STOPWORDS:
                user_word_counts[m.from_id][tok] += 1
                global_word_counts[tok] += 1
                user_total_words[m.from_id] += 1

    global_total = sum(global_word_counts.values()) or 1
    result: list[dict[str, Any]] = []

    for uid in active_ids:
        u_total = user_total_words.get(uid, 0)
        if u_total == 0:
            continue
        min_count = max(FAVORITE_WORD_MIN_COUNT, int(u_total * FAVORITE_WORD_MIN_FREQ))
        scored: list[tuple[str, float, int]] = []
        for word, count in user_word_counts[uid].items():
            if count < min_count:
                continue
            user_freq = count / u_total
            global_freq = global_word_counts[word] / global_total
            uniqueness = user_freq / global_freq if global_freq > 0 else 0.0
            scored.append((word, uniqueness, count))
        scored.sort(key=lambda t: t[1], reverse=True)
        top3 = scored[:3]
        if top3:
            result.append(
                {
                    "user_id": uid,
                    "display_name": None,
                    "words": [{"word": w, "count": c, "uniqueness": round(u, 1)} for w, u, c in top3],
                }
            )

    result.sort(key=lambda r: r["words"][0]["uniqueness"] if r["words"] else 0, reverse=True)
    return result


# ---- Streaks ----


def _compute_streaks(messages: list[GroupMessage]) -> dict[str, Any]:
    """Longest consecutive-day activity streak and longest dry spell."""
    if not messages:
        return {
            "hot_streak": {"days": 0, "start": None, "end": None},
            "dry_spell": {"days": 0, "start": None, "end": None},
        }

    active_dates = sorted({m.date.date() for m in messages})

    best_streak_len = 1
    best_streak_start = active_dates[0]
    best_streak_end = active_dates[0]
    cur_start = active_dates[0]
    cur_len = 1

    for prev, curr in zip(active_dates, active_dates[1:], strict=False):
        if (curr - prev).days == 1:
            cur_len += 1
        else:
            if cur_len > best_streak_len:
                best_streak_len = cur_len
                best_streak_start = cur_start
                best_streak_end = prev
            cur_start = curr
            cur_len = 1
    if cur_len > best_streak_len:
        best_streak_len = cur_len
        best_streak_start = cur_start
        best_streak_end = active_dates[-1]

    best_gap_days = 0
    best_gap_start = active_dates[0]
    best_gap_end = active_dates[0]
    for prev, curr in zip(active_dates, active_dates[1:], strict=False):
        gap = (curr - prev).days - 1
        if gap > best_gap_days:
            best_gap_days = gap
            best_gap_start = prev
            best_gap_end = curr

    return {
        "hot_streak": {
            "days": best_streak_len,
            "start": best_streak_start.isoformat(),
            "end": best_streak_end.isoformat(),
        },
        "dry_spell": {
            "days": best_gap_days,
            "start": best_gap_start.isoformat() if best_gap_days > 0 else None,
            "end": best_gap_end.isoformat() if best_gap_days > 0 else None,
        },
    }


# ---- Word counts (for word cloud) ----


def group_word_counts(
    messages: list[GroupMessage],
    active_ids: list[str],
) -> tuple[Counter[str], dict[str, Counter[str]]]:
    """Global and per-user token frequencies for the word cloud (stopwords removed).

    Returns:
        Tuple of (global_counts, per_user_counts).
    """
    active_set = set(active_ids)
    counts: Counter[str] = Counter()
    per_user: dict[str, Counter[str]] = defaultdict(Counter)
    for m in messages:
        if m.from_id not in active_set or not _is_text_message(m):
            continue
        for tok in _tokenize(m.text):
            if tok not in STOPWORDS:
                counts[tok] += 1
                per_user[m.from_id][tok] += 1
    return counts, dict(per_user)
