from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import replace
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


class AgentLLMSummarizerBackend:
    name = "agent-llm"

    def __init__(
        self,
        *,
        router: AgentLLMRouter,
        fallback_backend: SummarizerBackend | None = None,
        routing_hints: dict[str, object] | None = None,
    ) -> None:
        self.router = router
        self.fallback_backend = fallback_backend or HeuristicSummarizerBackend()
        self.routing_hints = dict(routing_hints or {})

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
        response = self.router(request)
        if isinstance(response, str):
            parsed = json.loads(response)
        else:
            parsed = response
        if not isinstance(parsed, dict):
            raise ValueError("Agent LLM router must return a JSON object or JSON object string")
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
    ) -> None:
        self.router = router
        self.heuristic_backend = heuristic_backend or HeuristicSummarizerBackend()
        self.routing_hints = dict(routing_hints or {})

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
        response = self.router(request)
        if isinstance(response, str):
            parsed = json.loads(response)
        else:
            parsed = response
        if not isinstance(parsed, dict):
            raise ValueError("Hybrid Agent LLM router must return a JSON object or JSON object string")
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
    ) -> None:
        if not command.strip():
            raise ValueError("custom-command summarizer requires a command")
        try:
            self.command = shlex.split(command)
        except ValueError as exc:
            raise ValueError(f"custom-command summarizer has invalid command syntax: {exc}") from exc
        if not self.command:
            raise ValueError("custom-command summarizer requires a command")
        self.timeout_seconds = timeout_seconds
        self.fallback_backend = fallback_backend or HeuristicSummarizerBackend()

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
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
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
) -> SummarizerBackend:
    normalized = name.strip().lower()
    if normalized == "heuristic":
        return HeuristicSummarizerBackend()
    if normalized == "custom-command":
        return CustomCommandSummarizerBackend(command=command or "")
    if normalized == "agent-llm":
        if agent_llm_router is None:
            raise ValueError("agent-llm summarizer requires an injected Agent LLM router")
        return AgentLLMSummarizerBackend(router=agent_llm_router, routing_hints=routing_hints)
    if normalized == "hybrid":
        if agent_llm_router is None:
            raise ValueError("hybrid summarizer requires an injected Agent LLM router")
        return HybridSummarizerBackend(router=agent_llm_router, routing_hints=routing_hints)
    raise ValueError(f"Unsupported summarizer backend: {name}")
