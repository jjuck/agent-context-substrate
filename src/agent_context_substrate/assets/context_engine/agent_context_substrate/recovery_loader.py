"""Recovery brief loading helpers for the agent_context_substrate context engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import LEDGER_PIPELINE


def recovery_dir(project_root: Path) -> Path:
    return project_root / "data" / "exports" / "recovery"


def ledger_path(project_root: Path) -> Path:
    return project_root / "data" / "index" / "session_ledger.json"


def load_recovery_brief(
    project_root: Path,
    requested_session_id: str | None = None,
) -> tuple[dict[str, Any] | None, Path | None]:
    if not requested_session_id:
        return None, None

    ledger_record = ledger_record_for(project_root, requested_session_id)
    candidate_paths: list[Path] = []
    if ledger_record:
        artifact_paths = dict(ledger_record.get("artifact_paths", {}))
        recovery_path = artifact_paths.get("recovery_json_path")
        if recovery_path:
            candidate_paths.append(resolve_artifact_path(project_root, recovery_path))

    candidate_paths.append(recovery_dir(project_root) / f"{requested_session_id}.json")
    return load_first_json(candidate_paths)


def load_latest_recovery_from_ledger(project_root: Path) -> tuple[dict[str, Any] | None, Path | None]:
    records = ledger_records(project_root)
    completed_records = [
        record
        for record in records
        if record.get("status") == "completed" and record.get("artifact_paths")
    ]
    completed_records.sort(key=lambda record: str(record.get("updated_at", "")), reverse=True)

    for record in completed_records:
        artifact_paths = dict(record.get("artifact_paths", {}))
        candidate_paths: list[Path] = []
        recovery_path = artifact_paths.get("recovery_json_path")
        if recovery_path:
            candidate_paths.append(resolve_artifact_path(project_root, recovery_path))
        session_id = str(record.get("session_id", ""))
        if session_id:
            candidate_paths.append(recovery_dir(project_root) / f"{session_id}.json")
        brief, source_path = load_first_json(candidate_paths)
        if brief is not None:
            return brief, source_path
    return None, None


def ledger_record_for(project_root: Path, session_id: str) -> dict[str, Any] | None:
    payload = load_json_object(ledger_path(project_root))
    if not payload:
        return None
    record = dict(payload.get(LEDGER_PIPELINE, {})).get(session_id)
    return record if isinstance(record, dict) else None


def ledger_records(project_root: Path) -> list[dict[str, Any]]:
    payload = load_json_object(ledger_path(project_root))
    if not payload:
        return []
    records = dict(payload.get(LEDGER_PIPELINE, {})).values()
    return [record for record in records if isinstance(record, dict)]


def resolve_artifact_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def load_first_json(paths: list[Path]) -> tuple[dict[str, Any] | None, Path | None]:
    for path in paths:
        payload = load_json_object(path)
        if payload is not None:
            return payload, path
    return None, None
