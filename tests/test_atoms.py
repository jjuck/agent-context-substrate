from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.atoms import (  # noqa: E402
    ClaimAtom,
    ConceptAtom,
    DecisionAtom,
    EntityAtom,
    QuestionAtom,
    extract_claim_atoms,
    extract_concept_atoms,
    extract_decision_atoms,
    extract_entity_atoms,
    extract_question_atoms,
)
from agent_context_substrate.models import EvidenceBackedText  # noqa: E402
from agent_context_substrate.summarizer import build_micro_summary_v2  # noqa: E402


def _raw_bundle() -> dict:
    return {
        "session": {"id": "session-atoms", "source": "telegram", "title": "Atoms"},
        "messages": [
            {"id": 1, "role": "user", "content": "Design claim atom extraction for README.md"},
            {"id": 2, "role": "assistant", "content": "Done.\n- Claims should cite message ids\n- Promotion candidates should use claims"},
        ],
    }


def test_extract_claim_atoms_from_micro_summary_v2() -> None:
    micro = build_micro_summary_v2(raw_bundle=_raw_bundle(), micro_id="micro-atoms")

    atoms = extract_claim_atoms(packet_id="packet-atoms", micro_summaries=[micro])

    assert atoms == [
        ClaimAtom(
            atom_id="packet-atoms-claim-1",
            text="Claims should cite message ids",
            type="design_claim",
            subjects=[],
            source_refs=["packet:packet-atoms#micro-atoms", "hermes-session:session-atoms#messages=1,2"],
            confidence=0.5,
            status="active",
            first_seen=micro.metadata.created_at,
            last_seen=micro.metadata.created_at,
            supports=[],
            contradicts=[],
            supersedes=[],
        ),
        ClaimAtom(
            atom_id="packet-atoms-claim-2",
            text="Promotion candidates should use claims",
            type="design_claim",
            subjects=[],
            source_refs=["packet:packet-atoms#micro-atoms", "hermes-session:session-atoms#messages=1,2"],
            confidence=0.5,
            status="active",
            first_seen=micro.metadata.created_at,
            last_seen=micro.metadata.created_at,
            supports=[],
            contradicts=[],
            supersedes=[],
        ),
    ]
    assert ClaimAtom.from_dict(atoms[0].to_dict()) == atoms[0]


def test_extract_decision_entity_concept_and_question_atoms_from_micro_summary_v2() -> None:
    base = build_micro_summary_v2(raw_bundle=_raw_bundle(), micro_id="micro-atoms")
    micro = replace(
        base,
        decisions=[EvidenceBackedText("Use packet-only by default", [1], 0.9)],
        entities=["Agent Context Substrate", "Hermes Agent", "Agent Context Substrate"],
        concepts=["packet-only", "summary lint", "packet-only"],
        open_questions=["Should stale claims be marked automatically?"],
    )

    decision_atoms = extract_decision_atoms(packet_id="packet-atoms", micro_summaries=[micro])
    entity_atoms = extract_entity_atoms(packet_id="packet-atoms", micro_summaries=[micro])
    concept_atoms = extract_concept_atoms(packet_id="packet-atoms", micro_summaries=[micro])
    question_atoms = extract_question_atoms(packet_id="packet-atoms", micro_summaries=[micro])

    assert decision_atoms == [
        DecisionAtom(
            atom_id="packet-atoms-decision-1",
            text="Use packet-only by default",
            source_refs=["packet:packet-atoms#micro-atoms", "hermes-session:session-atoms#messages=1,2"],
            confidence=0.9,
            status="active",
            first_seen=micro.metadata.created_at,
            last_seen=micro.metadata.created_at,
        )
    ]
    assert entity_atoms == [
        EntityAtom(
            atom_id="packet-atoms-entity-1",
            name="Agent Context Substrate",
            type="entity",
            source_refs=["packet:packet-atoms#micro-atoms", "hermes-session:session-atoms#messages=1,2"],
            status="active",
            first_seen=micro.metadata.created_at,
            last_seen=micro.metadata.created_at,
        ),
        EntityAtom(
            atom_id="packet-atoms-entity-2",
            name="Hermes Agent",
            type="entity",
            source_refs=["packet:packet-atoms#micro-atoms", "hermes-session:session-atoms#messages=1,2"],
            status="active",
            first_seen=micro.metadata.created_at,
            last_seen=micro.metadata.created_at,
        ),
    ]
    assert concept_atoms == [
        ConceptAtom(
            atom_id="packet-atoms-concept-1",
            name="packet-only",
            source_refs=["packet:packet-atoms#micro-atoms", "hermes-session:session-atoms#messages=1,2"],
            status="active",
            first_seen=micro.metadata.created_at,
            last_seen=micro.metadata.created_at,
        ),
        ConceptAtom(
            atom_id="packet-atoms-concept-2",
            name="summary lint",
            source_refs=["packet:packet-atoms#micro-atoms", "hermes-session:session-atoms#messages=1,2"],
            status="active",
            first_seen=micro.metadata.created_at,
            last_seen=micro.metadata.created_at,
        ),
    ]
    assert question_atoms == [
        QuestionAtom(
            atom_id="packet-atoms-question-1",
            text="Should stale claims be marked automatically?",
            source_refs=["packet:packet-atoms#micro-atoms", "hermes-session:session-atoms#messages=1,2"],
            status="open",
            first_seen=micro.metadata.created_at,
            last_seen=micro.metadata.created_at,
        )
    ]
    assert DecisionAtom.from_dict(decision_atoms[0].to_dict()) == decision_atoms[0]
    assert EntityAtom.from_dict(entity_atoms[0].to_dict()) == entity_atoms[0]
    assert ConceptAtom.from_dict(concept_atoms[0].to_dict()) == concept_atoms[0]
    assert QuestionAtom.from_dict(question_atoms[0].to_dict()) == question_atoms[0]
