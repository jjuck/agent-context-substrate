from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

_FILE_PATTERN = re.compile(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+")
_ALLOWED_FILE_EXTENSIONS = {
    "bash",
    "bat",
    "cfg",
    "conf",
    "css",
    "csv",
    "db",
    "env",
    "html",
    "ini",
    "ipynb",
    "java",
    "js",
    "json",
    "jsx",
    "lock",
    "log",
    "md",
    "pdf",
    "ps1",
    "py",
    "rst",
    "sh",
    "sql",
    "tar",
    "tgz",
    "toml",
    "ts",
    "tsx",
    "txt",
    "xml",
    "yaml",
    "yml",
    "zip",
    "gz",
}
_ALLOWED_SPECIAL_FILENAMES = {
    ".env",
    ".gitignore",
    ".gitattributes",
    "dockerfile",
    "justfile",
    "makefile",
}
_CONVERSATION_ROLES = {"user", "assistant"}


@dataclass(frozen=True)
class HeuristicMetadataSignals:
    salient_messages: list[dict[str, Any]]
    text: str
    files: list[str]
    entities: list[str]
    concepts: list[str]


def extract_metadata_signals(messages: list[dict[str, Any]]) -> HeuristicMetadataSignals:
    """Extract text and metadata signals from salient conversation messages."""

    message_list = list(messages)
    salient_messages = _select_salient_messages(message_list)
    text_source = salient_messages if salient_messages else message_list
    text = _collect_text(text_source)
    files = _extract_files(text)
    entities = _extract_entities(text)
    concepts = _extract_concepts(text)
    return HeuristicMetadataSignals(
        salient_messages=salient_messages,
        text=text,
        files=files,
        entities=entities,
        concepts=concepts,
    )


def _collect_text(messages: list[dict[str, Any]]) -> str:
    return " ".join(str(message.get("content") or "").strip() for message in messages).strip()


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _truncate_text(text: str, limit: int = 140) -> str:
    normalized = _normalize_text(text)
    if len(normalized) <= limit:
        return normalized
    cutoff = normalized[: limit - 3].rstrip()
    return f"{cutoff}..."


def _strip_markdown(text: str) -> str:
    cleaned = re.sub(r"`([^`]*)`", r"\1", text)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"_([^_]+)_", r"\1", cleaned)
    return _normalize_text(cleaned)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = _normalize_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _message_content(message: dict[str, Any]) -> str:
    return _normalize_text(str(message.get("content") or ""))


def _raw_message_content(message: dict[str, Any]) -> str:
    return str(message.get("content") or "").strip()


def _select_messages_by_role(messages: list[dict[str, Any]], role: str) -> list[str]:
    selected: list[str] = []
    for message in messages:
        if str(message.get("role") or "") != role:
            continue
        content = _message_content(message)
        if content:
            selected.append(content)
    return selected


def _select_raw_messages_by_role(messages: list[dict[str, Any]], role: str) -> list[str]:
    selected: list[str] = []
    for message in messages:
        if str(message.get("role") or "") != role:
            continue
        content = _raw_message_content(message)
        if content:
            selected.append(content)
    return selected


def _select_salient_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    salient: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "")
        content = _message_content(message)
        if role not in _CONVERSATION_ROLES:
            continue
        if not content:
            continue
        salient.append({"role": role, "content": content})
    return salient


def _clean_file_candidate(candidate: str) -> str:
    return candidate.strip().strip("`'\"([{<").rstrip("`'\".,:;!?)]}>")


def _is_probable_file_candidate(candidate: str) -> bool:
    basename = candidate.replace("\\", "/").rsplit("/", 1)[-1]
    lowered = basename.lower()
    if lowered in _ALLOWED_SPECIAL_FILENAMES:
        return True
    if "." not in basename:
        return False
    extension = basename.rsplit(".", 1)[-1]
    if extension != extension.lower():
        return False
    return extension in _ALLOWED_FILE_EXTENSIONS


def _extract_files(text: str) -> list[str]:
    seen: set[str] = set()
    files: list[str] = []
    for match in _FILE_PATTERN.findall(text):
        cleaned = _clean_file_candidate(match)
        if not cleaned:
            continue
        if not re.search(r"[A-Za-z_]", cleaned):
            continue
        if not _is_probable_file_candidate(cleaned):
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            files.append(cleaned)
    return files


def _extract_entities(text: str) -> list[str]:
    entities: list[str] = []
    if "Hermes" in text:
        entities.append("Hermes")
    return entities


def _extract_concepts(text: str) -> list[str]:
    concepts: list[str] = []
    lower = text.lower()
    if "context packet" in lower or "context-packet" in lower:
        concepts.append("context-packet")
    if "summarization" in lower:
        concepts.append("summarization")
    return concepts
