from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .heuristic_composition import compose_recovery_summary
from .heuristic_metadata import HeuristicMetadataSignals, extract_metadata_signals
from .heuristic_recovery import HeuristicRecoveryFields, extract_recovery_fields


@dataclass(frozen=True)
class HeuristicMessageAnalysis:
    messages: list[dict[str, Any]]
    salient_messages: list[dict[str, Any]]
    text: str
    request: str | None
    outcome: str | None
    key_points: list[str]
    follow_up_questions: list[str]
    recovery_summary: str
    files: list[str]
    entities: list[str]
    concepts: list[str]


def analyze_heuristic_messages(messages: list[dict[str, Any]]) -> HeuristicMessageAnalysis:
    """Extract stable heuristic summary stages from raw-compatible messages."""

    message_list = list(messages)
    metadata_signals = extract_metadata_signals(message_list)
    recovery_fields = extract_recovery_fields(message_list)
    return HeuristicMessageAnalysis(
        messages=message_list,
        salient_messages=metadata_signals.salient_messages,
        text=metadata_signals.text,
        request=recovery_fields.request,
        outcome=recovery_fields.outcome,
        key_points=recovery_fields.key_points,
        follow_up_questions=recovery_fields.follow_up_questions,
        recovery_summary=recovery_fields.recovery_summary,
        files=metadata_signals.files,
        entities=metadata_signals.entities,
        concepts=metadata_signals.concepts,
    )


__all__ = [
    "HeuristicMessageAnalysis",
    "HeuristicMetadataSignals",
    "HeuristicRecoveryFields",
    "analyze_heuristic_messages",
    "compose_recovery_summary",
    "extract_metadata_signals",
    "extract_recovery_fields",
]
