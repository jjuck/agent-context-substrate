from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os

from .ledger import SessionLedger
from .models import ContextPacket
from .paths import HarnessPaths


@dataclass(frozen=True)
class RecoveryBrief:
    session_id: str
    packet_id: str
    task_title: str
    macro_context: str
    decisions: list[str]
    critical_files: list[str]
    open_questions: list[str]
    related_pages: list[str]
    provenance: list[str]
    recovery_json_path: Path

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "packet_id": self.packet_id,
            "task_title": self.task_title,
            "macro_context": self.macro_context,
            "decisions": list(self.decisions),
            "critical_files": list(self.critical_files),
            "open_questions": list(self.open_questions),
            "related_pages": list(self.related_pages),
            "provenance": list(self.provenance),
        }


def _format_provenance(pointer) -> str:
    message_ids = ",".join(str(message_id) for message_id in pointer.message_ids)
    return f"hermes-session:{pointer.session_id}#messages={message_ids}"


def _truncate(values: list[str], max_items: int) -> list[str]:
    return list(values[:max_items])


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
        critical_files = _truncate(list(packet.critical_files), max_items)
        open_questions = _truncate(list(packet.open_questions), max_items)
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
        brief = RecoveryBrief(
            session_id=session_id,
            packet_id=packet.packet_id,
            task_title=packet.task_title,
            macro_context=packet.macro_context,
            decisions=decisions,
            critical_files=critical_files,
            open_questions=open_questions,
            related_pages=related_pages,
            provenance=provenance,
            recovery_json_path=recovery_path,
        )
        export_recovery_brief(brief, paths)
        return brief
    finally:
        if old_value is None:
            os.environ.pop("WIKI_PATH", None)
        else:
            os.environ["WIKI_PATH"] = old_value
