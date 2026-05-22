"""Stream-parsing and normalization for Telegram group chat export JSON files."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import ijson

from scripts.telegram._parsing import InvalidExportError

SUPPORTED_GROUP_TYPES = {"private_supergroup", "public_supergroup", "private_group", "public_group"}


@dataclass(frozen=True)
class GroupMetadata:
    """Top-level metadata extracted from a group chat export."""

    name: str
    chat_type: str
    chat_id: int


@dataclass
class GroupMessage:
    """Normalized group chat message used by metric and chart code."""

    id: int
    date: datetime
    from_id: str
    sender_name: str
    text: str
    text_entities: list[dict] = field(default_factory=list)
    media_type: str | None = None
    sticker_emoji: str | None = None
    forwarded_from_id: str | None = None
    reply_to_message_id: int | None = None
    duration_seconds: int | None = None


def _read_top_level_scalars(path: Path) -> dict[str, object]:
    """Extract top-level ``name``, ``type``, ``id`` without loading the messages array.

    Args:
        path: Path to the Telegram group chat export JSON file.

    Returns:
        Dictionary with ``name``, ``type``, and ``id`` keys when present.
    """
    out: dict[str, object] = {}
    with open(path, "rb") as f:
        for prefix, event, value in ijson.parse(f):
            if event == "start_array" and prefix == "messages":
                break
            if prefix == "name" and event == "string":
                out["name"] = value
            elif prefix == "type" and event == "string":
                out["type"] = value
            elif prefix == "id" and event == "number":
                out["id"] = int(value)
    return out


def _iter_raw_messages(path: Path) -> Iterator[dict]:
    """Yield raw message dicts from ``messages[]`` via streaming JSON parse.

    Args:
        path: Path to the Telegram group chat export JSON file.

    Yields:
        Raw message dictionaries from the export.
    """
    with open(path, "rb") as f:
        yield from ijson.items(f, "messages.item")


def _flatten_entities(entities: list[dict]) -> str:
    """Join the ``text`` of every entity in a ``text_entities`` array.

    Args:
        entities: List of entity dictionaries, each expected to have a ``text`` key.

    Returns:
        Concatenated text from all entities.
    """
    return "".join(str(e.get("text", "")) for e in entities)


def _flatten_text(text: str | list) -> str:
    """Collapse the ``text`` field into a plain string.

    Telegram exports may represent ``text`` as a plain string or as a list of
    mixed strings and entity-object dicts (each with a ``text`` key).

    Args:
        text: Either a plain string or a mixed list of strings and dicts.

    Returns:
        Flat string with all fragments concatenated.
    """
    if isinstance(text, str):
        return text
    parts: list[str] = []
    for fragment in text:
        if isinstance(fragment, str):
            parts.append(fragment)
        elif isinstance(fragment, dict):
            parts.append(str(fragment.get("text", "")))
    return "".join(parts)


def _normalize_one(raw: dict) -> GroupMessage | None:
    """Convert one raw Telegram message dict into a GroupMessage, or ``None`` to skip.

    Service messages, messages without ``from_id``, and messages without a
    parseable date are silently skipped.

    Args:
        raw: Raw message dictionary from the export.

    Returns:
        Normalized ``GroupMessage`` or ``None`` if the message should be skipped.
    """
    if raw.get("type") != "message":
        return None
    from_id = raw.get("from_id")
    sender_name = raw.get("from") or ""
    date_str = raw.get("date")
    if not from_id or not date_str:
        return None
    try:
        date = datetime.fromisoformat(date_str)
    except ValueError:
        return None

    msg_id = raw.get("id")
    if msg_id is None:
        return None

    entities = raw.get("text_entities") or []
    if not isinstance(entities, list):
        entities = []
    text_raw = raw.get("text", "")
    text = _flatten_text(text_raw) if isinstance(text_raw, list) else _flatten_entities(entities)

    fwd_id = raw.get("forwarded_from_id") or raw.get("forwarded_from")
    reply_to = raw.get("reply_to_message_id")

    raw_duration = raw.get("duration_seconds")

    return GroupMessage(
        id=int(msg_id),
        date=date,
        from_id=str(from_id),
        sender_name=str(sender_name),
        text=text,
        text_entities=list(entities),
        media_type=raw.get("media_type"),
        sticker_emoji=raw.get("sticker_emoji"),
        forwarded_from_id=str(fwd_id) if fwd_id else None,
        reply_to_message_id=int(reply_to) if reply_to is not None else None,
        duration_seconds=int(raw_duration) if raw_duration is not None else None,
    )


def _is_bot_name(name: str) -> bool:
    """Heuristic: Telegram bot usernames must end in 'bot' or 'Bot'."""
    return name.endswith("Bot") or name.endswith("bot")


def load_group_chat(path: Path) -> tuple[GroupMetadata, list[GroupMessage], dict[str, str], set[str]]:
    """Parse a group chat export into metadata, messages, a sender lookup, and bot IDs.

    Args:
        path: Path to the Telegram group chat export JSON file.

    Returns:
        A four-element tuple of (``GroupMetadata``, list of ``GroupMessage``,
        sender lookup mapping ``from_id`` to the most recent display name,
        set of ``from_id`` values detected as bots).

    Raises:
        InvalidExportError: If the file is missing required top-level keys or
            the chat type is not a supported group type.
    """
    scalars = _read_top_level_scalars(path)
    name = scalars.get("name")
    chat_type = scalars.get("type")
    chat_id = scalars.get("id")
    if not isinstance(name, str) or not isinstance(chat_type, str) or not isinstance(chat_id, int):
        raise InvalidExportError(
            "Export is missing required top-level keys: 'name', 'type', and 'id' must all be present."
        )
    if chat_type not in SUPPORTED_GROUP_TYPES:
        raise InvalidExportError(
            f"Unsupported chat type {chat_type!r}; supported group types are {SUPPORTED_GROUP_TYPES!r}."
        )

    messages: list[GroupMessage] = []
    sender_lookup: dict[str, str] = {}
    for raw in _iter_raw_messages(path):
        msg = _normalize_one(raw)
        if msg is None:
            continue
        messages.append(msg)
        sender_lookup.setdefault(msg.from_id, msg.sender_name)

    bot_ids = {uid for uid, name in sender_lookup.items() if _is_bot_name(name)}
    metadata = GroupMetadata(name=name, chat_type=chat_type, chat_id=chat_id)
    return metadata, messages, sender_lookup, bot_ids
