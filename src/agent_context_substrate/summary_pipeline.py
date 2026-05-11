from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .evidence import build_micro_evidence_bundle, export_micro_evidence_bundle
from .models import MicroSummaryV2, UnitSummaryV2
from .paths import HarnessPaths
from .safe_paths import safe_artifact_stem, safe_child_path
from .summarizer_backends import AgentLLMRouter, SummarizerBackend, get_summarizer_backend


BackendFactory = Callable[[str, str | None, AgentLLMRouter | None, dict[str, object] | None], SummarizerBackend]


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


@dataclass(frozen=True)
class SummaryArtifactResult:
    micro_path: Path
    unit_path: Path
    evidence_path: Path

    def as_tuple(self) -> tuple[Path, Path, Path]:
        return self.micro_path, self.unit_path, self.evidence_path


def build_v2_summary_artifacts(
    *,
    raw_bundle: dict[str, Any],
    paths: HarnessPaths,
    options: SummaryOptions,
    backend_factory: BackendFactory | None = None,
) -> SummaryArtifactResult:
    """Build and export evidence plus V2 micro/unit summary artifacts."""

    evidence = build_micro_evidence_bundle(raw_bundle=raw_bundle, micro_id=f"{options.packet_id}-micro-1")
    evidence_path = export_micro_evidence_bundle(bundle=evidence, exports_dir=paths.exports_dir)
    cache_input = _summary_cache_input(options=options, evidence_dict=evidence.to_dict())
    cache_key = _summary_cache_key(cache_input)
    cache_path = _summary_cache_path(paths=paths, cache_key=cache_key)

    if options.summary_cache and cache_path.exists():
        micro_summary, unit_summary = _load_summary_cache(cache_path)
        micro_path, unit_path = _export_summary_files(
            paths=paths,
            packet_id=options.packet_id,
            micro_summary=micro_summary,
            unit_summary=unit_summary,
        )
        return SummaryArtifactResult(micro_path=micro_path, unit_path=unit_path, evidence_path=evidence_path)

    backend = _build_backend(options=options, backend_factory=backend_factory)
    micro_summary = backend.summarize_micro(evidence, schema_version="micro_summary_v2")
    unit_summary = backend.summarize_unit(
        unit_id=f"{options.packet_id}-unit-1",
        session_id=options.session_id,
        title=options.unit_title,
        goal=options.goal,
        micro_summaries=[micro_summary],
        schema_version="unit_summary_v2",
        related_pages=list(options.related_pages),
    )
    micro_path, unit_path = _export_summary_files(
        paths=paths,
        packet_id=options.packet_id,
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


def _build_backend(*, options: SummaryOptions, backend_factory: BackendFactory | None) -> SummarizerBackend:
    if backend_factory is not None:
        return backend_factory(
            options.summary_mode,
            options.summarizer_command,
            options.agent_llm_router,
            dict(options.routing_hints),
        )
    return get_summarizer_backend(
        options.summary_mode,
        command=options.summarizer_command,
        agent_llm_router=options.agent_llm_router,
        routing_hints=dict(options.routing_hints),
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
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    return MicroSummaryV2.from_dict(payload["micro_summary"]), UnitSummaryV2.from_dict(payload["unit_summary"])


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
