from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .evidence import build_micro_evidence_bundle, export_micro_evidence_bundle
from .models import MicroSummaryV2, UnitSummaryV2
from .paths import HarnessPaths
from .safe_paths import safe_artifact_stem, safe_child_path
from .session_bundle import SessionBundle, ensure_session_bundle, resolve_session_bundle
from .summarizer_backends import AgentLLMRouter, LLMInputSafetyOptions, SummarizerBackend, get_summarizer_backend
from .summary_lint import SummaryLintReport, lint_micro_summary_v2, lint_unit_summary_v2


BackendFactory = Callable[
    [str, str | None, AgentLLMRouter | None, dict[str, object] | None, LLMInputSafetyOptions],
    SummarizerBackend,
]


class SummaryPipelineInvariantError(ValueError):
    """Raised when V2 summary artifacts violate pipeline-level invariants."""


@dataclass(frozen=True)
class _SummaryArtifactIds:
    packet_id: str
    micro_id: str
    unit_id: str


@dataclass(frozen=True)
class SummaryOptions:
    session_id: str
    packet_id: str
    unit_title: str
    goal: str
    related_pages: list[str] = field(default_factory=list)
    summary_mode: str = "heuristic"
    summarizer_command: str | None = None
    routing_hints: dict[str, object] = field(default_factory=dict)
    summary_cache: bool = False
    agent_llm_router: AgentLLMRouter | None = None
    llm_safety: LLMInputSafetyOptions = field(default_factory=LLMInputSafetyOptions)


@dataclass(frozen=True)
class SummaryArtifactResult:
    micro_path: Path
    unit_path: Path
    evidence_path: Path

    def as_tuple(self) -> tuple[Path, Path, Path]:
        return self.micro_path, self.unit_path, self.evidence_path


def build_v2_summary_artifacts(
    *,
    raw_bundle: Mapping[str, Any] | SessionBundle | None = None,
    session_bundle: Mapping[str, Any] | SessionBundle | None = None,
    paths: HarnessPaths,
    options: SummaryOptions,
    backend_factory: BackendFactory | None = None,
) -> SummaryArtifactResult:
    """Build and export evidence plus V2 micro/unit summary artifacts."""

    session_bundle = resolve_session_bundle(raw_bundle, session_bundle=session_bundle)
    artifact_ids = _summary_artifact_ids(options=options)
    _validate_summary_source_session(session_bundle=session_bundle, options=options)
    evidence = build_micro_evidence_bundle(session_bundle=session_bundle, micro_id=artifact_ids.micro_id)
    _validate_evidence_artifact_ids(session_id=evidence.session_id, micro_id=evidence.micro_id)
    cache_input = _summary_cache_input(options=options, evidence_dict=evidence.to_dict())
    cache_key = _summary_cache_key(cache_input)
    cache_path = _summary_cache_path(paths=paths, cache_key=cache_key)

    if options.summary_cache and cache_path.exists():
        micro_summary, unit_summary = _load_summary_cache(cache_path)
        _validate_micro_summary(
            session_bundle=session_bundle,
            micro_summary=micro_summary,
            expected_session_id=options.session_id,
        )
        _validate_unit_micro_references(unit_summary=unit_summary, micro_summaries=[micro_summary])
        _validate_unit_summary(
            unit_summary=unit_summary,
            micro_summaries=[micro_summary],
            expected_session_id=options.session_id,
        )
        evidence_path = export_micro_evidence_bundle(bundle=evidence, exports_dir=paths.exports_dir)
        micro_path, unit_path = _export_summary_files(
            paths=paths,
            packet_id=artifact_ids.packet_id,
            micro_summary=micro_summary,
            unit_summary=unit_summary,
        )
        return SummaryArtifactResult(micro_path=micro_path, unit_path=unit_path, evidence_path=evidence_path)

    backend = _build_backend(options=options, backend_factory=backend_factory)
    micro_summary = backend.summarize_micro(evidence, schema_version="micro_summary_v2")
    _validate_micro_summary(
        session_bundle=session_bundle,
        micro_summary=micro_summary,
        expected_session_id=options.session_id,
    )
    unit_summary = backend.summarize_unit(
        unit_id=artifact_ids.unit_id,
        session_id=options.session_id,
        title=options.unit_title,
        goal=options.goal,
        micro_summaries=[micro_summary],
        schema_version="unit_summary_v2",
        related_pages=list(options.related_pages),
    )
    _validate_unit_micro_references(unit_summary=unit_summary, micro_summaries=[micro_summary])
    _validate_unit_summary(
        unit_summary=unit_summary,
        micro_summaries=[micro_summary],
        expected_session_id=options.session_id,
    )
    evidence_path = export_micro_evidence_bundle(bundle=evidence, exports_dir=paths.exports_dir)
    micro_path, unit_path = _export_summary_files(
        paths=paths,
        packet_id=artifact_ids.packet_id,
        micro_summary=micro_summary,
        unit_summary=unit_summary,
    )
    if options.summary_cache:
        _write_summary_cache(
            cache_path=cache_path,
            cache_key=cache_key,
            cache_input=cache_input,
            micro_summary=micro_summary,
            unit_summary=unit_summary,
        )
    return SummaryArtifactResult(micro_path=micro_path, unit_path=unit_path, evidence_path=evidence_path)


def _raise_for_lint_issues(*, artifact: str, report: SummaryLintReport) -> None:
    if report.ok:
        return
    codes = ",".join(issue.code for issue in report.issues)
    raise SummaryPipelineInvariantError(f"{artifact} failed summary lint: {codes}")


def _summary_artifact_ids(*, options: SummaryOptions) -> _SummaryArtifactIds:
    try:
        packet_id = safe_artifact_stem(options.packet_id, label="packet id")
        micro_id = safe_artifact_stem(f"{packet_id}-micro-1", label="micro id")
        unit_id = safe_artifact_stem(f"{packet_id}-unit-1", label="unit id")
    except ValueError as exc:
        raise SummaryPipelineInvariantError(str(exc)) from exc
    return _SummaryArtifactIds(packet_id=packet_id, micro_id=micro_id, unit_id=unit_id)


def _validate_summary_source_session(*, session_bundle: Mapping[str, Any] | SessionBundle, options: SummaryOptions) -> None:
    bundle = ensure_session_bundle(session_bundle)
    raw_session_id = bundle.session_id
    if raw_session_id == options.session_id:
        return
    raise SummaryPipelineInvariantError(
        f"SummaryOptions session_id {options.session_id!r} does not match session_bundle session_id {raw_session_id!r}"
    )


def _validate_evidence_artifact_ids(*, session_id: str, micro_id: str) -> None:
    try:
        safe_artifact_stem(session_id, label="session id")
        safe_artifact_stem(micro_id, label="micro id")
    except ValueError as exc:
        raise SummaryPipelineInvariantError(str(exc)) from exc


def _validate_summary_session_id(*, artifact: str, summary_session_id: str, expected_session_id: str) -> None:
    if summary_session_id == expected_session_id:
        return
    raise SummaryPipelineInvariantError(
        f"{artifact} session_id {summary_session_id!r} does not match expected session_id {expected_session_id!r}"
    )


def _validate_micro_summary(
    *,
    session_bundle: Mapping[str, Any] | SessionBundle,
    micro_summary: MicroSummaryV2,
    expected_session_id: str,
) -> None:
    _validate_summary_session_id(
        artifact="micro_summary",
        summary_session_id=micro_summary.session_id,
        expected_session_id=expected_session_id,
    )
    _raise_for_lint_issues(
        artifact="micro_summary",
        report=lint_micro_summary_v2(micro_summary, session_bundle=session_bundle),
    )


def _validate_unit_summary(
    *,
    unit_summary: UnitSummaryV2,
    micro_summaries: list[MicroSummaryV2],
    expected_session_id: str,
) -> None:
    _validate_summary_session_id(
        artifact="unit_summary",
        summary_session_id=unit_summary.session_id,
        expected_session_id=expected_session_id,
    )
    _raise_for_lint_issues(
        artifact="unit_summary",
        report=lint_unit_summary_v2(unit_summary, micro_summaries=micro_summaries),
    )


def _validate_unit_micro_references(*, unit_summary: UnitSummaryV2, micro_summaries: list[MicroSummaryV2]) -> None:
    valid_micro_ids = {summary.micro_id for summary in micro_summaries}
    missing_micro_ids = [micro_id for micro_id in unit_summary.micro_ids if micro_id not in valid_micro_ids]
    if missing_micro_ids:
        raise SummaryPipelineInvariantError(
            f"UnitSummaryV2 {unit_summary.unit_id!r} references unknown micro_ids: {missing_micro_ids}"
        )


def _build_backend(*, options: SummaryOptions, backend_factory: BackendFactory | None) -> SummarizerBackend:
    if backend_factory is not None:
        return backend_factory(
            options.summary_mode,
            options.summarizer_command,
            options.agent_llm_router,
            dict(options.routing_hints),
            options.llm_safety,
        )
    return get_summarizer_backend(
        options.summary_mode,
        command=options.summarizer_command,
        agent_llm_router=options.agent_llm_router,
        routing_hints=dict(options.routing_hints),
        llm_safety=options.llm_safety,
    )


def _summary_cache_input(*, options: SummaryOptions, evidence_dict: dict[str, object]) -> dict[str, object]:
    return {
        "session_id": options.session_id,
        "packet_id": options.packet_id,
        "unit_title": options.unit_title,
        "goal": options.goal,
        "related_pages": list(options.related_pages),
        "summary_mode": options.summary_mode,
        "summarizer_command": options.summarizer_command,
        "routing_hints": dict(options.routing_hints),
        "llm_safety": {
            "redact": options.llm_safety.redact,
            "max_input_chars": options.llm_safety.max_input_chars,
            "allow_code_snippets": options.llm_safety.allow_code_snippets,
            "path_policy": options.llm_safety.path_policy,
        },
        "micro_schema_version": "micro_summary_v2",
        "unit_schema_version": "unit_summary_v2",
        "evidence": evidence_dict,
    }


def _summary_cache_key(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _summary_cache_path(*, paths: HarnessPaths, cache_key: str) -> Path:
    return paths.project_root / "data" / "cache" / "summaries" / f"{cache_key}.json"


def _load_summary_cache(cache_path: Path) -> tuple[MicroSummaryV2, UnitSummaryV2]:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        return MicroSummaryV2.from_dict(payload["micro_summary"]), UnitSummaryV2.from_dict(payload["unit_summary"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SummaryPipelineInvariantError("Malformed summary cache payload") from exc


def _write_summary_cache(
    *,
    cache_path: Path,
    cache_key: str,
    cache_input: dict[str, object],
    micro_summary: MicroSummaryV2,
    unit_summary: UnitSummaryV2,
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "cache_key": cache_key,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "cache_input": cache_input,
                "micro_summary": micro_summary.to_dict(),
                "unit_summary": unit_summary.to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _export_summary_files(
    *,
    paths: HarnessPaths,
    packet_id: str,
    micro_summary: MicroSummaryV2,
    unit_summary: UnitSummaryV2,
) -> tuple[Path, Path]:
    safe_packet_id = safe_artifact_stem(packet_id, label="packet id")
    summary_dir = paths.exports_dir / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    micro_path = safe_child_path(summary_dir, f"{safe_packet_id}-micro-v2", ".json", label="summary artifact id")
    unit_path = safe_child_path(summary_dir, f"{safe_packet_id}-unit-v2", ".json", label="summary artifact id")
    micro_path.write_text(json.dumps(micro_summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    unit_path.write_text(json.dumps(unit_summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return micro_path, unit_path
