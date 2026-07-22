from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar
import json
import os

from .paths import HarnessPaths
from .safe_paths import safe_artifact_stem, safe_wiki_target_path
from .wiki_patches import WikiPatchProposal


T = TypeVar("T")


class WikiApplyTransaction:
    """Keep wiki content and ACS bookkeeping consistent across an apply attempt."""

    def __init__(self, *, paths: HarnessPaths, wiki_root: Path, proposal: WikiPatchProposal) -> None:
        self.paths = paths
        self.wiki_root = Path(wiki_root).resolve(strict=False)
        self.proposal = proposal
        transaction_name = safe_artifact_stem(proposal.proposal_id, label="proposal id")
        self.transaction_dir = paths.project_root / "data" / "wiki_patches" / "transactions"
        self.manifest_path = self.transaction_dir / f"{transaction_name}.json"
        self.snapshot_dir = self.transaction_dir / f"{transaction_name}.snapshots"

    def execute(self, *, apply_pages: Callable[[], T], commit_artifacts: Callable[[T], None]) -> T:
        self.recover_incomplete()
        manifest = self._prepare()
        try:
            result = apply_pages()
            commit_artifacts(result)
        except Exception as exc:
            self._restore(manifest)
            self._write_manifest({**manifest, "status": "rolled_back", "error": f"{type(exc).__name__}: {exc}"})
            raise
        self._write_manifest({**manifest, "status": "completed", "completed_at": _utc_now(), "error": ""})
        return result

    def recover_incomplete(self) -> bool:
        manifest = self._read_manifest()
        if manifest is None or manifest.get("status") != "prepared":
            return False
        self._restore(manifest)
        self._write_manifest({**manifest, "status": "recovered", "recovered_at": _utc_now(), "error": ""})
        return True

    def _prepare(self) -> dict[str, Any]:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        entries: list[dict[str, object]] = []
        for index, (scope, relative_path, path) in enumerate(self._affected_paths(), start=1):
            backup_name = f"{index}.bin"
            existed = path.is_file()
            if existed:
                (self.snapshot_dir / backup_name).write_bytes(path.read_bytes())
            entries.append(
                {
                    "scope": scope,
                    "relative_path": relative_path,
                    "existed": existed,
                    "backup_name": backup_name if existed else "",
                }
            )
        manifest: dict[str, Any] = {
            "schema_version": "wiki_apply_transaction_v1",
            "proposal_id": self.proposal.proposal_id,
            "packet_id": self.proposal.packet_id,
            "status": "prepared",
            "prepared_at": _utc_now(),
            "entries": entries,
            "error": "",
        }
        self._write_manifest(manifest)
        return manifest

    def _affected_paths(self) -> list[tuple[str, str, Path]]:
        items: list[tuple[str, str, Path]] = []
        for operation in self.proposal.operations:
            path = safe_wiki_target_path(wiki_root=self.wiki_root, target=operation.target)
            if path is not None:
                items.append(("wiki", operation.target.replace("\\", "/"), path))
        items.extend(
            [
                ("wiki", "index.md", self.wiki_root / "index.md"),
                ("wiki", "log.md", self.wiki_root / "log.md"),
                (
                    "project",
                    "data/wiki_patches/applied.jsonl",
                    self.paths.project_root / "data" / "wiki_patches" / "applied.jsonl",
                ),
                (
                    "project",
                    f"data/promotions/{self.proposal.packet_id}.json",
                    self.paths.project_root / "data" / "promotions" / f"{self.proposal.packet_id}.json",
                ),
            ]
        )
        deduped: list[tuple[str, str, Path]] = []
        seen: set[Path] = set()
        for scope, relative_path, path in items:
            resolved = path.resolve(strict=False)
            if resolved in seen:
                continue
            seen.add(resolved)
            deduped.append((scope, relative_path, resolved))
        return deduped

    def _restore(self, manifest: dict[str, Any]) -> None:
        entries = manifest.get("entries")
        if not isinstance(entries, list):
            raise ValueError("wiki apply transaction manifest entries must be a list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("wiki apply transaction entry must be an object")
            target = self._entry_path(entry)
            if bool(entry.get("existed")):
                backup_name = str(entry.get("backup_name") or "")
                backup_path = self.snapshot_dir / backup_name
                if not backup_name or not backup_path.is_file():
                    raise FileNotFoundError(f"wiki apply transaction snapshot is missing: {backup_path}")
                _atomic_write_bytes(target, backup_path.read_bytes())
                continue
            if target.exists():
                target.unlink()

    def _entry_path(self, entry: dict[str, object]) -> Path:
        scope = str(entry.get("scope") or "")
        relative_path = str(entry.get("relative_path") or "")
        root = self.wiki_root if scope == "wiki" else self.paths.project_root.resolve(strict=False)
        candidate = (root / relative_path).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"unsafe wiki apply transaction path: {relative_path}") from exc
        return candidate

    def _read_manifest(self) -> dict[str, Any] | None:
        if not self.manifest_path.exists():
            return None
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("wiki apply transaction manifest must be an object")
        return payload

    def _write_manifest(self, payload: dict[str, Any]) -> None:
        self.transaction_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_bytes(
            self.manifest_path,
            (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.acs-tmp")
    temporary_path.write_bytes(content)
    os.replace(temporary_path, path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
