from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.models import EvidenceBackedText, MicroSummaryV2, SummaryMetadata, UnitSummaryV2  # noqa: E402
from agent_context_substrate.paths import HarnessPaths  # noqa: E402
from agent_context_substrate.summary_pipeline import (  # noqa: E402
    SummaryOptions,
    SummaryPipelineInvariantError,
    build_v2_summary_artifacts,
)


class CountingBackend:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def summarize_micro(self, evidence, *, schema_version: str) -> MicroSummaryV2:
        self.calls.append("micro")
        return MicroSummaryV2(
            micro_id=evidence.micro_id,
            session_id=evidence.session_id,
            message_ids=list(evidence.message_ids),
            recovery_summary="Recovered implementation context.",
            knowledge_summary="A reusable SummaryPipeline service is being introduced.",
            retrieval_summary="SummaryPipeline service build_v2_summary_artifacts",
            user_intent="Introduce SummaryPipeline.",
            assistant_outcome="Created service-level v2 summary artifacts.",
            metadata=SummaryMetadata(
                mode="test-backend",
                schema_version=schema_version,
                prompt_version=None,
                model=None,
                input_hash="input",
                created_at="2026-05-08T00:00:00+00:00",
            ),
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
        self.calls.append("unit")
        return UnitSummaryV2(
            unit_id=unit_id,
            session_id=session_id,
            title=title,
            goal=goal,
            state="SummaryPipeline artifacts exported.",
            micro_ids=[summary.micro_id for summary in micro_summaries],
            related_pages=list(related_pages or []),
            metadata=SummaryMetadata(
                mode="test-backend",
                schema_version=schema_version,
                prompt_version=None,
                model=None,
                input_hash="input",
                created_at="2026-05-08T00:00:00+00:00",
            ),
        )


class InvalidMicroEvidenceBackend(CountingBackend):
    def summarize_micro(self, evidence, *, schema_version: str) -> MicroSummaryV2:
        self.calls.append("micro")
        return MicroSummaryV2(
            micro_id=evidence.micro_id,
            session_id=evidence.session_id,
            message_ids=list(evidence.message_ids),
            recovery_summary="Recovered implementation context.",
            knowledge_summary="A reusable SummaryPipeline service is being introduced.",
            retrieval_summary="SummaryPipeline service build_v2_summary_artifacts",
            user_intent="Introduce SummaryPipeline.",
            assistant_outcome="Created service-level v2 summary artifacts.",
            decisions=[
                EvidenceBackedText(
                    text="Decision cites a non-existent message.",
                    evidence_message_ids=[999],
                    confidence=0.8,
                )
            ],
            metadata=SummaryMetadata(
                mode="invalid-test-backend",
                schema_version=schema_version,
                prompt_version=None,
                model=None,
                input_hash="input",
                created_at="2026-05-08T00:00:00+00:00",
            ),
        )


class InvalidUnitReferenceBackend(CountingBackend):
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
        self.calls.append("unit")
        return UnitSummaryV2(
            unit_id=unit_id,
            session_id=session_id,
            title=title,
            goal=goal,
            state="Invalid unit summary references a missing micro summary.",
            micro_ids=["missing-micro"],
            related_pages=list(related_pages or []),
            metadata=SummaryMetadata(
                mode="invalid-test-backend",
                schema_version=schema_version,
                prompt_version=None,
                model=None,
                input_hash="input",
                created_at="2026-05-08T00:00:00+00:00",
            ),
        )


def _raw_bundle() -> dict[str, object]:
    return {
        "session": {"id": "session-1", "source": "telegram", "title": "SummaryPipeline"},
        "messages": [
            {
                "id": 1,
                "role": "user",
                "content": "Please introduce summary_pipeline.py for build_v2_summary_artifacts.",
                "timestamp": 1776395278.0,
            },
            {
                "id": 2,
                "role": "assistant",
                "content": "I will extract the v2 summary export flow from cli.py.",
                "timestamp": 1776395280.0,
            },
        ],
        "slice": {"start_message_id": 1, "end_message_id": 2},
        "message_count": 2,
    }


def test_build_v2_summary_artifacts_exports_evidence_and_cache_then_reuses_cache(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    options = SummaryOptions(
        session_id="session-1",
        packet_id="packet-1",
        unit_title="Unit",
        goal="Keep CLI thin.",
        related_pages=["Architecture"],
        summary_mode="heuristic",
        routing_hints={"model": "fast", "budget": "small"},
        summary_cache=True,
    )
    calls: list[str] = []

    first_result = build_v2_summary_artifacts(
        raw_bundle=_raw_bundle(),
        paths=paths,
        options=options,
        backend_factory=lambda mode, command, router, routing_hints, llm_safety: CountingBackend(calls),
    )

    assert calls == ["micro", "unit"]
    assert first_result.evidence_path.exists()
    evidence_payload = json.loads(first_result.evidence_path.read_text(encoding="utf-8"))
    assert evidence_payload["session_id"] == "session-1"
    assert evidence_payload["micro_id"] == "packet-1-micro-1"
    cache_files = list((paths.project_root / "data" / "cache" / "summaries").glob("*.json"))
    assert len(cache_files) == 1
    cache_payload = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert cache_payload["cache_input"]["routing_hints"] == {"model": "fast", "budget": "small"}

    second_result = build_v2_summary_artifacts(
        raw_bundle=_raw_bundle(),
        paths=paths,
        options=options,
        backend_factory=lambda mode, command, router, routing_hints: (_ for _ in ()).throw(AssertionError("cache miss")),
    )

    assert second_result.micro_path.exists()
    assert second_result.unit_path.exists()
    assert second_result.evidence_path == first_result.evidence_path
    assert calls == ["micro", "unit"]


def test_build_v2_summary_artifacts_rejects_unsafe_packet_id_before_export(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    options = SummaryOptions(
        session_id="session-1",
        packet_id="../escape",
        unit_title="Unit",
        goal="Keep generated summary artifact ids safe.",
    )
    calls: list[str] = []

    with pytest.raises(SummaryPipelineInvariantError, match="Unsafe packet id"):
        build_v2_summary_artifacts(
            raw_bundle=_raw_bundle(),
            paths=paths,
            options=options,
            backend_factory=lambda mode, command, router, routing_hints, llm_safety: CountingBackend(calls),
        )

    assert calls == []
    assert not (paths.project_root / "data").exists()


def test_build_v2_summary_artifacts_rejects_mismatched_session_id_before_export(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    options = SummaryOptions(
        session_id="other-session",
        packet_id="packet-1",
        unit_title="Unit",
        goal="Keep generated summary artifacts tied to the source session.",
    )
    calls: list[str] = []

    with pytest.raises(SummaryPipelineInvariantError, match="session_id"):
        build_v2_summary_artifacts(
            raw_bundle=_raw_bundle(),
            paths=paths,
            options=options,
            backend_factory=lambda mode, command, router, routing_hints, llm_safety: CountingBackend(calls),
        )

    assert calls == []
    assert not (paths.project_root / "data").exists()


def test_build_v2_summary_artifacts_rejects_unit_summary_with_unknown_micro_reference(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    options = SummaryOptions(
        session_id="session-1",
        packet_id="packet-1",
        unit_title="Unit",
        goal="Keep V2 summary artifacts valid.",
    )
    calls: list[str] = []

    with pytest.raises(SummaryPipelineInvariantError, match="missing-micro"):
        build_v2_summary_artifacts(
            raw_bundle=_raw_bundle(),
            paths=paths,
            options=options,
            backend_factory=lambda mode, command, router, routing_hints, llm_safety: InvalidUnitReferenceBackend(calls),
        )

    assert calls == ["micro", "unit"]
    assert not (paths.project_root / "data" / "exports" / "summaries" / "packet-1-unit-v2.json").exists()


def test_build_v2_summary_artifacts_rejects_micro_summary_with_unknown_evidence_id(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    options = SummaryOptions(
        session_id="session-1",
        packet_id="packet-1",
        unit_title="Unit",
        goal="Keep V2 summary artifacts grounded.",
    )
    calls: list[str] = []

    with pytest.raises(SummaryPipelineInvariantError, match="evidence_exists"):
        build_v2_summary_artifacts(
            raw_bundle=_raw_bundle(),
            paths=paths,
            options=options,
            backend_factory=lambda mode, command, router, routing_hints, llm_safety: InvalidMicroEvidenceBackend(calls),
        )

    assert calls == ["micro"]
    assert not (paths.project_root / "data" / "exports" / "summaries" / "packet-1-micro-v2.json").exists()
