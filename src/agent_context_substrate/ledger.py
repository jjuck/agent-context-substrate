from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json


@dataclass(frozen=True)
class LedgerRecord:
    session_id: str
    pipeline: str
    status: str
    updated_at: str
    artifact_paths: dict[str, str]
    issue_count: int = 0
    attempt_count: int = 0
    last_error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "pipeline": self.pipeline,
            "status": self.status,
            "updated_at": self.updated_at,
            "artifact_paths": dict(self.artifact_paths),
            "issue_count": self.issue_count,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "LedgerRecord":
        return cls(
            session_id=str(payload["session_id"]),
            pipeline=str(payload["pipeline"]),
            status=str(payload["status"]),
            updated_at=str(payload["updated_at"]),
            artifact_paths={
                str(key): str(value)
                for key, value in dict(payload.get("artifact_paths", {})).items()
            },
            issue_count=int(payload.get("issue_count", 0)),
            attempt_count=int(payload.get("attempt_count", 0)),
            last_error=str(payload.get("last_error", "")),
        )


class SessionLedger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _read_all(self) -> dict[str, dict[str, dict[str, object]]]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}

    def _write_all(self, payload: dict[str, dict[str, dict[str, object]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_record(self, session_id: str, pipeline: str) -> LedgerRecord | None:
        payload = self._read_all()
        pipeline_entries = payload.get(pipeline, {})
        record = pipeline_entries.get(session_id)
        if not isinstance(record, dict):
            return None
        return LedgerRecord.from_dict(record)

    def mark_completed(
        self,
        *,
        session_id: str,
        pipeline: str,
        artifact_paths: dict[str, str],
        issue_count: int = 0,
        attempt_count: int = 0,
    ) -> LedgerRecord:
        payload = self._read_all()
        pipeline_entries = payload.setdefault(pipeline, {})
        record = LedgerRecord(
            session_id=session_id,
            pipeline=pipeline,
            status="completed",
            updated_at=datetime.now(timezone.utc).isoformat(),
            artifact_paths=dict(artifact_paths),
            issue_count=issue_count,
            attempt_count=attempt_count,
            last_error="",
        )
        pipeline_entries[session_id] = record.to_dict()
        self._write_all(payload)
        return record

    def mark_failed(
        self,
        *,
        session_id: str,
        pipeline: str,
        error: str,
        artifact_paths: dict[str, str] | None = None,
    ) -> LedgerRecord:
        payload = self._read_all()
        pipeline_entries = payload.setdefault(pipeline, {})
        existing_payload = pipeline_entries.get(session_id)
        existing_attempts = 0
        if isinstance(existing_payload, dict):
            existing_attempts = int(existing_payload.get("attempt_count", 0))
        record = LedgerRecord(
            session_id=session_id,
            pipeline=pipeline,
            status="failed",
            updated_at=datetime.now(timezone.utc).isoformat(),
            artifact_paths=dict(artifact_paths or {}),
            issue_count=0,
            attempt_count=existing_attempts + 1,
            last_error=error,
        )
        pipeline_entries[session_id] = record.to_dict()
        self._write_all(payload)
        return record
