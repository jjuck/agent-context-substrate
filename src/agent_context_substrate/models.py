from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RawSessionReference:
    session_id: str
    message_ids: list[int]
    source: str
    started_at: str | None
    ended_at: str | None
    title: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "message_ids": list(self.message_ids),
            "source": self.source,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RawSessionReference":
        return cls(
            session_id=payload["session_id"],
            message_ids=list(payload.get("message_ids", [])),
            source=payload["source"],
            started_at=payload.get("started_at"),
            ended_at=payload.get("ended_at"),
            title=payload.get("title"),
        )


@dataclass(frozen=True)
class MicroSummary:
    micro_id: str
    session_id: str
    message_ids: list[int]
    summary: str
    why_it_matters: str
    request: str | None = None
    outcome: str | None = None
    key_points: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    parent_unit_id: str | None = None
    provenance: RawSessionReference | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "micro_id": self.micro_id,
            "session_id": self.session_id,
            "message_ids": list(self.message_ids),
            "summary": self.summary,
            "why_it_matters": self.why_it_matters,
            "request": self.request,
            "outcome": self.outcome,
            "key_points": list(self.key_points),
            "follow_up_questions": list(self.follow_up_questions),
            "artifacts": list(self.artifacts),
            "files": list(self.files),
            "entities": list(self.entities),
            "concepts": list(self.concepts),
            "parent_unit_id": self.parent_unit_id,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MicroSummary":
        provenance_payload = payload.get("provenance")
        return cls(
            micro_id=payload["micro_id"],
            session_id=payload["session_id"],
            message_ids=list(payload.get("message_ids", [])),
            summary=payload["summary"],
            why_it_matters=payload["why_it_matters"],
            request=payload.get("request"),
            outcome=payload.get("outcome"),
            key_points=list(payload.get("key_points", [])),
            follow_up_questions=list(payload.get("follow_up_questions", [])),
            artifacts=list(payload.get("artifacts", [])),
            files=list(payload.get("files", [])),
            entities=list(payload.get("entities", [])),
            concepts=list(payload.get("concepts", [])),
            parent_unit_id=payload.get("parent_unit_id"),
            provenance=(
                RawSessionReference.from_dict(provenance_payload)
                if provenance_payload
                else None
            ),
        )


@dataclass(frozen=True)
class UnitSummary:
    unit_id: str
    session_id: str
    title: str
    goal: str
    decisions: list[str] = field(default_factory=list)
    progress: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    micro_ids: list[str] = field(default_factory=list)
    related_pages: list[str] = field(default_factory=list)
    provenance: RawSessionReference | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "session_id": self.session_id,
            "title": self.title,
            "goal": self.goal,
            "decisions": list(self.decisions),
            "progress": list(self.progress),
            "open_questions": list(self.open_questions),
            "micro_ids": list(self.micro_ids),
            "related_pages": list(self.related_pages),
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UnitSummary":
        provenance_payload = payload.get("provenance")
        return cls(
            unit_id=payload["unit_id"],
            session_id=payload["session_id"],
            title=payload["title"],
            goal=payload["goal"],
            decisions=list(payload.get("decisions", [])),
            progress=list(payload.get("progress", [])),
            open_questions=list(payload.get("open_questions", [])),
            micro_ids=list(payload.get("micro_ids", [])),
            related_pages=list(payload.get("related_pages", [])),
            provenance=(
                RawSessionReference.from_dict(provenance_payload)
                if provenance_payload
                else None
            ),
        )


@dataclass(frozen=True)
class ContextPacket:
    packet_id: str
    task_title: str
    macro_context: str
    unit_summaries: list[UnitSummary] = field(default_factory=list)
    micro_summaries: list[MicroSummary] = field(default_factory=list)
    raw_pointers: list[RawSessionReference] = field(default_factory=list)
    critical_files: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "task_title": self.task_title,
            "macro_context": self.macro_context,
            "unit_summaries": [summary.to_dict() for summary in self.unit_summaries],
            "micro_summaries": [summary.to_dict() for summary in self.micro_summaries],
            "raw_pointers": [pointer.to_dict() for pointer in self.raw_pointers],
            "critical_files": list(self.critical_files),
            "open_questions": list(self.open_questions),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ContextPacket":
        return cls(
            packet_id=payload["packet_id"],
            task_title=payload["task_title"],
            macro_context=payload["macro_context"],
            unit_summaries=[
                UnitSummary.from_dict(item)
                for item in payload.get("unit_summaries", [])
            ],
            micro_summaries=[
                MicroSummary.from_dict(item)
                for item in payload.get("micro_summaries", [])
            ],
            raw_pointers=[
                RawSessionReference.from_dict(item)
                for item in payload.get("raw_pointers", [])
            ],
            critical_files=list(payload.get("critical_files", [])),
            open_questions=list(payload.get("open_questions", [])),
        )
