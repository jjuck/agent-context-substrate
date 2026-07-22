from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import re


AgentLLMRouter = Callable[[dict[str, object]], dict[str, object] | str]


@dataclass(frozen=True)
class LLMInputSafetyOptions:
    """Safety controls for payloads sent to opt-in LLM/custom workers."""

    redact: bool = True
    max_input_chars: int = 12_000
    allow_code_snippets: bool = False
    path_policy: str = "redact"

    def __post_init__(self) -> None:
        if self.max_input_chars < 256:
            raise ValueError("llm max input chars must be at least 256")
        if self.path_policy not in {"redact", "allow"}:
            raise ValueError("llm path policy must be one of: allow, redact")


_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b([A-Za-z0-9_-]*(?:api[_-]?key|secret|token|password|credential|connection[_-]?string)[A-Za-z0-9_-]*)"
    r"\s*[:=]\s*([^\s,;]+)",
    flags=re.IGNORECASE,
)
_BEARER_TOKEN_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", flags=re.IGNORECASE)
_TOKEN_PATTERN = re.compile(
    r"\b(?:(?:sk|pk)-[A-Za-z0-9_./+=-]{6,}|(?:ghp|github_pat|xox[baprs])[_-][A-Za-z0-9_./+=-]{6,})\b"
)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_CODE_FENCE_PATTERN = re.compile(r"```.*?```", flags=re.DOTALL)
_WINDOWS_ABSOLUTE_PATH_PATTERN = re.compile(
    r"\b[A-Za-z]:[\\/](?:[^\\/\s,;:'\"<>|]+[\\/])*[^\\/\s,;:'\"<>|]+(?: [^\\/\s,;:'\"<>|]+)*"
)
_UNIX_ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?<![^\s('\"\[<{=])/(?:[^/\s,;:'\"<>|]+(?: [^/\s,;:'\"<>|]+)*\/)*[^/\s,;:'\"<>|]+(?: [^/\s,;:'\"<>|]+)*"
)
_LOCAL_PATH_REDACTION = "<REDACTED_LOCAL_PATH>"
_TRUNCATION_MARKER = "...<TRUNCATED_FOR_LLM_INPUT>"


def call_router_with_json_repair(
    *,
    router: AgentLLMRouter,
    request: dict[str, object],
    safety: LLMInputSafetyOptions,
    error_label: str,
) -> dict[str, object]:
    response = router(prepare_llm_request(request, safety=safety))
    try:
        return _parse_router_json_response(response, error_label=error_label)
    except json.JSONDecodeError as exc:
        repair_request = {
            "kind": "repair-json",
            "schema_version": request.get("schema_version"),
            "invalid_json": response,
            "json_error": str(exc),
            "original_request": request,
            "instruction": "Return only one strict JSON object matching the original schema.",
        }
        repaired_response = router(prepare_llm_request(repair_request, safety=safety))
        return _parse_router_json_response(repaired_response, error_label=error_label)


def prepare_llm_request(
    request: dict[str, object],
    *,
    safety: LLMInputSafetyOptions,
) -> dict[str, object]:
    prepared = _sanitize_value(request, safety=safety)
    if not isinstance(prepared, dict):
        raise TypeError("LLM request must sanitize to a JSON object")
    return _bound_llm_request(prepared, max_chars=safety.max_input_chars)


def _parse_router_json_response(
    response: dict[str, object] | str,
    *,
    error_label: str,
) -> dict[str, object]:
    parsed = json.loads(response) if isinstance(response, str) else response
    if not isinstance(parsed, dict):
        raise ValueError(f"{error_label} must return a JSON object or JSON object string")
    return parsed


def _sanitize_value(value: object, *, safety: LLMInputSafetyOptions) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            if not safety.allow_code_snippets and key == "code_blocks" and isinstance(item, list):
                sanitized[str(key)] = []
            else:
                sanitized[str(key)] = _sanitize_value(item, safety=safety)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(item, safety=safety) for item in value]
    if isinstance(value, str):
        text = value
        if not safety.allow_code_snippets:
            text = _CODE_FENCE_PATTERN.sub("<CODE_BLOCK_OMITTED>", text)
        if safety.path_policy == "redact":
            text = _redact_local_paths(text)
        return _redact_llm_text(text) if safety.redact else text
    return value


def _redact_llm_text(text: str) -> str:
    redacted = _SECRET_ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}=<REDACTED_SECRET>", text)
    redacted = _BEARER_TOKEN_PATTERN.sub("Bearer <REDACTED_SECRET>", redacted)
    redacted = _TOKEN_PATTERN.sub("<REDACTED_SECRET>", redacted)
    return _EMAIL_PATTERN.sub("<REDACTED_EMAIL>", redacted)


def _redact_local_paths(text: str) -> str:
    redacted = _WINDOWS_ABSOLUTE_PATH_PATTERN.sub(_LOCAL_PATH_REDACTION, text)
    return _UNIX_ABSOLUTE_PATH_PATTERN.sub(_LOCAL_PATH_REDACTION, redacted)


def _bound_llm_request(request: dict[str, object], *, max_chars: int) -> dict[str, object]:
    if _json_size(request) <= max_chars:
        return request
    for string_limit in _descending_string_limits(max_chars):
        string_bounded = _truncate_strings(request, per_string_limit=string_limit)
        for list_limit in (64, 32, 16, 8, 4, 2, 1):
            bounded = _truncate_lists(string_bounded, max_items=list_limit)
            if isinstance(bounded, dict):
                bounded["llm_input_truncated"] = True
            if _json_size(bounded) <= max_chars:
                return bounded
    compact = {
        "kind": request.get("kind"),
        "schema_version": request.get("schema_version"),
        "routing_hints": request.get("routing_hints", {}),
        "evidence": _truncate_lists(
            _truncate_strings(request.get("evidence", {}), per_string_limit=32),
            max_items=1,
        ),
        "llm_input_truncated": True,
    }
    return compact if _json_size(compact) <= max_chars else {"llm_input_truncated": True}


def _descending_string_limits(max_chars: int) -> list[int]:
    initial = max(64, min(2048, max_chars // 8))
    return sorted({initial, 512, 256, 128, 64, 32}, reverse=True)


def _truncate_strings(value: object, *, per_string_limit: int) -> object:
    if isinstance(value, dict):
        return {key: _truncate_strings(item, per_string_limit=per_string_limit) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate_strings(item, per_string_limit=per_string_limit) for item in value]
    if isinstance(value, str) and len(value) > per_string_limit:
        keep = max(0, per_string_limit - len(_TRUNCATION_MARKER))
        return value[:keep] + _TRUNCATION_MARKER
    return value


def _truncate_lists(value: object, *, max_items: int) -> object:
    if isinstance(value, dict):
        return {key: _truncate_lists(item, max_items=max_items) for key, item in value.items()}
    if isinstance(value, list):
        items = value
        if len(items) > max_items:
            head_count = (max_items + 1) // 2
            tail_count = max_items // 2
            items = items[:head_count] + (items[-tail_count:] if tail_count else [])
        return [_truncate_lists(item, max_items=max_items) for item in items]
    return value


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True))
