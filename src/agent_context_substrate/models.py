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
class SummaryMetadata:
    mode: str
    schema_version: str
    prompt_version: str | None
    model: str | None
    input_hash: str
    created_at: str
    confidence: float | None = None
    fallback_from: str | None = None
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "schema_version": self.schema_version,
            "prompt_version": self.prompt_version,
            "model": self.model,
            "input_hash": self.input_hash,
            "created_at": self.created_at,
            "confidence": self.confidence,
            "fallback_from": self.fallback_from,
            "fallback_reason": self.fallback_reason,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SummaryMetadata":
        confidence = payload.get("confidence")
        return cls(
            mode=str(payload["mode"]),
            schema_version=str(payload["schema_version"]),
            prompt_version=(
                str(payload["prompt_version"])
                if payload.get("prompt_version") is not None
                else None
            ),
            model=str(payload["model"]) if payload.get("model") is not None else None,
            input_hash=str(payload["input_hash"]),
            created_at=str(payload["created_at"]),
            confidence=float(confidence) if confidence is not None else None,
            fallback_from=(
                str(payload["fallback_from"])
                if payload.get("fallback_from") is not None
                else None
            ),
            fallback_reason=(
                str(payload["fallback_reason"])
                if payload.get("fallback_reason") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class EvidenceBackedText:
    text: str
    evidence_message_ids: list[int]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "evidence_message_ids": list(self.evidence_message_ids),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceBackedText":
        return cls(
            text=str(payload["text"]),
            evidence_message_ids=[
                int(message_id)
                for message_id in payload.get("evidence_message_ids", [])
            ],
            confidence=float(payload["confidence"]),
        )


@dataclass(frozen=True)
class EvidenceMessage:
    message_id: int
    role: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "role": self.role,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceMessage":
        return cls(
            message_id=int(payload["message_id"]),
            role=str(payload["role"]),
            content=str(payload["content"]),
        )


@dataclass(frozen=True)
class MicroEvidenceBundle:
    session_id: str
    micro_id: str
    message_ids: list[int]
    user_messages: list[EvidenceMessage]
    assistant_messages: list[EvidenceMessage]
    heuristic_request: str | None
    heuristic_outcome: str | None
    heuristic_key_points: list[str]
    files: list[str]
    code_blocks: list[str]
    urls: list[str]
    headings: list[str]
    explicit_questions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "micro_id": self.micro_id,
            "message_ids": list(self.message_ids),
            "user_messages": [message.to_dict() for message in self.user_messages],
            "assistant_messages": [message.to_dict() for message in self.assistant_messages],
            "heuristic_request": self.heuristic_request,
            "heuristic_outcome": self.heuristic_outcome,
            "heuristic_key_points": list(self.heuristic_key_points),
            "files": list(self.files),
            "code_blocks": list(self.code_blocks),
            "urls": list(self.urls),
            "headings": list(self.headings),
            "explicit_questions": list(self.explicit_questions),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MicroEvidenceBundle":
        return cls(
            session_id=str(payload["session_id"]),
            micro_id=str(payload["micro_id"]),
            message_ids=[int(message_id) for message_id in payload.get("message_ids", [])],
            user_messages=[
                EvidenceMessage.from_dict(item)
                for item in payload.get("user_messages", [])
            ],
            assistant_messages=[
                EvidenceMessage.from_dict(item)
                for item in payload.get("assistant_messages", [])
            ],
            heuristic_request=payload.get("heuristic_request"),
            heuristic_outcome=payload.get("heuristic_outcome"),
            heuristic_key_points=list(payload.get("heuristic_key_points", [])),
            files=list(payload.get("files", [])),
            code_blocks=list(payload.get("code_blocks", [])),
            urls=list(payload.get("urls", [])),
            headings=list(payload.get("headings", [])),
            explicit_questions=list(payload.get("explicit_questions", [])),
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
class MicroSummaryV2:
    micro_id: str
    session_id: str
    message_ids: list[int]
    recovery_summary: str
    knowledge_summary: str
    retrieval_summary: str
    user_intent: str | None
    assistant_outcome: str | None
    decisions: list[EvidenceBackedText] = field(default_factory=list)
    claims: list[EvidenceBackedText] = field(default_factory=list)
    action_items: list[EvidenceBackedText] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    metadata: SummaryMetadata | None = None
    provenance: RawSessionReference | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "micro_id": self.micro_id,
            "session_id": self.session_id,
            "message_ids": list(self.message_ids),
            "recovery_summary": self.recovery_summary,
            "knowledge_summary": self.knowledge_summary,
            "retrieval_summary": self.retrieval_summary,
            "user_intent": self.user_intent,
            "assistant_outcome": self.assistant_outcome,
            "decisions": [item.to_dict() for item in self.decisions],
            "claims": [item.to_dict() for item in self.claims],
            "action_items": [item.to_dict() for item in self.action_items],
            "open_questions": list(self.open_questions),
            "files": list(self.files),
            "entities": list(self.entities),
            "concepts": list(self.concepts),
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MicroSummaryV2":
        metadata_payload = payload.get("metadata")
        provenance_payload = payload.get("provenance")
        return cls(
            micro_id=str(payload["micro_id"]),
            session_id=str(payload["session_id"]),
            message_ids=[int(message_id) for message_id in payload.get("message_ids", [])],
            recovery_summary=str(payload["recovery_summary"]),
            knowledge_summary=str(payload["knowledge_summary"]),
            retrieval_summary=str(payload["retrieval_summary"]),
            user_intent=payload.get("user_intent"),
            assistant_outcome=payload.get("assistant_outcome"),
            decisions=[EvidenceBackedText.from_dict(item) for item in payload.get("decisions", [])],
            claims=[EvidenceBackedText.from_dict(item) for item in payload.get("claims", [])],
            action_items=[EvidenceBackedText.from_dict(item) for item in payload.get("action_items", [])],
            open_questions=list(payload.get("open_questions", [])),
            files=list(payload.get("files", [])),
            entities=list(payload.get("entities", [])),
            concepts=list(payload.get("concepts", [])),
            metadata=SummaryMetadata.from_dict(metadata_payload) if metadata_payload else None,
            provenance=RawSessionReference.from_dict(provenance_payload) if provenance_payload else None,
        )


@dataclass(frozen=True)
class UnitSummaryV2:
    unit_id: str
    session_id: str
    title: str
    goal: str
    state: str
    decisions: list[EvidenceBackedText] = field(default_factory=list)
    progress: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    wiki_candidates: list[EvidenceBackedText] = field(default_factory=list)
    micro_ids: list[str] = field(default_factory=list)
    related_pages: list[str] = field(default_factory=list)
    metadata: SummaryMetadata | None = None
    provenance: RawSessionReference | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "session_id": self.session_id,
            "title": self.title,
            "goal": self.goal,
            "state": self.state,
            "decisions": [item.to_dict() for item in self.decisions],
            "progress": list(self.progress),
            "next_actions": list(self.next_actions),
            "open_questions": list(self.open_questions),
            "risk_notes": list(self.risk_notes),
            "wiki_candidates": [item.to_dict() for item in self.wiki_candidates],
            "micro_ids": list(self.micro_ids),
            "related_pages": list(self.related_pages),
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UnitSummaryV2":
        metadata_payload = payload.get("metadata")
        provenance_payload = payload.get("provenance")
        return cls(
            unit_id=str(payload["unit_id"]),
            session_id=str(payload["session_id"]),
            title=str(payload["title"]),
            goal=str(payload["goal"]),
            state=str(payload["state"]),
            decisions=[EvidenceBackedText.from_dict(item) for item in payload.get("decisions", [])],
            progress=list(payload.get("progress", [])),
            next_actions=list(payload.get("next_actions", [])),
            open_questions=list(payload.get("open_questions", [])),
            risk_notes=list(payload.get("risk_notes", [])),
            wiki_candidates=[EvidenceBackedText.from_dict(item) for item in payload.get("wiki_candidates", [])],
            micro_ids=list(payload.get("micro_ids", [])),
            related_pages=list(payload.get("related_pages", [])),
            metadata=SummaryMetadata.from_dict(metadata_payload) if metadata_payload else None,
            provenance=RawSessionReference.from_dict(provenance_payload) if provenance_payload else None,
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
