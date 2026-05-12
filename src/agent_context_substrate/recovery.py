from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import json
import os

from .ledger import SessionLedger
from .models import ContextPacket
from .paths import HarnessPaths


@dataclass(frozen=True)
class RecoveryQualityIssue:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass(frozen=True)
class RecoveryQualityReport:
    score: float
    issues: list[RecoveryQualityIssue]

    @property
    def ok(self) -> bool:
        return self.score >= 0.8 and not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "score": self.score,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class RecoveryBrief:
    session_id: str
    packet_id: str
    task_title: str
    macro_context: str
    decisions: list[str]
    progress: list[str]
    critical_files: list[str]
    open_questions: list[str]
    next_actions: list[str]
    related_pages: list[str]
    provenance: list[str]
    recovery_json_path: Path
    quality_gate: RecoveryQualityReport | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "packet_id": self.packet_id,
            "task_title": self.task_title,
            "macro_context": self.macro_context,
            "decisions": list(self.decisions),
            "progress": list(self.progress),
            "critical_files": list(self.critical_files),
            "open_questions": list(self.open_questions),
            "next_actions": list(self.next_actions),
            "related_pages": list(self.related_pages),
            "provenance": list(self.provenance),
            "quality_gate": self.quality_gate.to_dict() if self.quality_gate else None,
        }


def _format_provenance(pointer) -> str:
    message_ids = ",".join(str(message_id) for message_id in pointer.message_ids)
    return f"hermes-session:{pointer.session_id}#messages={message_ids}"


def _truncate(values: list[str], max_items: int) -> list[str]:
    return list(values[:max_items])


def _has_content(value: str) -> bool:
    return bool(value.strip())


def _append_quality_issue(
    issues: list[RecoveryQualityIssue],
    *,
    code: str,
    severity: str,
    message: str,
) -> None:
    issues.append(RecoveryQualityIssue(code=code, severity=severity, message=message))


def evaluate_recovery_brief_quality(brief: RecoveryBrief) -> RecoveryQualityReport:
    checks: list[bool] = []
    issues: list[RecoveryQualityIssue] = []

    has_task_title = _has_content(brief.task_title)
    checks.append(has_task_title)
    if not has_task_title:
        _append_quality_issue(
            issues,
            code="missing_task_title",
            severity="error",
            message="Recovery brief needs a task title so the user can identify the workstream.",
        )

    has_macro_context = _has_content(brief.macro_context)
    checks.append(has_macro_context)
    if not has_macro_context:
        _append_quality_issue(
            issues,
            code="missing_macro_context",
            severity="error",
            message="Recovery brief needs macro_context describing what was happening.",
        )

    has_work_state = bool(brief.decisions or brief.progress)
    checks.append(has_work_state)
    if not has_work_state:
        _append_quality_issue(
            issues,
            code="missing_work_state",
            severity="error",
            message="Recovery brief needs decisions or progress to show the last concrete state.",
        )

    has_active_context = bool(brief.critical_files or brief.related_pages)
    checks.append(has_active_context)
    if not has_active_context:
        _append_quality_issue(
            issues,
            code="missing_active_context",
            severity="warning",
            message="Recovery brief should include critical files or related pages for fast re-entry.",
        )

    has_next_step = bool(brief.next_actions or brief.open_questions)
    checks.append(has_next_step)
    if not has_next_step:
        _append_quality_issue(
            issues,
            code="missing_next_step",
            severity="warning",
            message="Recovery brief should include next_actions or open_questions for the next safe action.",
        )

    has_provenance = bool(brief.provenance)
    checks.append(has_provenance)
    if not has_provenance:
        _append_quality_issue(
            issues,
            code="missing_provenance",
            severity="error",
            message="Recovery brief needs provenance back to raw session messages or packet evidence.",
        )

    score = round(sum(1 for check in checks if check) / len(checks), 2)
    return RecoveryQualityReport(score=score, issues=issues)


def _derive_next_actions(*, progress: list[str], decisions: list[str], open_questions: list[str], max_items: int) -> list[str]:
    markers = ("next step", "next action", "next:", "todo", "follow up", "다음", "후속", "진행")
    actions: list[str] = []
    for value in [*progress, *decisions]:
        lowered = value.casefold()
        if any(marker in lowered for marker in markers):
            actions.append(value)
    if not actions and open_questions:
        actions.extend(f"Resolve open question: {question}" for question in open_questions)
    return _truncate(actions, max_items)


def export_recovery_brief(brief: RecoveryBrief, paths: HarnessPaths) -> Path:
    export_dir = paths.exports_dir / "recovery"
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / f"{brief.session_id}.json"
    output_path.write_text(
        json.dumps(brief.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def build_recovery_brief(
    session_id: str,
    *,
    project_root: Path,
    wiki_root: Path,
    max_items: int = 5,
) -> RecoveryBrief:
    old_value = os.environ.get("WIKI_PATH")
    os.environ["WIKI_PATH"] = str(Path(wiki_root).resolve())
    try:
        paths = HarnessPaths(project_root=Path(project_root).resolve())
        ledger = SessionLedger(paths.index_dir / "session_ledger.json")
        record = ledger.get_record(session_id, "session_finalize")
        if record is None:
            raise KeyError(f"No session_finalize ledger record for session_id={session_id}")

        packet_json_path = Path(record.artifact_paths["packet_json_path"])
        payload = json.loads(packet_json_path.read_text(encoding="utf-8"))
        packet = ContextPacket.from_dict(payload)

        unit_summary = packet.unit_summaries[0] if packet.unit_summaries else None
        decisions = _truncate(list(unit_summary.decisions if unit_summary else []), max_items)
        progress = _truncate(list(unit_summary.progress if unit_summary else []), max_items)
        critical_files = _truncate(list(packet.critical_files), max_items)
        open_questions = _truncate(list(packet.open_questions), max_items)
        next_actions = _derive_next_actions(
            progress=progress,
            decisions=decisions,
            open_questions=open_questions,
            max_items=max_items,
        )
        related_pages = _truncate(
            [
                Path(record.artifact_paths[key]).stem
                for key in ["query", "concept", "plan", "architecture"]
                if key in record.artifact_paths
            ],
            max_items,
        )
        provenance = _truncate(
            [_format_provenance(pointer) for pointer in packet.raw_pointers],
            max_items,
        )

        recovery_path = paths.exports_dir / "recovery" / f"{session_id}.json"
        brief_without_gate = RecoveryBrief(
            session_id=session_id,
            packet_id=packet.packet_id,
            task_title=packet.task_title,
            macro_context=packet.macro_context,
            decisions=decisions,
            progress=progress,
            critical_files=critical_files,
            open_questions=open_questions,
            next_actions=next_actions,
            related_pages=related_pages,
            provenance=provenance,
            recovery_json_path=recovery_path,
        )
        brief = replace(
            brief_without_gate,
            quality_gate=evaluate_recovery_brief_quality(brief_without_gate),
        )
        export_recovery_brief(brief, paths)
        return brief
    finally:
        if old_value is None:
            os.environ.pop("WIKI_PATH", None)
        else:
            os.environ["WIKI_PATH"] = old_value
