from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import EvidenceBackedText, MicroSummaryV2


@dataclass(frozen=True)
class ClaimAtom:
    atom_id: str
    text: str
    type: str
    subjects: list[str]
    source_refs: list[str]
    confidence: float
    status: str
    first_seen: str
    last_seen: str
    supports: list[str]
    contradicts: list[str]
    supersedes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "text": self.text,
            "type": self.type,
            "subjects": list(self.subjects),
            "source_refs": list(self.source_refs),
            "confidence": self.confidence,
            "status": self.status,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "supports": list(self.supports),
            "contradicts": list(self.contradicts),
            "supersedes": list(self.supersedes),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ClaimAtom":
        return cls(
            atom_id=str(payload["atom_id"]),
            text=str(payload["text"]),
            type=str(payload["type"]),
            subjects=list(payload.get("subjects", [])),
            source_refs=list(payload.get("source_refs", [])),
            confidence=float(payload["confidence"]),
            status=str(payload["status"]),
            first_seen=str(payload["first_seen"]),
            last_seen=str(payload["last_seen"]),
            supports=list(payload.get("supports", [])),
            contradicts=list(payload.get("contradicts", [])),
            supersedes=list(payload.get("supersedes", [])),
        )


@dataclass(frozen=True)
class DecisionAtom:
    atom_id: str
    text: str
    source_refs: list[str]
    confidence: float
    status: str
    first_seen: str
    last_seen: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "text": self.text,
            "source_refs": list(self.source_refs),
            "confidence": self.confidence,
            "status": self.status,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DecisionAtom":
        return cls(
            atom_id=str(payload["atom_id"]),
            text=str(payload["text"]),
            source_refs=list(payload.get("source_refs", [])),
            confidence=float(payload["confidence"]),
            status=str(payload["status"]),
            first_seen=str(payload["first_seen"]),
            last_seen=str(payload["last_seen"]),
        )


@dataclass(frozen=True)
class EntityAtom:
    atom_id: str
    name: str
    type: str
    source_refs: list[str]
    status: str
    first_seen: str
    last_seen: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "name": self.name,
            "type": self.type,
            "source_refs": list(self.source_refs),
            "status": self.status,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EntityAtom":
        return cls(
            atom_id=str(payload["atom_id"]),
            name=str(payload["name"]),
            type=str(payload["type"]),
            source_refs=list(payload.get("source_refs", [])),
            status=str(payload["status"]),
            first_seen=str(payload["first_seen"]),
            last_seen=str(payload["last_seen"]),
        )


@dataclass(frozen=True)
class ConceptAtom:
    atom_id: str
    name: str
    source_refs: list[str]
    status: str
    first_seen: str
    last_seen: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "name": self.name,
            "source_refs": list(self.source_refs),
            "status": self.status,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ConceptAtom":
        return cls(
            atom_id=str(payload["atom_id"]),
            name=str(payload["name"]),
            source_refs=list(payload.get("source_refs", [])),
            status=str(payload["status"]),
            first_seen=str(payload["first_seen"]),
            last_seen=str(payload["last_seen"]),
        )


@dataclass(frozen=True)
class QuestionAtom:
    atom_id: str
    text: str
    source_refs: list[str]
    status: str
    first_seen: str
    last_seen: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "text": self.text,
            "source_refs": list(self.source_refs),
            "status": self.status,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "QuestionAtom":
        return cls(
            atom_id=str(payload["atom_id"]),
            text=str(payload["text"]),
            source_refs=list(payload.get("source_refs", [])),
            status=str(payload["status"]),
            first_seen=str(payload["first_seen"]),
            last_seen=str(payload["last_seen"]),
        )


def extract_claim_atoms(*, packet_id: str, micro_summaries: list[MicroSummaryV2]) -> list[ClaimAtom]:
    atoms: list[ClaimAtom] = []
    for micro in micro_summaries:
        claims = _claims_or_fallback(micro)
        for claim in claims:
            index = len(atoms) + 1
            created_at = _created_at(micro)
            atoms.append(
                ClaimAtom(
                    atom_id=f"{packet_id}-claim-{index}",
                    text=claim.text,
                    type="design_claim",
                    subjects=[*micro.entities, *micro.concepts],
                    source_refs=_source_refs(packet_id=packet_id, micro=micro),
                    confidence=claim.confidence,
                    status="active",
                    first_seen=created_at,
                    last_seen=created_at,
                    supports=[],
                    contradicts=[],
                    supersedes=[],
                )
            )
    return atoms


def extract_decision_atoms(*, packet_id: str, micro_summaries: list[MicroSummaryV2]) -> list[DecisionAtom]:
    atoms: list[DecisionAtom] = []
    for micro in micro_summaries:
        for decision in micro.decisions:
            created_at = _created_at(micro)
            atoms.append(
                DecisionAtom(
                    atom_id=f"{packet_id}-decision-{len(atoms) + 1}",
                    text=decision.text,
                    source_refs=_source_refs(packet_id=packet_id, micro=micro),
                    confidence=decision.confidence,
                    status="active",
                    first_seen=created_at,
                    last_seen=created_at,
                )
            )
    return atoms


def extract_entity_atoms(*, packet_id: str, micro_summaries: list[MicroSummaryV2]) -> list[EntityAtom]:
    atoms: list[EntityAtom] = []
    seen: set[str] = set()
    for micro in micro_summaries:
        for entity in micro.entities:
            normalized = _normalize_name(entity)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            created_at = _created_at(micro)
            atoms.append(
                EntityAtom(
                    atom_id=f"{packet_id}-entity-{len(atoms) + 1}",
                    name=entity,
                    type="entity",
                    source_refs=_source_refs(packet_id=packet_id, micro=micro),
                    status="active",
                    first_seen=created_at,
                    last_seen=created_at,
                )
            )
    return atoms


def extract_concept_atoms(*, packet_id: str, micro_summaries: list[MicroSummaryV2]) -> list[ConceptAtom]:
    atoms: list[ConceptAtom] = []
    seen: set[str] = set()
    for micro in micro_summaries:
        for concept in micro.concepts:
            normalized = _normalize_name(concept)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            created_at = _created_at(micro)
            atoms.append(
                ConceptAtom(
                    atom_id=f"{packet_id}-concept-{len(atoms) + 1}",
                    name=concept,
                    source_refs=_source_refs(packet_id=packet_id, micro=micro),
                    status="active",
                    first_seen=created_at,
                    last_seen=created_at,
                )
            )
    return atoms


def extract_question_atoms(*, packet_id: str, micro_summaries: list[MicroSummaryV2]) -> list[QuestionAtom]:
    atoms: list[QuestionAtom] = []
    seen: set[str] = set()
    for micro in micro_summaries:
        for question in micro.open_questions:
            normalized = _normalize_name(question)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            created_at = _created_at(micro)
            atoms.append(
                QuestionAtom(
                    atom_id=f"{packet_id}-question-{len(atoms) + 1}",
                    text=question,
                    source_refs=_source_refs(packet_id=packet_id, micro=micro),
                    status="open",
                    first_seen=created_at,
                    last_seen=created_at,
                )
            )
    return atoms


def _claims_or_fallback(micro: MicroSummaryV2) -> list[EvidenceBackedText]:
    if micro.claims:
        return list(micro.claims)
    if not micro.knowledge_summary.strip():
        return []
    return [
        EvidenceBackedText(
            text=micro.knowledge_summary,
            evidence_message_ids=list(micro.message_ids),
            confidence=0.4,
        )
    ]


def _source_refs(*, packet_id: str, micro: MicroSummaryV2) -> list[str]:
    return [f"packet:{packet_id}#{micro.micro_id}", _format_raw_source_ref(micro)]


def _created_at(micro: MicroSummaryV2) -> str:
    return micro.metadata.created_at if micro.metadata else ""


def _normalize_name(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _format_raw_source_ref(micro: MicroSummaryV2) -> str:
    if micro.provenance:
        message_ids = ",".join(str(message_id) for message_id in micro.provenance.message_ids)
        return f"hermes-session:{micro.provenance.session_id}#messages={message_ids}"
    message_ids = ",".join(str(message_id) for message_id in micro.message_ids)
    return f"hermes-session:{micro.session_id}#messages={message_ids}"
