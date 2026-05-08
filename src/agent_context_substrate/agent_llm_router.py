from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any


class AgentLLMRouterUnavailable(RuntimeError):
    """Raised when the host Agent does not expose a compatible LLM router."""


RouterMethod = Callable[..., Any]

_SECRET_KEY_RE = re.compile(r"(?i)(api[_-]?key|token|password|secret|connection[_-]?string)")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_ -]?key|token|password|secret|connection[_ -]?string)\s*[:=]\s*([^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_COMMON_KEY_RE = re.compile(r"\b(?:sk|pk|ghp|gho|github_pat|xoxb|xoxp)-[A-Za-z0-9_\-]{8,}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_SYSTEM_PROMPT = """You are the Agent Context Substrate summarizer.
Return strict JSON only. Do not include markdown fences or explanations.
Use only the provided evidence. Do not invent files, decisions, entities, or message ids.
Preserve evidence_message_ids for evidence-backed fields.
Never include API keys, tokens, passwords, credentials, or connection strings.
""".strip()


_METHOD_CANDIDATES = (
    "route_llm_json",
    "call_llm_json",
    "complete_json",
    "route_llm",
    "call_llm",
    "complete",
)
_CONTAINER_CANDIDATES = ("llm", "agent", "router")


def build_agent_llm_router(host: object) -> Callable[[dict[str, object]], dict[str, object]]:
    """Build an AgentLLMRouter callable from a host Agent/plugin context.

    This adapter is intentionally provider-agnostic: it looks for a host method
    that already knows the Agent's model/provider/key/routing policy, then sends
    a strict-JSON request to that method.
    """

    method = _find_router_method(host)
    if method is None:
        raise AgentLLMRouterUnavailable("host exposes no compatible Agent LLM router method")

    def router(request: dict[str, object]) -> dict[str, object]:
        host_request = build_host_llm_request(request)
        raw_response = _invoke_router_method(method, host_request)
        return _extract_json_object(raw_response)

    return router


def build_host_llm_request(request: dict[str, object]) -> dict[str, object]:
    safe_request = _redact_secret_like_values(request)
    routing_hints = safe_request.get("routing_hints")
    if not isinstance(routing_hints, dict):
        routing_hints = {}
    return {
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(safe_request, ensure_ascii=False, indent=2, sort_keys=True),
            },
        ],
        "response_format": {"type": "json_object"},
        "routing_hints": dict(routing_hints),
        "purpose": "agent-context-substrate-summary",
    }


def _find_router_method(host: object) -> RouterMethod | None:
    for candidate in _METHOD_CANDIDATES:
        method = getattr(host, candidate, None)
        if callable(method):
            return method
    for container_name in _CONTAINER_CANDIDATES:
        container = getattr(host, container_name, None)
        if container is None:
            continue
        method = _find_router_method(container)
        if method is not None:
            return method
    return None


def _invoke_router_method(method: RouterMethod, host_request: dict[str, object]) -> object:
    try:
        return method(host_request)
    except TypeError as first_error:
        try:
            return method(**host_request)
        except TypeError:
            raise first_error


def _extract_json_object(response: object) -> dict[str, object]:
    if isinstance(response, dict):
        for key in ("json", "data", "parsed"):
            candidate = response.get(key)
            if isinstance(candidate, dict):
                return candidate
        for key in ("content", "text", "message"):
            candidate = response.get(key)
            if isinstance(candidate, str):
                return _parse_json_object(candidate)
        return response
    if isinstance(response, str):
        return _parse_json_object(response)
    raise ValueError("Agent LLM router returned neither a JSON object nor JSON text")


def _parse_json_object(text: str) -> dict[str, object]:
    parsed = json.loads(_strip_json_fence(text))
    if not isinstance(parsed, dict):
        raise ValueError("Agent LLM router response must be a JSON object")
    return parsed


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _redact_secret_like_values(value: object) -> object:
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEY_RE.search(key_text):
                redacted[key_text] = "<REDACTED_SECRET>"
            else:
                redacted[key_text] = _redact_secret_like_values(item)
        return redacted
    if isinstance(value, list):
        return [_redact_secret_like_values(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_secret_like_values(item) for item in value]
    if isinstance(value, str):
        return _redact_secret_string(value)
    return value


def _redact_secret_string(text: str) -> str:
    redacted = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=<REDACTED_SECRET>", text)
    redacted = _BEARER_RE.sub("Bearer <REDACTED_SECRET>", redacted)
    redacted = _COMMON_KEY_RE.sub("<REDACTED_SECRET>", redacted)
    redacted = _EMAIL_RE.sub("<REDACTED_EMAIL>", redacted)
    return redacted
