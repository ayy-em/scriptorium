"""Stream-parsing and normalization for raw Telegram export JSON files."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import ijson


@dataclass(frozen=True)
class Participant:
    """One side of a Telegram personal chat."""

    id: str
    display_name: str
    is_self: bool


@dataclass(frozen=True)
class ChatMetadata:
    """Top-level metadata extracted from the export."""

    name: str
    chat_type: str
    chat_id: int
    participants: tuple[Participant, ...]


@dataclass
class Message:
    """Normalized chat message used by metric and chart code."""

    date: datetime
    from_id: str
    sender_name: str
    text: str
    text_entities: list[dict] = field(default_factory=list)
    media_type: str | None = None
    sticker_emoji: str | None = None


SUPPORTED_CHAT_TYPE = "personal_chat"
MAX_PARTICIPANTS = 2


class InvalidExportError(ValueError):
    """Raised when an export file is not a supported personal Telegram chat."""


def _read_top_level_scalars(path: Path) -> dict[str, object]:
    """Extract top-level ``name``, ``type``, ``id`` without loading the messages array."""
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


def iter_raw_messages(path: Path) -> Iterator[dict]:
    """Yield raw message dicts from ``messages[]`` via streaming JSON parse."""
    with open(path, "rb") as f:
        yield from ijson.items(f, "messages.item")


def _flatten_entities(entities: list[dict]) -> str:
    """Join the ``text`` of every entity in a ``text_entities`` array."""
    return "".join(str(e.get("text", "")) for e in entities)


def _normalize_one(raw: dict) -> Message | None:
    """Convert one raw Telegram message dict into a Message, or return None to skip."""
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
    entities = raw.get("text_entities") or []
    if not isinstance(entities, list):
        entities = []
    text = _flatten_entities(entities)
    return Message(
        date=date,
        from_id=str(from_id),
        sender_name=str(sender_name),
        text=text,
        text_entities=list(entities),
        media_type=raw.get("media_type"),
        sticker_emoji=raw.get("sticker_emoji"),
    )


def load_chat(path: Path) -> tuple[ChatMetadata, list[Message]]:
    """Parse the export at ``path`` into metadata + a list of normalized messages.

    Raises ``InvalidExportError`` if the file is not a personal chat or has more
    than two distinct participants.
    """
    scalars = _read_top_level_scalars(path)
    name = scalars.get("name")
    chat_type = scalars.get("type")
    chat_id = scalars.get("id")
    if not isinstance(name, str) or not isinstance(chat_type, str) or not isinstance(chat_id, int):
        raise InvalidExportError(
            "Export is missing required top-level keys: 'name', 'type', and 'id' must all be present."
        )
    if chat_type != SUPPORTED_CHAT_TYPE:
        raise InvalidExportError(
            f"Unsupported chat type {chat_type!r}; only {SUPPORTED_CHAT_TYPE!r} is supported in MVP."
        )

    messages: list[Message] = []
    sender_lookup: dict[str, str] = {}
    for raw in iter_raw_messages(path):
        msg = _normalize_one(raw)
        if msg is None:
            continue
        messages.append(msg)
        sender_lookup.setdefault(msg.from_id, msg.sender_name)
        if len(sender_lookup) > MAX_PARTICIPANTS:
            raise InvalidExportError(
                f"Export has more than 2 distinct senders ({len(sender_lookup)}); "
                "group/channel chats are not supported in MVP."
            )

    participants = _identify_participants(name, sender_lookup)
    metadata = ChatMetadata(name=name, chat_type=chat_type, chat_id=chat_id, participants=participants)
    return metadata, messages


def _identify_participants(partner_name: str, sender_lookup: dict[str, str]) -> tuple[Participant, ...]:
    """Map the root ``name`` to the partner; everything else is ``self``."""
    partner_id: str | None = None
    self_id: str | None = None
    self_display: str | None = None
    for from_id, display in sender_lookup.items():
        if display == partner_name and partner_id is None:
            partner_id = from_id
        elif self_id is None:
            self_id = from_id
            self_display = display

    out: list[Participant] = []
    if self_id is not None:
        out.append(Participant(id=self_id, display_name=self_display or "(you)", is_self=True))
    if partner_id is not None:
        out.append(Participant(id=partner_id, display_name=partner_name, is_self=False))
    elif self_id is not None:
        out.append(Participant(id="unknown", display_name=partner_name, is_self=False))
    elif sender_lookup:
        only_id, only_display = next(iter(sender_lookup.items()))
        out.append(Participant(id=only_id, display_name=only_display, is_self=True))
        out.append(Participant(id="unknown", display_name=partner_name, is_self=False))
    return tuple(out)
