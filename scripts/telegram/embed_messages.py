"""Embed Telegram messages (preprocessed by ``telegram.preprocess``) for downstream retrieval."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

from core.argparse import ScriptoriumParser
from core.paths import inputs_dir, outputs_dir

TITLE = "Embed preprocessed Telegram messages"
DESCRIPTION = "Embed every message with sliding-window context; write embeddings.jsonl + manifest."

DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_WINDOW = 4
DEFAULT_BATCH = 256
_OPENAI_API_KEY = "OPENAI_API_KEY"


class MissingCredentialsError(RuntimeError):
    """Raised when an embedding client is needed but no API key is configured."""


def _inputs() -> Path:
    return inputs_dir("telegram")


def _outputs() -> Path:
    return outputs_dir("telegram")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_source(source: Path) -> tuple[list[dict], list[str]]:
    """Return (messages_in_chronological_order, source_filenames)."""
    if source.suffix.lower() == ".zip":
        messages: list[dict] = []
        member_names: list[str] = []
        with zipfile.ZipFile(source) as zf:
            for name in sorted(zf.namelist()):
                if not name.startswith("messages_") or not name.endswith(".json"):
                    continue
                messages.extend(json.loads(zf.read(name).decode("utf-8")))
                member_names.append(name)
        return messages, member_names

    data = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "messages" in data:
        data = data["messages"]
    if not isinstance(data, list):
        raise ValueError(f"unexpected JSON shape in {source}; expected list or {{'messages': [...]}}")
    return data, [source.name]


def _plain_text(message: dict) -> str:
    """Flatten ``text_entities`` (short key ``e``) into a single plain-text string."""
    entities = message.get("e") or []
    if not isinstance(entities, list):
        return ""
    parts: list[str] = []
    for entity in entities:
        if isinstance(entity, dict):
            text = entity.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif isinstance(entity, str):
            parts.append(entity)
    return "".join(parts).strip()


def _build_unit_text(message: dict, context: list[dict]) -> str:
    r"""Render `<context>\n<current>` with `sender (date): text` lines."""
    lines: list[str] = []
    for ctx in context:
        if text := _plain_text(ctx):
            lines.append(f"{ctx.get('f', '?')} ({ctx.get('d', '?')}): {text}")
    current = _plain_text(message)
    lines.append(f"{message.get('f', '?')} ({message.get('d', '?')}): {current}")
    return "\n".join(lines)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _default_client():
    api_key = os.environ.get(_OPENAI_API_KEY, "").strip()
    if not api_key:
        raise MissingCredentialsError(
            f"OpenAI embeddings require {_OPENAI_API_KEY} to be set. Export your key before running."
        )
    from openai import OpenAI  # noqa: PLC0415

    return OpenAI(api_key=api_key)


def _embed_batch(client, model: str, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(input=texts, model=model)
    return [item.embedding for item in response.data]


def _load_cache(path: Path) -> dict[str, list[float]]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}


def _save_cache(path: Path, cache: dict[str, list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache), encoding="utf-8")


def embed_messages(  # noqa: PLR0913
    source: Path,
    output_dir: Path,
    *,
    model: str = DEFAULT_MODEL,
    window: int = DEFAULT_WINDOW,
    batch_size: int = DEFAULT_BATCH,
    client=None,
) -> Path:
    """Embed every message in ``source`` and write outputs to ``output_dir``.

    Args:
        source: A .zip from ``telegram.preprocess`` or a processed .json.
        output_dir: Destination directory. Will contain ``embeddings.jsonl``,
            ``manifest.json``, and ``embedding_cache.json``.
        model: Embedding model name. Defaults to text-embedding-3-small.
        window: Number of preceding messages to include as context per unit.
        batch_size: Number of texts per embedding API call.
        client: Optional pre-built client (mock in tests). When ``None``, builds
            an OpenAI client from ``OPENAI_API_KEY``.

    Returns:
        Path to ``output_dir/manifest.json`` on success.

    Raises:
        FileNotFoundError: If ``source`` does not exist.
        ValueError: If ``window`` or ``batch_size`` are non-positive.
        MissingCredentialsError: If no client is provided and the env var is unset.
    """
    if not source.is_file():
        raise FileNotFoundError(f"source not found: {source}")
    if window < 0:
        raise ValueError(f"window must be non-negative, got {window}")
    if batch_size <= 0:
        raise ValueError(f"batch_size must be positive, got {batch_size}")

    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / "embedding_cache.json"
    cache = _load_cache(cache_path)

    messages, source_members = _load_source(source)

    units: list[dict] = []
    for idx, message in enumerate(messages):
        context = messages[max(0, idx - window) : idx]
        text = _build_unit_text(message, context)
        units.append(
            {
                "unit_id": idx,
                "date": message.get("d"),
                "from": message.get("f"),
                "type": message.get("t"),
                "text": _plain_text(message),
                "context_text": text,
                "content_hash": _content_hash(text),
            }
        )

    if client is None:
        client = _default_client()

    seen_hashes: set[str] = set(cache.keys())
    pending_indices: list[int] = []
    pending_texts: list[str] = []
    for i, unit in enumerate(units):
        h = unit["content_hash"]
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        pending_indices.append(i)
        pending_texts.append(unit["context_text"])

    for start in range(0, len(pending_texts), batch_size):
        chunk = pending_texts[start : start + batch_size]
        chunk_indices = pending_indices[start : start + batch_size]
        embeddings = _embed_batch(client, model, chunk)
        for unit_idx, vector in zip(chunk_indices, embeddings, strict=True):
            cache[units[unit_idx]["content_hash"]] = vector
        _save_cache(cache_path, cache)

    dims = len(next(iter(cache.values()))) if cache else 0
    embeddings_path = output_dir / "embeddings.jsonl"
    with open(embeddings_path, "w", encoding="utf-8") as f:
        for unit in units:
            record = {
                "unit_id": unit["unit_id"],
                "date": unit["date"],
                "from": unit["from"],
                "type": unit["type"],
                "text": unit["text"],
                "embedding": cache[unit["content_hash"]],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    manifest = {
        "source_name": source.name,
        "source_sha256": _sha256(source),
        "source_members": source_members,
        "model": model,
        "dimensions": dims,
        "total_units": len(units),
        "window": window,
        "batch_size": batch_size,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


_EXAMPLES = """
examples:
  uv run main.py telegram.embed_messages processed.zip
  uv run main.py telegram.embed_messages processed.zip --window 6 --batch-size 128
  uv run main.py telegram.embed_messages messages_2020.json --output run-1
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py telegram.embed_messages",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Preprocessed .zip (from telegram.preprocess) or a single processed .json",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="embeddings",
        metavar="DIR",
        help="Subdirectory under telegram/outputs/ (default: embeddings)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Embedding model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=DEFAULT_WINDOW,
        help=f"Sliding-window context size (default: {DEFAULT_WINDOW})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH,
        help=f"Texts per embedding API call (default: {DEFAULT_BATCH})",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to embed_messages()."""
    args = get_parser().parse_args()

    source = args.source
    if source.parent == Path("."):
        source = _inputs() / source.name

    output_dir = _outputs() / args.output

    try:
        manifest_path = embed_messages(
            source,
            output_dir,
            model=args.model,
            window=args.window,
            batch_size=args.batch_size,
        )
    except MissingCredentialsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"wrote manifest {manifest_path}")
    sys.exit(0)
