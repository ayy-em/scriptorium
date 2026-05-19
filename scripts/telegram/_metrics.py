"""Compute the chat_analytics dict from parsed messages."""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import re
from statistics import mean, median
from typing import Any
from urllib.parse import urlparse

import emoji

from scripts.telegram._parsing import ChatMetadata, Message
from scripts.telegram._stopwords_en import ENGLISH_STOPWORDS
from scripts.telegram._stopwords_ru import RUSSIAN_STOPWORDS

SESSION_GAP = timedelta(hours=4)
WORD_RE = re.compile(r"\b\w+\b", flags=re.UNICODE)
LINK_ENTITY_TYPES = {"link", "text_link", "url"}
TOP_N_EMOJIS = 20
TOP_N_STICKERS = 20
TOP_N_DOMAINS = 10
TOP_N_OPENER_WORDS = 5
LONG_MESSAGE_WORD_THRESHOLD = 50
MIN_WORD_LEN = 4
# Flattened text must be longer than this to count in length/vocab metrics —
# weeds out stickers, one-letter reactions, and other noise.
MIN_TEXT_MESSAGE_CHARS = 3
# A session needs at least one initiator + one responder to yield a reply sample.
MIN_SESSION_LEN_FOR_REPLY = 2
STOPWORDS: frozenset[str] = ENGLISH_STOPWORDS | RUSSIAN_STOPWORDS


def build_analytics(
    metadata: ChatMetadata,
    messages: list[Message],
    *,
    now: datetime | None = None,
    source_file_name: str = "",
    source_sha256: str = "",
) -> dict[str, Any]:
    """Compute the full analytics dictionary matching the chat_analytics.json schema."""
    now = now or datetime.now()
    messages = sorted(messages, key=lambda m: m.date)

    participants = metadata.participants
    self_p = next((p for p in participants if p.is_self), None)
    partner_p = next((p for p in participants if not p.is_self), None)
    user_ids: list[str] = [p.id for p in (self_p, partner_p) if p is not None]

    totals = _compute_totals(messages, now)
    share = _compute_share(messages, user_ids)
    monthly = _compute_monthly_volume(messages, now.year)
    monthly_avg = _compute_avg_per_month(messages, user_ids)
    heatmap = _compute_heatmap(messages)

    sessions = _split_sessions(messages)
    initiation = _compute_initiation_share(sessions, user_ids)
    reply_latency = _compute_reply_latency(sessions, user_ids)
    double_text = _compute_double_text(sessions, user_ids)

    length_stats = _compute_message_length(messages, user_ids)
    long_msg = _compute_long_message_share(messages, user_ids)
    vocab = _compute_vocab_richness(messages, user_ids)
    streaks = _compute_streaks(messages)
    links = _compute_external_links(messages, user_ids)
    top_emojis = _compute_top_emojis(messages, user_ids)
    top_stickers = _compute_top_stickers(messages, user_ids)
    opener_words = _compute_session_opener_words(sessions, user_ids)

    return {
        "schema_version": 1,
        "generated_at": now.replace(microsecond=0).isoformat(),
        "source": {
            "file_name": source_file_name,
            "sha256": source_sha256,
            "chat_name": metadata.name,
            "chat_type": metadata.chat_type,
            "chat_id": metadata.chat_id,
            "timezone_note": (
                "Timestamps are treated as the chat's local time; Telegram exports do not encode a timezone."
            ),
        },
        "participants": [{"id": p.id, "display_name": p.display_name, "is_self": p.is_self} for p in participants],
        "totals": totals,
        "share_by_user": share,
        "monthly_volume": monthly,
        "avg_messages_per_month_by_user": monthly_avg,
        "activity_heatmap": heatmap,
        "initiation_share": initiation,
        "median_message_length": length_stats,
        "long_message_share": long_msg,
        "reply_latency_seconds": reply_latency,
        "double_text_rate": double_text,
        "vocabulary_richness": vocab,
        "streaks": streaks,
        "external_links": links,
        "top_emojis": top_emojis,
        "top_stickers": top_stickers,
        "session_opener_words": opener_words,
    }


def _compute_totals(messages: list[Message], now: datetime) -> dict[str, Any]:
    if not messages:
        return {
            "messages_all_time": 0,
            "messages_ytd": 0,
            "avg_messages_per_day": 0.0,
            "date_range": {"start": None, "end": None, "days": 0},
        }
    first = messages[0].date.date()
    last = messages[-1].date.date()
    days = (last - first).days + 1
    ytd = sum(1 for m in messages if m.date.year == now.year)
    return {
        "messages_all_time": len(messages),
        "messages_ytd": ytd,
        "avg_messages_per_day": round(len(messages) / days, 2),
        "date_range": {"start": first.isoformat(), "end": last.isoformat(), "days": days},
    }


def _compute_share(messages: list[Message], user_ids: list[str]) -> dict[str, float]:
    if not messages:
        return {uid: 0.0 for uid in user_ids}
    counts = Counter(m.from_id for m in messages)
    total = sum(counts.values())
    return {uid: round(counts.get(uid, 0) / total, 4) for uid in user_ids}


def _compute_monthly_volume(messages: list[Message], current_year: int) -> dict[str, list[int]]:
    years = [current_year - 2, current_year - 1, current_year]
    present_years = {m.date.year for m in messages}
    out: dict[str, list[int]] = {}
    for y in years:
        if y not in present_years:
            continue
        buckets = [0] * 12
        for m in messages:
            if m.date.year == y:
                buckets[m.date.month - 1] += 1
        out[str(y)] = buckets
    return out


def _compute_avg_per_month(messages: list[Message], user_ids: list[str]) -> dict[str, float]:
    if not messages:
        return {uid: 0.0 for uid in user_ids}
    by_user_month: dict[str, set[tuple[int, int]]] = defaultdict(set)
    counts: dict[str, int] = defaultdict(int)
    months_present: set[tuple[int, int]] = set()
    for m in messages:
        key = (m.date.year, m.date.month)
        months_present.add(key)
        by_user_month[m.from_id].add(key)
        counts[m.from_id] += 1
    span = max(1, len(months_present))
    return {uid: round(counts.get(uid, 0) / span, 2) for uid in user_ids}


def _compute_heatmap(messages: list[Message]) -> dict[str, Any]:
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    matrix = [[0] * 24 for _ in range(7)]
    for m in messages:
        matrix[m.date.weekday()][m.date.hour] += 1
    peak_d, peak_h, peak_c = 0, 0, 0
    for d in range(7):
        for h in range(24):
            if matrix[d][h] > peak_c:
                peak_d, peak_h, peak_c = d, h, matrix[d][h]
    peak = {"day": days[peak_d], "hour": peak_h, "count": peak_c}
    return {"days": days, "matrix": matrix, "peak": peak}


def _split_sessions(messages: list[Message]) -> list[list[Message]]:
    if not messages:
        return []
    sessions: list[list[Message]] = []
    current: list[Message] = [messages[0]]
    for prev, curr in zip(messages, messages[1:], strict=False):
        if curr.date - prev.date > SESSION_GAP:
            sessions.append(current)
            current = []
        current.append(curr)
    if current:
        sessions.append(current)
    return sessions


def _compute_initiation_share(sessions: list[list[Message]], user_ids: list[str]) -> dict[str, Any]:
    counts = Counter(s[0].from_id for s in sessions)
    total = sum(counts.values())
    out: dict[str, Any] = {uid: round(counts.get(uid, 0) / total, 4) if total else 0.0 for uid in user_ids}
    out["sessions_total"] = total
    return out


def _compute_reply_latency(sessions: list[list[Message]], user_ids: list[str]) -> dict[str, dict[str, float]]:
    """One reply-latency sample per session that received a response.

    For each session: time(first message from the other user) − time(the last
    consecutive message in the initiator's opening run). The gap is credited to
    the responder. Sessions where the initiator is never replied to are
    discarded.
    """
    latencies: dict[str, list[float]] = defaultdict(list)
    for session in sessions:
        if len(session) < MIN_SESSION_LEN_FOR_REPLY:
            continue
        initiator = session[0].from_id
        # Find the first message NOT from the initiator.
        response_idx = next((i for i, m in enumerate(session) if m.from_id != initiator), None)
        if response_idx is None:
            continue  # initiator monologued the whole session — no reply to credit
        last_initial_run_msg = session[response_idx - 1]
        first_response = session[response_idx]
        gap = (first_response.date - last_initial_run_msg.date).total_seconds()
        latencies[first_response.from_id].append(gap)
    out: dict[str, dict[str, float]] = {}
    for uid in user_ids:
        samples = latencies.get(uid, [])
        if not samples:
            out[uid] = {"mean": 0.0, "median": 0.0, "p90": 0.0, "samples": 0}
            continue
        samples_sorted = sorted(samples)
        last = len(samples_sorted) - 1
        p90 = samples_sorted[min(last, int(len(samples_sorted) * 0.9))]
        p95 = samples_sorted[min(last, int(len(samples_sorted) * 0.95))]
        out[uid] = {
            "mean": round(mean(samples), 1),
            "median": round(median(samples), 1),
            "p90": round(p90, 1),
            "p95": round(p95, 1),
            "samples": len(samples),
        }
    return out


def _compute_double_text(sessions: list[list[Message]], user_ids: list[str]) -> dict[str, dict[str, float]]:
    """Cross-session double-texts.

    A double-text occurs when the same user sends the last message of session
    N-1 *and* initiates session N — i.e. they followed up across a >4h gap
    without receiving a reply. Each such session boundary adds one double-text
    for the repeating user.
    """
    counts: dict[str, int] = defaultdict(int)
    for prev, cur in zip(sessions, sessions[1:], strict=False):
        if prev[-1].from_id == cur[0].from_id:
            counts[cur[0].from_id] += 1
    total = sum(counts.values())
    return {
        uid: {
            "count": counts.get(uid, 0),
            "share": round(counts.get(uid, 0) / total, 4) if total else 0.0,
        }
        for uid in user_ids
    }


def _is_text_message(m: Message) -> bool:
    return m.sticker_emoji is None and len(m.text) > MIN_TEXT_MESSAGE_CHARS


def _strip_emoji(text: str) -> str:
    return emoji.replace_emoji(text, replace="")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in WORD_RE.findall(_strip_emoji(text)) if len(t) >= MIN_WORD_LEN]


def _compute_message_length(messages: list[Message], user_ids: list[str]) -> dict[str, dict[str, Any]]:
    by_user_chars: dict[str, list[int]] = defaultdict(list)
    by_user_words: dict[str, list[int]] = defaultdict(list)
    for m in messages:
        if not _is_text_message(m):
            continue
        by_user_chars[m.from_id].append(len(m.text))
        by_user_words[m.from_id].append(len(WORD_RE.findall(m.text)))
    out: dict[str, dict[str, Any]] = {}
    for uid in user_ids:
        chars = by_user_chars.get(uid, [])
        words = by_user_words.get(uid, [])
        out[uid] = {
            "chars": int(round(median(chars))) if chars else 0,
            "words": int(round(median(words))) if words else 0,
            "mean_words": round(mean(words), 2) if words else 0.0,
        }
    return out


def _compute_long_message_share(messages: list[Message], user_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Fraction of each user's text messages with >50 words, excluding forwards."""
    by_user_total: dict[str, int] = defaultdict(int)
    by_user_long: dict[str, int] = defaultdict(int)
    for m in messages:
        if not _is_text_message(m):
            continue
        if m.forwarded_from_id is not None:
            continue
        by_user_total[m.from_id] += 1
        if len(WORD_RE.findall(m.text)) > LONG_MESSAGE_WORD_THRESHOLD:
            by_user_long[m.from_id] += 1
    out: dict[str, dict[str, Any]] = {}
    for uid in user_ids:
        total = by_user_total.get(uid, 0)
        count = by_user_long.get(uid, 0)
        out[uid] = {
            "count": count,
            "total": total,
            "share": round(count / total, 4) if total else 0.0,
        }
    return out


def _compute_session_opener_words(
    sessions: list[list[Message]], user_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Top words used to open a session, per user and combined.

    A "session opener" is the first message of each session, regardless of
    whether the other side ever replied. Stopwords + short words are filtered
    the same way as the word cloud.
    """
    by_user: dict[str, Counter[str]] = {uid: Counter() for uid in user_ids}
    combined: Counter[str] = Counter()
    for s in sessions:
        opener = s[0]
        for tok in _tokenize(opener.text):
            if tok in STOPWORDS:
                continue
            combined[tok] += 1
            if opener.from_id in by_user:
                by_user[opener.from_id][tok] += 1
    out: dict[str, list[dict[str, Any]]] = {}
    for uid in user_ids:
        out[uid] = [{"word": w, "count": c} for w, c in by_user[uid].most_common(TOP_N_OPENER_WORDS)]
    out["combined"] = [{"word": w, "count": c} for w, c in combined.most_common(TOP_N_OPENER_WORDS)]
    return out


def _compute_vocab_richness(messages: list[Message], user_ids: list[str]) -> dict[str, dict[str, Any]]:
    by_user: dict[str, list[str]] = defaultdict(list)
    for m in messages:
        if not _is_text_message(m):
            continue
        by_user[m.from_id].extend(_tokenize(m.text))
    out: dict[str, dict[str, Any]] = {}
    for uid in user_ids:
        tokens = by_user.get(uid, [])
        total = len(tokens)
        unique = len(set(tokens))
        out[uid] = {
            "unique": unique,
            "total": total,
            "ratio": round(unique / total, 4) if total else 0.0,
        }
    return out


def _compute_streaks(messages: list[Message]) -> dict[str, Any]:
    if not messages:
        empty = {"start": None, "end": None, "days": 0}
        return {"longest_silence": empty, "longest_streak": empty}
    dates_with_msgs: set[date] = {m.date.date() for m in messages}
    first = messages[0].date.date()
    last = messages[-1].date.date()

    longest_silence = {"start": None, "end": None, "days": 0}
    longest_streak = {"start": None, "end": None, "days": 0}
    cur_silence_start: date | None = None
    cur_streak_start: date | None = None
    d = first
    while d <= last:
        has_msg = d in dates_with_msgs
        if has_msg:
            if cur_silence_start is not None:
                days = (d - cur_silence_start).days
                if days > longest_silence["days"]:
                    longest_silence = {
                        "start": cur_silence_start.isoformat(),
                        "end": (d - timedelta(days=1)).isoformat(),
                        "days": days,
                    }
                cur_silence_start = None
            if cur_streak_start is None:
                cur_streak_start = d
        else:
            if cur_streak_start is not None:
                days = (d - cur_streak_start).days
                if days > longest_streak["days"]:
                    longest_streak = {
                        "start": cur_streak_start.isoformat(),
                        "end": (d - timedelta(days=1)).isoformat(),
                        "days": days,
                    }
                cur_streak_start = None
            if cur_silence_start is None:
                cur_silence_start = d
        d += timedelta(days=1)
    if cur_streak_start is not None:
        days = (last - cur_streak_start).days + 1
        if days > longest_streak["days"]:
            longest_streak = {
                "start": cur_streak_start.isoformat(),
                "end": last.isoformat(),
                "days": days,
            }
    return {"longest_silence": longest_silence, "longest_streak": longest_streak}


def _iter_links(m: Message) -> list[str]:
    urls: list[str] = []
    for e in m.text_entities:
        if not isinstance(e, dict):
            continue
        etype = e.get("type")
        if etype not in LINK_ENTITY_TYPES:
            continue
        if etype == "text_link":
            url = e.get("href") or e.get("text") or ""
        else:
            url = e.get("text") or ""
        if url:
            urls.append(str(url))
    return urls


def _normalize_domain(url: str) -> str | None:
    try:
        parsed = urlparse(url if "://" in url else f"http://{url}")
    except ValueError:
        return None
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def _compute_external_links(messages: list[Message], user_ids: list[str]) -> dict[str, Any]:
    by_user: dict[str, int] = defaultdict(int)
    by_domain: Counter[str] = Counter()
    for m in messages:
        for url in _iter_links(m):
            domain = _normalize_domain(url)
            if domain is None:
                continue
            by_user[m.from_id] += 1
            by_domain[domain] += 1
    top = by_domain.most_common(TOP_N_DOMAINS)
    top_dict: dict[str, int] = {d: c for d, c in top}
    other = sum(c for d, c in by_domain.items() if d not in top_dict)
    if other:
        top_dict["other"] = other
    return {
        "by_user": {uid: by_user.get(uid, 0) for uid in user_ids},
        "by_domain": top_dict,
    }


def _compute_top_emojis(messages: list[Message], user_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    per_user: dict[str, Counter[str]] = defaultdict(Counter)
    for m in messages:
        if not m.text:
            continue
        for entry in emoji.emoji_list(m.text):
            per_user[m.from_id][entry["emoji"]] += 1
    out: dict[str, list[dict[str, Any]]] = {}
    for uid in user_ids:
        out[uid] = [{"emoji": e, "count": c} for e, c in per_user.get(uid, Counter()).most_common(TOP_N_EMOJIS)]
    return out


def _compute_top_stickers(messages: list[Message], user_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    per_user: dict[str, Counter[str]] = defaultdict(Counter)
    for m in messages:
        if m.sticker_emoji:
            per_user[m.from_id][m.sticker_emoji] += 1
    out: dict[str, list[dict[str, Any]]] = {}
    for uid in user_ids:
        out[uid] = [
            {"sticker_emoji": e, "count": c} for e, c in per_user.get(uid, Counter()).most_common(TOP_N_STICKERS)
        ]
    return out


def per_user_word_counts(messages: list[Message], user_ids: list[str]) -> dict[str, Counter[str]]:
    """Token frequency per user (lowercased, length-filtered, stopwords removed).

    Used by the word-cloud renderer; lives here so the filtering rule is shared.
    """
    out: dict[str, Counter[str]] = {uid: Counter() for uid in user_ids}
    for m in messages:
        if not _is_text_message(m):
            continue
        for tok in _tokenize(m.text):
            if tok in STOPWORDS:
                continue
            if m.from_id in out:
                out[m.from_id][tok] += 1
    return out


def shared_word_counts(per_user: dict[str, Counter[str]]) -> tuple[Counter[str], dict[str, float]]:
    """Combine per-user counts into total counts + a per-word 'self-share' score.

    The returned ``shares`` map gives, for each word, the fraction of mentions
    that came from the self user (the first user_id passed in). Used by the
    word-cloud color function.
    """
    if not per_user:
        return Counter(), {}
    user_ids = list(per_user.keys())
    self_id = user_ids[0]
    total: Counter[str] = Counter()
    for c in per_user.values():
        total.update(c)
    shares: dict[str, float] = {}
    for word, count in total.items():
        self_count = per_user[self_id].get(word, 0)
        shares[word] = self_count / count if count else 0.5
    return total, shares
