from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from .codex_cli import codex_command_available, resolve_codex_command
from .codex_exec import CodexExecRuntime
from .llm_runtime import (
    AgentLLMRouter,
    LLMInputSafetyOptions,
    call_router_with_json_repair,
    prepare_llm_request,
)
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


# Backward-compatible aliases for integrations that imported the old private names.
_call_router_with_json_repair = call_router_with_json_repair
_prepare_llm_request = prepare_llm_request


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


class CodexCliSummarizerBackend:
    name = "codex-cli"

    def __init__(
        self,
        *,
        codex_command: str | None = None,
        project_root: Path | str | None = None,
        timeout_seconds: int = 90,
        fallback_backend: SummarizerBackend | None = None,
        routing_hints: dict[str, object] | None = None,
        llm_safety: LLMInputSafetyOptions | None = None,
    ) -> None:
        self.codex_command = codex_command
        self.project_root = Path(project_root).expanduser() if project_root is not None else Path.cwd()
        self.timeout_seconds = max(1, int(timeout_seconds))
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
            payload = self._run_codex_exec(
                kind="micro",
                request={
                    "kind": "micro",
                    "schema_version": schema_version,
                    "evidence": evidence.to_dict(),
                    "routing_hints": self.routing_hints,
                },
                schema=_micro_summary_json_schema(),
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
            payload = self._run_codex_exec(
                kind="unit",
                request={
                    "kind": "unit",
                    "unit_id": unit_id,
                    "session_id": session_id,
                    "title": title,
                    "goal": goal,
                    "schema_version": schema_version,
                    "related_pages": list(related_pages or []),
                    "micro_summaries": [summary.to_dict() for summary in micro_summaries],
                    "routing_hints": self.routing_hints,
                },
                schema=_unit_summary_json_schema(),
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

    def _run_codex_exec(
        self,
        *,
        kind: str,
        request: dict[str, object],
        schema: dict[str, object],
    ) -> dict[str, object]:
        prepared_request = _prepare_llm_request(request, safety=self.llm_safety)
        request_json = json.dumps(prepared_request, ensure_ascii=False, sort_keys=True)
        runtime = CodexExecRuntime(
            codex_command=self.codex_command,
            project_root=self.project_root,
            timeout_seconds=self.timeout_seconds,
            model=str(self.routing_hints["model"]) if self.routing_hints.get("model") else None,
        )
        return runtime.run_structured(
            prompt=_codex_summary_prompt(kind=kind, request_json=request_json),
            schema=schema,
            schema_filename=f"{kind}-summary-schema.json",
            error_label="codex-cli summarizer",
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
            raise ValueError(f"codex-cli micro summary failed lint: {issue_codes}")

    def _raise_if_unit_summary_fails_lint(
        self,
        summary: UnitSummaryV2,
        micro_summaries: list[MicroSummaryV2],
    ) -> None:
        report = lint_unit_summary_v2(summary, micro_summaries=micro_summaries)
        if not report.ok:
            issue_codes = ", ".join(issue.code for issue in report.issues)
            raise ValueError(f"codex-cli unit summary failed lint: {issue_codes}")


class AutoSummarizerBackend:
    name = "auto"

    def __init__(
        self,
        *,
        routing_hints: dict[str, object] | None = None,
        llm_safety: LLMInputSafetyOptions | None = None,
        fallback_backend: SummarizerBackend | None = None,
    ) -> None:
        self.routing_hints = dict(routing_hints or {})
        self.llm_safety = llm_safety or LLMInputSafetyOptions()
        self.fallback_backend = fallback_backend or HeuristicSummarizerBackend()
        self.codex_command = _codex_cli_command_hint(self.routing_hints)
        self.project_root = Path(str(self.routing_hints.get("codex_project_root") or Path.cwd()))
        self.timeout_seconds = _positive_int_hint(self.routing_hints, "codex_timeout_seconds", default=90)

    def summarize_micro(
        self,
        evidence: MicroEvidenceBundle,
        *,
        schema_version: str,
    ) -> MicroSummaryV2:
        if not _codex_cli_available(self.codex_command):
            fallback = self.fallback_backend.summarize_micro(evidence, schema_version=schema_version)
            return _with_fallback_metadata(
                fallback,
                fallback_from=self.name,
                fallback_reason="codex_cli_unavailable",
            )
        return self._codex_backend().summarize_micro(evidence, schema_version=schema_version)

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
        if not _codex_cli_available(self.codex_command):
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
                fallback_reason="codex_cli_unavailable",
            )
        return self._codex_backend().summarize_unit(
            unit_id=unit_id,
            session_id=session_id,
            title=title,
            goal=goal,
            micro_summaries=micro_summaries,
            schema_version=schema_version,
            related_pages=list(related_pages or []),
        )

    def _codex_backend(self) -> CodexCliSummarizerBackend:
        return CodexCliSummarizerBackend(
            codex_command=self.codex_command,
            project_root=self.project_root,
            timeout_seconds=self.timeout_seconds,
            fallback_backend=self.fallback_backend,
            routing_hints=self.routing_hints,
            llm_safety=self.llm_safety,
        )


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


def _summarizer_fallback_reason(exc: Exception) -> str:
    message = str(exc)
    if "failed lint:" in message:
        issue_codes = message.split("failed lint:", 1)[1].strip()
        return f"lint:{issue_codes}"
    if "custom-command summarizer failed" in message:
        return "command_failed"
    if "codex-cli summarizer failed" in message:
        return "command_failed"
    if "codex-cli summarizer unavailable" in message:
        return "codex_cli_unavailable"
    if "invalid JSON" in message or isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    return type(exc).__name__


def _codex_summary_prompt(*, kind: str, request_json: str) -> str:
    return (
        "Use this Agent Context Substrate summary input JSON: "
        f"{request_json}\n\nReturn only one strict JSON object for "
        f"the {kind} summary. Use only provided evidence, preserve message ids, "
        "do not invent files or claims, and do not include markdown fences. "
        "Preserve unresolved explicit_questions in open_questions. "
        "Only copy files, entities, and concepts that appear verbatim in the provided evidence."
    )


def _codex_cli_available(command: str | None = None) -> bool:
    if command:
        return codex_command_available(command)
    return resolve_codex_command() is not None


def _codex_cli_command_hint(routing_hints: dict[str, object]) -> str | None:
    value = routing_hints.get("codex_cli_command")
    if value is None:
        return os.environ.get("AGENT_CONTEXT_SUBSTRATE_CODEX_CLI")
    text = str(value).strip()
    return text or None


def _positive_int_hint(routing_hints: dict[str, object], key: str, *, default: int) -> int:
    try:
        value = int(routing_hints.get(key, default))
    except (TypeError, ValueError):
        return default
    return max(1, value)


def _summary_metadata_json_schema(schema_version: str) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["codex-cli"]},
            "schema_version": {"type": "string", "const": schema_version},
            "prompt_version": {"type": ["string", "null"]},
            "model": {"type": ["string", "null"]},
            "input_hash": {"type": "string"},
            "created_at": {"type": "string"},
            "confidence": {"type": ["number", "null"]},
            "fallback_from": {"type": ["string", "null"]},
            "fallback_reason": {"type": ["string", "null"]},
        },
        "required": [
            "mode",
            "schema_version",
            "prompt_version",
            "model",
            "input_hash",
            "created_at",
            "confidence",
            "fallback_from",
            "fallback_reason",
        ],
        "additionalProperties": False,
    }


def _evidence_backed_text_json_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "evidence_message_ids": {"type": "array", "items": {"type": "integer"}},
            "confidence": {"type": "number"},
        },
        "required": ["text", "evidence_message_ids", "confidence"],
        "additionalProperties": False,
    }


def _raw_session_reference_json_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "message_ids": {"type": "array", "items": {"type": "integer"}},
            "source": {"type": "string"},
            "started_at": {"type": ["string", "null"]},
            "ended_at": {"type": ["string", "null"]},
            "title": {"type": ["string", "null"]},
        },
        "required": ["session_id", "message_ids", "source", "started_at", "ended_at", "title"],
        "additionalProperties": False,
    }


def _micro_summary_json_schema() -> dict[str, object]:
    required = [
        "micro_id",
        "session_id",
        "message_ids",
        "recovery_summary",
        "knowledge_summary",
        "retrieval_summary",
        "user_intent",
        "assistant_outcome",
        "decisions",
        "claims",
        "action_items",
        "open_questions",
        "files",
        "entities",
        "concepts",
        "metadata",
        "provenance",
    ]
    evidence_text = _evidence_backed_text_json_schema()
    return {
        "type": "object",
        "properties": {
            "micro_id": {"type": "string"},
            "session_id": {"type": "string"},
            "message_ids": {"type": "array", "items": {"type": "integer"}},
            "recovery_summary": {"type": "string"},
            "knowledge_summary": {"type": "string"},
            "retrieval_summary": {"type": "string"},
            "user_intent": {"type": ["string", "null"]},
            "assistant_outcome": {"type": ["string", "null"]},
            "decisions": {"type": "array", "items": evidence_text},
            "claims": {"type": "array", "items": evidence_text},
            "action_items": {"type": "array", "items": evidence_text},
            "open_questions": {"type": "array", "items": {"type": "string"}},
            "files": {"type": "array", "items": {"type": "string"}},
            "entities": {"type": "array", "items": {"type": "string"}},
            "concepts": {"type": "array", "items": {"type": "string"}},
            "metadata": _summary_metadata_json_schema("micro_summary_v2"),
            "provenance": {"anyOf": [{"type": "null"}, _raw_session_reference_json_schema()]},
        },
        "required": required,
        "additionalProperties": False,
    }


def _unit_summary_json_schema() -> dict[str, object]:
    evidence_text = _evidence_backed_text_json_schema()
    return {
        "type": "object",
        "properties": {
            "unit_id": {"type": "string"},
            "session_id": {"type": "string"},
            "title": {"type": "string"},
            "goal": {"type": "string"},
            "state": {"type": "string"},
            "decisions": {"type": "array", "items": evidence_text},
            "progress": {"type": "array", "items": {"type": "string"}},
            "next_actions": {"type": "array", "items": {"type": "string"}},
            "open_questions": {"type": "array", "items": {"type": "string"}},
            "risk_notes": {"type": "array", "items": {"type": "string"}},
            "wiki_candidates": {"type": "array", "items": evidence_text},
            "micro_ids": {"type": "array", "items": {"type": "string"}},
            "related_pages": {"type": "array", "items": {"type": "string"}},
            "metadata": _summary_metadata_json_schema("unit_summary_v2"),
            "provenance": {"anyOf": [{"type": "null"}, _raw_session_reference_json_schema()]},
        },
        "required": [
            "unit_id",
            "session_id",
            "title",
            "goal",
            "state",
            "decisions",
            "progress",
            "next_actions",
            "open_questions",
            "risk_notes",
            "wiki_candidates",
            "micro_ids",
            "related_pages",
            "metadata",
            "provenance",
        ],
        "additionalProperties": False,
    }


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
    if normalized == "auto":
        return AutoSummarizerBackend(routing_hints=routing_hints, llm_safety=llm_safety)
    if normalized in {"codex-cli", "codex-exec"}:
        hints = dict(routing_hints or {})
        return CodexCliSummarizerBackend(
            codex_command=_codex_cli_command_hint(hints),
            project_root=Path(str(hints.get("codex_project_root") or Path.cwd())),
            timeout_seconds=_positive_int_hint(hints, "codex_timeout_seconds", default=90),
            routing_hints=hints,
            llm_safety=llm_safety,
        )
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
