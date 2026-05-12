from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import json

from .models import ContextPacket


def read_text_lossy(path: Path) -> str:
    """Read UTF-8 text, ignoring invalid bytes when a source contains lossy text."""

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def load_context_packet(path: Path) -> ContextPacket | None:
    """Load a context packet, returning None for malformed or non-packet files."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ContextPacket.from_dict(payload)
    except Exception:
        return None


def json_search_text(payload: dict[str, object]) -> str:
    """Return deterministic JSON text for lexical source scoring."""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def load_json_object(path: Path) -> dict[str, object] | None:
    """Load a JSON object, returning None for malformed or non-object JSON."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def load_json_list(path: Path) -> list[object] | None:
    """Load a JSON list, returning None for malformed or non-list JSON."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, list) else None


def iter_jsonl_objects(path: Path) -> Iterator[tuple[int, dict[str, object]]]:
    """Yield JSON object records from a JSONL source, skipping malformed lines."""

    for line_index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except Exception:
            continue
        if isinstance(record, dict):
            yield line_index, record


def load_jsonl_record(path: Path, line_index: int) -> dict[str, object]:
    """Load one JSONL object by line index, raising for unsafe or mismatched records."""

    if line_index < 0:
        raise KeyError(f"Invalid JSONL line_index={line_index}")
    lines = path.read_text(encoding="utf-8").splitlines()
    if line_index >= len(lines):
        raise KeyError(f"Missing JSONL line_index={line_index} in {path}")
    record = json.loads(lines[line_index])
    if not isinstance(record, dict):
        raise ValueError(f"Expected JSON object at {path}:{line_index}")
    return record
