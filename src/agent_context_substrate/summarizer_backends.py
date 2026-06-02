from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

from .models import EvidenceMessage, MicroEvidenceBundle, MicroSummaryV2, UnitSummaryV2
from .summarizer import build_micro_summary_v2, build_unit_summary_v2
from .summary_lint import lint_micro_summary_v2, lint_unit_summary_v2


class SummarizerBackend(Protocol):
    name: str

    def summarize_micro(
        self,
        evidence: MicroEvidenceBundle,
        *,
        schema_version: str,
    ) -> MicroSummaryV2:
        ...

    def summarize_unit(
        self,
        *,
        unit_id: str,
        session_id: str,
        title: str,
        goal: str,
        micro_summaries: list[MicroSummaryV2],
        schema_version: str,
        related_pages: list[str] | None = None,
    ) -> UnitSummaryV2:
        ...


AgentLLMRouter = Callable[[dict[str, object]], dict[str, object] | str]


def _split_custom_command(command: str) -> list[str]:
    if os.name != "nt":
        return shlex.split(command)
    return _split_windows_command(command)


def _split_windows_command(command: str) -> list[str]:
    import ctypes

    argc = ctypes.c_int()
    command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
    command_line_to_argv.argtypes = (ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int))
    command_line_to_argv.restype = ctypes.POINTER(ctypes.c_wchar_p)
    local_free = ctypes.windll.kernel32.LocalFree
    local_free.argtypes = (ctypes.c_void_p,)
    local_free.restype = ctypes.c_void_p
    argv = command_line_to_argv(command, ctypes.byref(argc))
    if not argv:
        raise ValueError("unable to parse Windows command line")
    try:
        return [argv[index] for index in range(argc.value)]
    finally:
        local_free(argv)


@dataclass(frozen=True)
class LLMInputSafetyOptions:
    """Safety controls for payloads sent to opt-in LLM/custom summarizers."""

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
    r"(?<![A-Za-z0-9+.:/\-])/(?:[^/\s,;:'\"<>|]+(?: [^/\s,;:'\"<>|]+)*\/)*[^/\s,;:'\"<>|]+(?: [^/\s,;:'\"<>|]+)*"
)
_LOCAL_PATH_REDACTION = "<REDACTED_LOCAL_PATH>"
_TRUNCATION_MARKER = "…<TRUNCATED_FOR_LLM_INPUT>"


class AgentLLMSummarizerBackend:
    name = "agent-llm"

    def __init__(
        self,
        *,
        router: AgentLLMRouter,
        fallback_backend: SummarizerBackend | None = None,
        routing_hints: dict[str, object] | None = None,
        llm_safety: LLMInputSafetyOptions | None = None,
    ) -> None:
        self.router = router
        self.fallback_backend = fallback_backend or HeuristicSummarizerBackend()
        self.routing_hints = dict(routing_hints or {})
        self.llm_safety = llm_safety or LLMInputSafetyOptions()

    def summarize_micro(
        self,
        evidence: MicroEvidenceBundle,
        *,
        schema_version: str,
    ) -> MicroSummaryV2:
        if schema_version != "micro_summary_v2":
            raise ValueError(f"Unsupported micro summary schema_version={schema_version!r}")
        try:
            payload = self._call_router(
                {
                    "kind": "micro",
                    "schema_version": schema_version,
                    "evidence": evidence.to_dict(),
                    "routing_hints": self.routing_hints,
                }
            )
            summary = MicroSummaryV2.from_dict(payload)
            self._raise_if_micro_summary_fails_lint(summary, evidence)
            return summary
        except Exception as exc:
            fallback = self.fallback_backend.summarize_micro(evidence, schema_version=schema_version)
            return _with_fallback_metadata(
                fallback,
                fallback_from=self.name,
                fallback_reason=_summarizer_fallback_reason(exc),
            )

    def summarize_unit(
        self,
        *,
        unit_id: str,
        session_id: str,
        title: str,
        goal: str,
        micro_summaries: list[MicroSummaryV2],
        schema_version: str,
        related_pages: list[str] | None = None,
    ) -> UnitSummaryV2:
        if schema_version != "unit_summary_v2":
            raise ValueError(f"Unsupported unit summary schema_version={schema_version!r}")
        try:
            payload = self._call_router(
                {
                    "kind": "unit",
                    "unit_id": unit_id,
                    "session_id": session_id,
                    "title": title,
                    "goal": goal,
                    "schema_version": schema_version,
                    "related_pages": list(related_pages or []),
                    "micro_summaries": [summary.to_dict() for summary in micro_summaries],
                    "routing_hints": self.routing_hints,
                }
            )
            summary = UnitSummaryV2.from_dict(payload)
            self._raise_if_unit_summary_fails_lint(summary, micro_summaries)
            return summary
        except Exception as exc:
            fallback = self.fallback_backend.summarize_unit(
                unit_id=unit_id,
                session_id=session_id,
                title=title,
                goal=goal,
                micro_summaries=micro_summaries,
                schema_version=schema_version,
                related_pages=list(related_pages or []),
            )
            return _with_fallback_metadata(
                fallback,
                fallback_from=self.name,
                fallback_reason=_summarizer_fallback_reason(exc),
            )

    def _call_router(self, request: dict[str, object]) -> dict[str, object]:
        return _call_router_with_json_repair(
            router=self.router,
            request=request,
            safety=self.llm_safety,
            error_label="Agent LLM router",
        )

    def _raise_if_micro_summary_fails_lint(
        self,
        summary: MicroSummaryV2,
        evidence: MicroEvidenceBundle,
    ) -> None:
        raw_bundle = _raw_bundle_from_evidence(evidence)
        report = lint_micro_summary_v2(summary, raw_bundle=raw_bundle)
        if not report.ok:
            issue_codes = ", ".join(issue.code for issue in report.issues)
            raise ValueError(f"Agent LLM micro summary failed lint: {issue_codes}")

    def _raise_if_unit_summary_fails_lint(
        self,
        summary: UnitSummaryV2,
        micro_summaries: list[MicroSummaryV2],
    ) -> None:
        report = lint_unit_summary_v2(summary, micro_summaries=micro_summaries)
        if not report.ok:
            issue_codes = ", ".join(issue.code for issue in report.issues)
            raise ValueError(f"Agent LLM unit summary failed lint: {issue_codes}")


class HybridSummarizerBackend:
    name = "hybrid"

    def __init__(
        self,
        *,
        router: AgentLLMRouter,
        heuristic_backend: SummarizerBackend | None = None,
        routing_hints: dict[str, object] | None = None,
        llm_safety: LLMInputSafetyOptions | None = None,
    ) -> None:
        self.router = router
        self.heuristic_backend = heuristic_backend or HeuristicSummarizerBackend()
        self.routing_hints = dict(routing_hints or {})
        self.llm_safety = llm_safety or LLMInputSafetyOptions()

    def summarize_micro(
        self,
        evidence: MicroEvidenceBundle,
        *,
        schema_version: str,
    ) -> MicroSummaryV2:
        if schema_version != "micro_summary_v2":
            raise ValueError(f"Unsupported micro summary schema_version={schema_version!r}")
        heuristic_summary = self.heuristic_backend.summarize_micro(evidence, schema_version=schema_version)
        try:
            payload = self._call_router(
                {
                    "kind": "micro",
                    "mode": self.name,
                    "schema_version": schema_version,
                    "evidence": evidence.to_dict(),
                    "heuristic_summary": heuristic_summary.to_dict(),
                    "routing_hints": self.routing_hints,
                }
            )
            summary = MicroSummaryV2.from_dict(payload)
            self._raise_if_micro_summary_fails_lint(summary, evidence)
            return summary
        except Exception as exc:
            return _with_fallback_metadata(
                heuristic_summary,
                fallback_from=self.name,
                fallback_reason=_summarizer_fallback_reason(exc),
            )

    def summarize_unit(
        self,
        *,
        unit_id: str,
        session_id: str,
        title: str,
        goal: str,
        micro_summaries: list[MicroSummaryV2],
        schema_version: str,
        related_pages: list[str] | None = None,
    ) -> UnitSummaryV2:
        if schema_version != "unit_summary_v2":
            raise ValueError(f"Unsupported unit summary schema_version={schema_version!r}")
        heuristic_summary = self.heuristic_backend.summarize_unit(
            unit_id=unit_id,
            session_id=session_id,
            title=title,
            goal=goal,
            micro_summaries=micro_summaries,
            schema_version=schema_version,
            related_pages=list(related_pages or []),
        )
        try:
            payload = self._call_router(
                {
                    "kind": "unit",
                    "mode": self.name,
                    "unit_id": unit_id,
                    "session_id": session_id,
                    "title": title,
                    "goal": goal,
                    "schema_version": schema_version,
                    "related_pages": list(related_pages or []),
                    "micro_summaries": [summary.to_dict() for summary in micro_summaries],
                    "heuristic_unit_summary": heuristic_summary.to_dict(),
                    "routing_hints": self.routing_hints,
                }
            )
            summary = UnitSummaryV2.from_dict(payload)
            self._raise_if_unit_summary_fails_lint(summary, micro_summaries)
            return summary
        except Exception as exc:
            return _with_fallback_metadata(
                heuristic_summary,
                fallback_from=self.name,
                fallback_reason=_summarizer_fallback_reason(exc),
            )

    def _call_router(self, request: dict[str, object]) -> dict[str, object]:
        return _call_router_with_json_repair(
            router=self.router,
            request=request,
            safety=self.llm_safety,
            error_label="Hybrid Agent LLM router",
        )

    def _raise_if_micro_summary_fails_lint(
        self,
        summary: MicroSummaryV2,
        evidence: MicroEvidenceBundle,
    ) -> None:
        raw_bundle = _raw_bundle_from_evidence(evidence)
        report = lint_micro_summary_v2(summary, raw_bundle=raw_bundle)
        if not report.ok:
            issue_codes = ", ".join(issue.code for issue in report.issues)
            raise ValueError(f"hybrid micro summary failed lint: {issue_codes}")

    def _raise_if_unit_summary_fails_lint(
        self,
        summary: UnitSummaryV2,
        micro_summaries: list[MicroSummaryV2],
    ) -> None:
        report = lint_unit_summary_v2(summary, micro_summaries=micro_summaries)
        if not report.ok:
            issue_codes = ", ".join(issue.code for issue in report.issues)
            raise ValueError(f"hybrid unit summary failed lint: {issue_codes}")


class CustomCommandSummarizerBackend:
    name = "custom-command"

    def __init__(
        self,
        command: str,
        *,
        timeout_seconds: int = 60,
        fallback_backend: SummarizerBackend | None = None,
        llm_safety: LLMInputSafetyOptions | None = None,
    ) -> None:
        if not command.strip():
            raise ValueError("custom-command summarizer requires a command")
        try:
            self.command = _split_custom_command(command)
        except ValueError as exc:
            raise ValueError(f"custom-command summarizer has invalid command syntax: {exc}") from exc
        if not self.command:
            raise ValueError("custom-command summarizer requires a command")
        self.timeout_seconds = timeout_seconds
        self.fallback_backend = fallback_backend or HeuristicSummarizerBackend()
        self.llm_safety = llm_safety or LLMInputSafetyOptions()

    def summarize_micro(
        self,
        evidence: MicroEvidenceBundle,
        *,
        schema_version: str,
    ) -> MicroSummaryV2:
        if schema_version != "micro_summary_v2":
            raise ValueError(f"Unsupported micro summary schema_version={schema_version!r}")
        try:
            payload = self._run_command({"kind": "micro", **evidence.to_dict()})
            summary = MicroSummaryV2.from_dict(payload)
            self._raise_if_micro_summary_fails_lint(summary, evidence)
            return summary
        except Exception as exc:
            fallback = self.fallback_backend.summarize_micro(evidence, schema_version=schema_version)
            return _with_fallback_metadata(
                fallback,
                fallback_from=self.name,
                fallback_reason=_summarizer_fallback_reason(exc),
            )

    def summarize_unit(
        self,
        *,
        unit_id: str,
        session_id: str,
        title: str,
        goal: str,
        micro_summaries: list[MicroSummaryV2],
        schema_version: str,
        related_pages: list[str] | None = None,
    ) -> UnitSummaryV2:
        if schema_version != "unit_summary_v2":
            raise ValueError(f"Unsupported unit summary schema_version={schema_version!r}")
        try:
            payload = self._run_command(
                {
                    "kind": "unit",
                    "unit_id": unit_id,
                    "session_id": session_id,
                    "title": title,
                    "goal": goal,
                    "schema_version": schema_version,
                    "related_pages": list(related_pages or []),
                    "micro_summaries": [summary.to_dict() for summary in micro_summaries],
                }
            )
            summary = UnitSummaryV2.from_dict(payload)
            self._raise_if_unit_summary_fails_lint(summary, micro_summaries)
            return summary
        except Exception as exc:
            fallback = self.fallback_backend.summarize_unit(
                unit_id=unit_id,
                session_id=session_id,
                title=title,
                goal=goal,
                micro_summaries=micro_summaries,
                schema_version=schema_version,
                related_pages=list(related_pages or []),
            )
            return _with_fallback_metadata(
                fallback,
                fallback_from=self.name,
                fallback_reason=_summarizer_fallback_reason(exc),
            )

    def _run_command(self, payload: dict[str, object]) -> dict[str, object]:
        result = subprocess.run(
            self.command,
            input=json.dumps(_prepare_llm_request(payload, safety=self.llm_safety), ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
            shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"custom-command summarizer failed with exit_code={result.returncode}: {result.stderr.strip()}"
            )
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"custom-command summarizer returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("custom-command summarizer must return a JSON object")
        return parsed

    def _raise_if_micro_summary_fails_lint(
        self,
        summary: MicroSummaryV2,
        evidence: MicroEvidenceBundle,
    ) -> None:
        raw_bundle = _raw_bundle_from_evidence(evidence)
        report = lint_micro_summary_v2(summary, raw_bundle=raw_bundle)
        if not report.ok:
            issue_codes = ", ".join(issue.code for issue in report.issues)
            raise ValueError(f"custom-command micro summary failed lint: {issue_codes}")

    def _raise_if_unit_summary_fails_lint(
        self,
        summary: UnitSummaryV2,
        micro_summaries: list[MicroSummaryV2],
    ) -> None:
        report = lint_unit_summary_v2(summary, micro_summaries=micro_summaries)
        if not report.ok:
            issue_codes = ", ".join(issue.code for issue in report.issues)
            raise ValueError(f"custom-command unit summary failed lint: {issue_codes}")


class HeuristicSummarizerBackend:
    name = "heuristic"

    def summarize_micro(
        self,
        evidence: MicroEvidenceBundle,
        *,
        schema_version: str,
    ) -> MicroSummaryV2:
        if schema_version != "micro_summary_v2":
            raise ValueError(f"Unsupported micro summary schema_version={schema_version!r}")
        raw_bundle = _raw_bundle_from_evidence(evidence)
        return build_micro_summary_v2(raw_bundle=raw_bundle, micro_id=evidence.micro_id)

    def summarize_unit(
        self,
        *,
        unit_id: str,
        session_id: str,
        title: str,
        goal: str,
        micro_summaries: list[MicroSummaryV2],
        schema_version: str,
        related_pages: list[str] | None = None,
    ) -> UnitSummaryV2:
        if schema_version != "unit_summary_v2":
            raise ValueError(f"Unsupported unit summary schema_version={schema_version!r}")
        return build_unit_summary_v2(
            unit_id=unit_id,
            session_id=session_id,
            title=title,
            goal=goal,
            micro_summaries=micro_summaries,
            related_pages=list(related_pages or []),
        )


def _raw_bundle_from_evidence(evidence: MicroEvidenceBundle) -> dict:
    messages = sorted(
        [*_messages_to_raw(evidence.user_messages), *_messages_to_raw(evidence.assistant_messages)],
        key=lambda message: int(message["id"]),
    )
    return {
        "session": {
            "id": evidence.session_id,
            "source": "unknown",
            "title": evidence.session_id,
            "started_at": None,
            "ended_at": None,
        },
        "messages": messages,
        "slice": {
            "start_message_id": min(evidence.message_ids) if evidence.message_ids else None,
            "end_message_id": max(evidence.message_ids) if evidence.message_ids else None,
        },
        "message_count": len(messages),
    }


def _messages_to_raw(messages: list[EvidenceMessage]) -> list[dict[str, object]]:
    return [
        {"id": message.message_id, "role": message.role, "content": message.content}
        for message in messages
    ]


def _call_router_with_json_repair(
    *,
    router: AgentLLMRouter,
    request: dict[str, object],
    safety: LLMInputSafetyOptions,
    error_label: str,
) -> dict[str, object]:
    response = router(_prepare_llm_request(request, safety=safety))
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
        repaired_response = router(_prepare_llm_request(repair_request, safety=safety))
        return _parse_router_json_response(repaired_response, error_label=error_label)


def _parse_router_json_response(response: dict[str, object] | str, *, error_label: str) -> dict[str, object]:
    if isinstance(response, str):
        parsed = json.loads(response)
    else:
        parsed = response
    if not isinstance(parsed, dict):
        raise ValueError(f"{error_label} must return a JSON object or JSON object string")
    return parsed


def _prepare_llm_request(request: dict[str, object], *, safety: LLMInputSafetyOptions) -> dict[str, object]:
    prepared = _sanitize_value(request, safety=safety)
    if not isinstance(prepared, dict):
        raise TypeError("LLM request must sanitize to a JSON object")
    return _bound_llm_request(prepared, max_chars=safety.max_input_chars)


def _sanitize_value(value, *, safety: LLMInputSafetyOptions):
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            if not safety.allow_code_snippets and key == "code_blocks" and isinstance(item, list):
                sanitized[key] = []
            else:
                sanitized[key] = _sanitize_value(item, safety=safety)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(item, safety=safety) for item in value]
    if isinstance(value, str):
        text = value
        if not safety.allow_code_snippets:
            text = _CODE_FENCE_PATTERN.sub("<CODE_BLOCK_OMITTED>", text)
        if safety.path_policy == "redact":
            text = _redact_local_paths(text)
        if safety.redact:
            text = _redact_llm_text(text)
        return text
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
    bounded = _truncate_strings(request, max_chars=max_chars)
    if _json_size(bounded) <= max_chars:
        return bounded
    compact = {
        "kind": request.get("kind"),
        "schema_version": request.get("schema_version"),
        "routing_hints": request.get("routing_hints", {}),
        "llm_input_truncated": True,
    }
    if _json_size(compact) <= max_chars:
        return compact
    return {"llm_input_truncated": True}


def _truncate_strings(value, *, max_chars: int):
    if isinstance(value, dict):
        return {key: _truncate_strings(item, max_chars=max_chars) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate_strings(item, max_chars=max_chars) for item in value]
    if isinstance(value, str):
        per_string_limit = max(32, max_chars // 8)
        if len(value) <= per_string_limit:
            return value
        keep = max(0, per_string_limit - len(_TRUNCATION_MARKER))
        return value[:keep] + _TRUNCATION_MARKER
    return value


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _summarizer_fallback_reason(exc: Exception) -> str:
    message = str(exc)
    if "failed lint:" in message:
        issue_codes = message.split("failed lint:", 1)[1].strip()
        return f"lint:{issue_codes}"
    if "custom-command summarizer failed" in message:
        return "command_failed"
    if "invalid JSON" in message or isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    return type(exc).__name__


def _with_fallback_metadata(
    summary: MicroSummaryV2 | UnitSummaryV2,
    *,
    fallback_from: str,
    fallback_reason: str,
):
    if summary.metadata is None:
        return summary
    return replace(
        summary,
        metadata=replace(
            summary.metadata,
            fallback_from=fallback_from,
            fallback_reason=fallback_reason,
        ),
    )


def get_summarizer_backend(
    name: str = "heuristic",
    *,
    command: str | None = None,
    agent_llm_router: AgentLLMRouter | None = None,
    routing_hints: dict[str, object] | None = None,
    llm_safety: LLMInputSafetyOptions | None = None,
) -> SummarizerBackend:
    normalized = name.strip().lower()
    if normalized == "heuristic":
        return HeuristicSummarizerBackend()
    if normalized == "custom-command":
        return CustomCommandSummarizerBackend(command=command or "", llm_safety=llm_safety)
    if normalized == "agent-llm":
        if agent_llm_router is None:
            raise ValueError("agent-llm summarizer requires an injected Agent LLM router")
        return AgentLLMSummarizerBackend(router=agent_llm_router, routing_hints=routing_hints, llm_safety=llm_safety)
    if normalized == "hybrid":
        if agent_llm_router is None:
            raise ValueError("hybrid summarizer requires an injected Agent LLM router")
        return HybridSummarizerBackend(router=agent_llm_router, routing_hints=routing_hints, llm_safety=llm_safety)
    raise ValueError(f"Unsupported summarizer backend: {name}")
