from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .heuristic_composition import compose_recovery_summary
from .heuristic_metadata import HeuristicMetadataSignals, extract_metadata_signals
from .heuristic_recovery import HeuristicRecoveryFields, extract_recovery_fields


@dataclass(frozen=True)
class HeuristicMessageAnalysis:
    messages: list[dict[str, Any]]
    metadata_signals: HeuristicMetadataSignals
    recovery_fields: HeuristicRecoveryFields

    @property
    def salient_messages(self) -> list[dict[str, Any]]:
        return self.metadata_signals.salient_messages

    @property
    def text(self) -> str:
        return self.metadata_signals.text

    @property
    def files(self) -> list[str]:
        return self.metadata_signals.files

    @property
    def entities(self) -> list[str]:
        return self.metadata_signals.entities

    @property
    def concepts(self) -> list[str]:
        return self.metadata_signals.concepts

    @property
    def request(self) -> str | None:
        return self.recovery_fields.request

    @property
    def outcome(self) -> str | None:
        return self.recovery_fields.outcome

    @property
    def key_points(self) -> list[str]:
        return self.recovery_fields.key_points

    @property
    def follow_up_questions(self) -> list[str]:
        return self.recovery_fields.follow_up_questions

    @property
    def recovery_summary(self) -> str:
        return self.recovery_fields.recovery_summary


def analyze_heuristic_messages(messages: list[dict[str, Any]]) -> HeuristicMessageAnalysis:
    """Extract stable heuristic summary stages from raw-compatible messages."""

    message_list = list(messages)
    metadata_signals = extract_metadata_signals(message_list)
    recovery_fields = extract_recovery_fields(message_list)
    return HeuristicMessageAnalysis(
        messages=message_list,
        metadata_signals=metadata_signals,
        recovery_fields=recovery_fields,
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
