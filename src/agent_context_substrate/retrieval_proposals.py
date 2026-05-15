from __future__ import annotations

from pathlib import Path

from .retrieval_ids import encode_hit_id
from .retrieval_scoring import make_snippet, score_text
from .retrieval_sources import iter_jsonl_objects, json_search_text, load_json_list, load_json_object
from .retrieval_types import RetrievalHit
from .safe_paths import is_safe_project_artifact_path


_PROMOTION_PREFIX = ("data", "promotions")
_WIKI_PATCH_PREFIX = ("data", "wiki_patches")
_APPLIED_PATCH_PREFIX = ("data", "wiki_patches")


def search_promotions(terms: list[str], project_root: Path) -> list[RetrievalHit]:
    promotions_dir = project_root / "data" / "promotions"
    if not promotions_dir.exists():
        return []
    hits: list[RetrievalHit] = []
    for path in sorted(promotions_dir.glob("*.json")):
        if not is_safe_project_artifact_path(path, project_root, *_PROMOTION_PREFIX):
            continue
        payload = load_json_list(path)
        if payload is None:
            continue
        rel_path = path.relative_to(project_root).as_posix()
        for candidate in payload:
            if not isinstance(candidate, dict):
                continue
            content = json_search_text(candidate)
            score = score_text(content, terms)
            if score <= 0:
                continue
            candidate_id = str(candidate.get("candidate_id", ""))
            packet_id = str(candidate.get("packet_id", ""))
            evidence = [str(item) for item in candidate.get("evidence", []) if item]
            provenance = [f"promotion:{candidate_id}", *evidence] if candidate_id else evidence
            title = candidate_id or f"Promotion candidate in {path.name}"
            hit_payload = {
                "source_type": "promotion_candidate",
                "source_path": rel_path,
                "candidate_id": candidate_id,
                "packet_id": packet_id,
                "title": title,
                "provenance": provenance,
            }
            hits.append(
                RetrievalHit(
                    hit_id=encode_hit_id(hit_payload),
                    source_type="promotion_candidate",
                    source_path=rel_path,
                    title=title,
                    snippet=make_snippet(content, terms),
                    score=score,
                    provenance=provenance,
                )
            )
    return hits


def search_wiki_patches(terms: list[str], project_root: Path) -> list[RetrievalHit]:
    wiki_patches_dir = project_root / "data" / "wiki_patches"
    if not wiki_patches_dir.exists():
        return []
    hits: list[RetrievalHit] = []
    for path in sorted(wiki_patches_dir.glob("*.json")):
        if not is_safe_project_artifact_path(path, project_root, *_WIKI_PATCH_PREFIX):
            continue
        proposal = load_json_object(path)
        if proposal is None:
            continue
        rel_path = path.relative_to(project_root).as_posix()
        packet_id = str(proposal.get("packet_id", ""))
        for operation in proposal.get("operations", []):
            if not isinstance(operation, dict):
                continue
            content = json_search_text(operation)
            score = score_text(content, terms)
            if score <= 0:
                continue
            patch_id = str(operation.get("patch_id", ""))
            candidate_id = str(operation.get("candidate_id", ""))
            evidence = [str(item) for item in operation.get("evidence", []) if item]
            provenance = [f"wiki-patch:{patch_id}", *evidence] if patch_id else evidence
            title = patch_id or f"Wiki patch in {path.name}"
            hit_payload = {
                "source_type": "wiki_patch",
                "source_path": rel_path,
                "patch_id": patch_id,
                "candidate_id": candidate_id,
                "packet_id": packet_id,
                "title": title,
                "provenance": provenance,
            }
            hits.append(
                RetrievalHit(
                    hit_id=encode_hit_id(hit_payload),
                    source_type="wiki_patch",
                    source_path=rel_path,
                    title=title,
                    snippet=make_snippet(content, terms),
                    score=score,
                    provenance=provenance,
                )
            )
    applied_log = wiki_patches_dir / "applied.jsonl"
    if applied_log.exists() and is_safe_project_artifact_path(applied_log, project_root, *_APPLIED_PATCH_PREFIX):
        hits.extend(search_applied_patch_log(terms, project_root, applied_log))
    return hits


def search_applied_patch_log(terms: list[str], project_root: Path, path: Path) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    rel_path = path.relative_to(project_root).as_posix()
    for line_index, record in iter_jsonl_objects(path):
        content = json_search_text(record)
        score = score_text(content, terms)
        if score <= 0:
            continue
        patch_id = str(record.get("patch_id", ""))
        candidate_id = str(record.get("candidate_id", ""))
        packet_id = str(record.get("packet_id", ""))
        provenance = [f"applied-patch:{patch_id}"] if patch_id else [f"applied-patch-line:{line_index}"]
        title = patch_id or f"Applied patch line {line_index}"
        payload = {
            "source_type": "applied_patch",
            "source_path": rel_path,
            "line_index": line_index,
            "patch_id": patch_id,
            "candidate_id": candidate_id,
            "packet_id": packet_id,
            "title": title,
            "provenance": provenance,
        }
        hits.append(
            RetrievalHit(
                hit_id=encode_hit_id(payload),
                source_type="applied_patch",
                source_path=rel_path,
                title=title,
                snippet=make_snippet(content, terms),
                score=score,
                provenance=provenance,
            )
        )
    return hits
