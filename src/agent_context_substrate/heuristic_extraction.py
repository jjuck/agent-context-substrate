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
_SECTION_STOP_MARKERS = ("evidence", "proof", "원하면", "next step", "next steps")


@dataclass(frozen=True)
class HeuristicRecoveryFields:
    request: str | None
    outcome: str | None
    key_points: list[str]
    follow_up_questions: list[str]
    recovery_summary: str


@dataclass(frozen=True)
class HeuristicMessageAnalysis:
    messages: list[dict[str, Any]]
    salient_messages: list[dict[str, Any]]
    text: str
    request: str | None
    outcome: str | None
    key_points: list[str]
    follow_up_questions: list[str]
    recovery_summary: str
    files: list[str]
    entities: list[str]
    concepts: list[str]


def analyze_heuristic_messages(messages: list[dict[str, Any]]) -> HeuristicMessageAnalysis:
    """Extract stable heuristic summary stages from raw-compatible messages."""

    message_list = list(messages)
    salient_messages = _select_salient_messages(message_list)
    text_source = salient_messages if salient_messages else message_list
    text = _collect_text(text_source)
    files = _extract_files(text)
    entities = _extract_entities(text)
    concepts = _extract_concepts(text)
    recovery_fields = extract_recovery_fields(message_list)
    return HeuristicMessageAnalysis(
        messages=message_list,
        salient_messages=salient_messages,
        text=text,
        request=recovery_fields.request,
        outcome=recovery_fields.outcome,
        key_points=recovery_fields.key_points,
        follow_up_questions=recovery_fields.follow_up_questions,
        recovery_summary=recovery_fields.recovery_summary,
        files=files,
        entities=entities,
        concepts=concepts,
    )


def extract_recovery_fields(messages: list[dict[str, Any]]) -> HeuristicRecoveryFields:
    """Extract request/outcome/key-point fields used by recovery summaries."""

    message_list = list(messages)
    follow_up_questions = _extract_follow_up_questions(message_list)
    request = _extract_request(message_list, follow_up_questions)
    outcome = _extract_outcome(message_list)
    key_points = _extract_key_points(message_list)
    recovery_summary = compose_recovery_summary(
        messages=message_list,
        request=request,
        outcome=outcome,
        key_points=key_points,
        follow_up_questions=follow_up_questions,
    )
    return HeuristicRecoveryFields(
        request=request,
        outcome=outcome,
        key_points=key_points,
        follow_up_questions=follow_up_questions,
        recovery_summary=recovery_summary,
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


def _extract_request(messages: list[dict[str, Any]], follow_up_questions: list[str] | None = None) -> str | None:
    user_messages = _select_messages_by_role(messages, "user")
    if not user_messages:
        return None
    trailing_questions = set(follow_up_questions or [])
    request_messages = [message for message in user_messages if message not in trailing_questions]
    if not request_messages:
        request_messages = user_messages
    return _truncate_text(" Then: ".join(request_messages[:2]), limit=220)


def _split_message_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text).splitlines() if line.strip()]


def _is_list_line(text: str) -> bool:
    return bool(re.match(r"^(?:[-*]|\d+[.)])\s+", text))


def _normalize_list_line(text: str) -> str:
    stripped = re.sub(r"^(?:[-*]|\d+[.)])\s+", "", text).strip()
    return _strip_markdown(stripped)


def _should_stop_key_point_collection(text: str) -> bool:
    lowered = _strip_markdown(text).lower().rstrip(":")
    return any(lowered.startswith(marker) for marker in _SECTION_STOP_MARKERS)


def _extract_outcome(messages: list[dict[str, Any]]) -> str | None:
    assistant_messages = _select_raw_messages_by_role(messages, "assistant")
    for content in reversed(assistant_messages):
        for line in _split_message_lines(content):
            if _is_list_line(line):
                continue
            cleaned = _strip_markdown(line).rstrip(":")
            if cleaned:
                return _truncate_text(cleaned, limit=220)
        cleaned_content = _strip_markdown(content)
        if cleaned_content:
            return _truncate_text(cleaned_content, limit=220)
    return None


def _should_skip_key_point(text: str) -> bool:
    lowered = _strip_markdown(text).lower()
    return lowered.startswith(("즉,", "so ", "meaning "))


def _extract_key_points(messages: list[dict[str, Any]], limit: int = 4) -> list[str]:
    assistant_messages = _select_raw_messages_by_role(messages, "assistant")
    points: list[str] = []
    for content in assistant_messages:
        for line in _split_message_lines(content):
            if _should_stop_key_point_collection(line):
                return _dedupe_preserve_order(points)[:limit]
            if not _is_list_line(line):
                continue
            normalized = _normalize_list_line(line)
            if not normalized or _should_skip_key_point(normalized):
                continue
            points.append(_truncate_text(normalized, limit=160))
    return _dedupe_preserve_order(points)[:limit]


def _extract_follow_up_questions(messages: list[dict[str, Any]]) -> list[str]:
    salient_messages = _select_salient_messages(messages)
    if not salient_messages:
        return []
    last_message = salient_messages[-1]
    if last_message["role"] != "user":
        return []
    question = _truncate_text(last_message["content"], limit=220)
    if not question:
        return []
    if "?" not in question and "？" not in question:
        return []
    return [question]


def compose_recovery_summary(
    *,
    messages: list[dict[str, Any]],
    request: str | None,
    outcome: str | None,
    key_points: list[str],
    follow_up_questions: list[str],
) -> str:
    """Compose the recovery-oriented summary from extracted heuristic fields."""

    parts: list[str] = []
    if request:
        parts.append(f"Request: {request}")
    if outcome:
        parts.append(f"Outcome: {outcome}")
    if key_points:
        parts.append(f"Key points: {'; '.join(key_points[:3])}")
    if follow_up_questions:
        parts.append(f"Open question: {follow_up_questions[0]}")
    if parts:
        return " ".join(parts)

    fallback_text = _collect_text(messages)
    if fallback_text:
        return _truncate_text(fallback_text)
    return ""


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
