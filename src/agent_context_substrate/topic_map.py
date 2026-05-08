from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import re

from .safe_paths import safe_child_path


@dataclass(frozen=True)
class TopicMapNode:
    node_id: str
    type: str
    label: str
    source_path: str
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "type": self.type,
            "label": self.label,
            "source_path": self.source_path,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TopicMapEdge:
    source: str
    target: str
    type: str
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TopicMap:
    schema_version: str
    nodes: list[TopicMapNode]
    edges: list[TopicMapEdge]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


_WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:#[^\]]+)?(?:\|[^\]]+)?\]\]")


def build_topic_map(*, project_root: Path, wiki_root: Path) -> TopicMap:
    project_root = Path(project_root)
    wiki_root = Path(wiki_root)
    builder = _TopicMapBuilder()

    _add_context_packets(builder, project_root)
    _add_claim_atoms(builder, project_root)
    _add_structured_atoms(builder, project_root)
    _add_promotion_candidates(builder, project_root)
    _add_wiki_patches(builder, project_root)
    _add_applied_patch_log(builder, project_root)
    _add_wiki_pages(builder, wiki_root)

    return TopicMap(
        schema_version="topic_map_v1",
        nodes=builder.nodes(),
        edges=builder.edges(),
    )


def export_topic_map(*, topic_map: TopicMap, project_root: Path, report_id: str = "topic_map") -> tuple[Path, Path]:
    index_dir = Path(project_root) / "data" / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    json_path = safe_child_path(index_dir, report_id, ".json", label="topic map report id")
    markdown_path = safe_child_path(index_dir, report_id, ".md", label="topic map report id")
    json_path.write_text(json.dumps(topic_map.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_topic_map_markdown(topic_map), encoding="utf-8")
    return json_path, markdown_path


def render_topic_map_markdown(topic_map: TopicMap) -> str:
    node_counts: dict[str, int] = {}
    edge_counts: dict[str, int] = {}
    for node in topic_map.nodes:
        node_counts[node.type] = node_counts.get(node.type, 0) + 1
    for edge in topic_map.edges:
        edge_counts[edge.type] = edge_counts.get(edge.type, 0) + 1

    lines = [
        "# Topic Map",
        "",
        f"- schema_version: `{topic_map.schema_version}`",
        f"- nodes={len(topic_map.nodes)}",
        f"- edges={len(topic_map.edges)}",
        "",
        "## Node Types",
    ]
    if node_counts:
        lines.extend(f"- `{kind}`: {count}" for kind, count in sorted(node_counts.items()))
    else:
        lines.append("- None")
    lines.extend(["", "## Edge Types"])
    if edge_counts:
        lines.extend(f"- `{kind}`: {count}" for kind, count in sorted(edge_counts.items()))
    else:
        lines.append("- None")
    lines.extend(["", "## Edges"])
    if topic_map.edges:
        for edge in topic_map.edges[:200]:
            lines.append(f"- `{edge.source}` --{edge.type}--> `{edge.target}`")
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


class _TopicMapBuilder:
    def __init__(self) -> None:
        self._nodes: dict[str, TopicMapNode] = {}
        self._edges: dict[tuple[str, str, str], TopicMapEdge] = {}

    def add_node(
        self,
        node_id: str,
        type: str,
        label: str,
        *,
        source_path: str = "",
        metadata: dict[str, object] | None = None,
    ) -> None:
        if node_id in self._nodes:
            return
        self._nodes[node_id] = TopicMapNode(
            node_id=node_id,
            type=type,
            label=label,
            source_path=source_path,
            metadata=dict(metadata or {}),
        )

    def add_edge(
        self,
        source: str,
        target: str,
        type: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if not source or not target:
            return
        key = (source, target, type)
        if key in self._edges:
            return
        self._edges[key] = TopicMapEdge(source=source, target=target, type=type, metadata=dict(metadata or {}))

    def nodes(self) -> list[TopicMapNode]:
        return sorted(self._nodes.values(), key=lambda node: (node.type, node.node_id))

    def edges(self) -> list[TopicMapEdge]:
        return sorted(self._edges.values(), key=lambda edge: (edge.type, edge.source, edge.target))


def _add_context_packets(builder: _TopicMapBuilder, project_root: Path) -> None:
    packet_dir = project_root / "data" / "exports" / "context_packets"
    if not packet_dir.exists():
        return
    for path in sorted(packet_dir.glob("*.json")):
        payload = _load_json_object(path)
        if not payload:
            continue
        packet_id = str(payload.get("packet_id", path.stem))
        rel_path = _relative_to(path, project_root)
        builder.add_node(
            f"packet:{packet_id}",
            "packet",
            str(payload.get("task_title") or packet_id),
            source_path=rel_path,
        )


def _add_claim_atoms(builder: _TopicMapBuilder, project_root: Path) -> None:
    claims_path = project_root / "data" / "atoms" / "claims.jsonl"
    if not claims_path.exists():
        return
    for claim in _load_jsonl_objects(claims_path):
        atom_id = str(claim.get("atom_id", ""))
        if not atom_id:
            continue
        claim_node = f"claim:{atom_id}"
        builder.add_node(
            claim_node,
            "claim",
            str(claim.get("text") or atom_id),
            source_path=_relative_to(claims_path, project_root),
            metadata={"status": str(claim.get("status", "")), "type": str(claim.get("type", ""))},
        )
        for source_ref in [str(ref) for ref in claim.get("source_refs", []) if ref]:
            evidence_node = f"evidence:{source_ref}"
            builder.add_node(evidence_node, "evidence", source_ref, metadata={"ref": source_ref})
            builder.add_edge(claim_node, evidence_node, "supported_by")
            packet_id = _packet_id_from_packet_ref(source_ref)
            if packet_id:
                packet_node = f"packet:{packet_id}"
                builder.add_node(packet_node, "packet", packet_id)
                builder.add_edge(packet_node, claim_node, "contains_claim")


def _add_structured_atoms(builder: _TopicMapBuilder, project_root: Path) -> None:
    specs = [
        ("decisions.jsonl", "decision", "text", "contains_decision"),
        ("entities.jsonl", "entity", "name", "mentions_entity"),
        ("concepts.jsonl", "concept", "name", "mentions_concept"),
        ("questions.jsonl", "question", "text", "raises_question"),
    ]
    for filename, node_type, label_key, packet_edge_type in specs:
        atom_path = project_root / "data" / "atoms" / filename
        if not atom_path.exists():
            continue
        rel_path = _relative_to(atom_path, project_root)
        for atom in _load_jsonl_objects(atom_path):
            atom_id = str(atom.get("atom_id", ""))
            if not atom_id:
                continue
            atom_node = f"{node_type}:{atom_id}"
            builder.add_node(
                atom_node,
                node_type,
                str(atom.get(label_key) or atom_id),
                source_path=rel_path,
                metadata={"status": str(atom.get("status", ""))},
            )
            for source_ref in [str(ref) for ref in atom.get("source_refs", []) if ref]:
                evidence_node = f"evidence:{source_ref}"
                builder.add_node(evidence_node, "evidence", source_ref, metadata={"ref": source_ref})
                builder.add_edge(atom_node, evidence_node, "supported_by")
                packet_id = _packet_id_from_packet_ref(source_ref)
                if packet_id:
                    packet_node = f"packet:{packet_id}"
                    builder.add_node(packet_node, "packet", packet_id)
                    builder.add_edge(packet_node, atom_node, packet_edge_type)



def _add_promotion_candidates(builder: _TopicMapBuilder, project_root: Path) -> None:
    promotions_dir = project_root / "data" / "promotions"
    if not promotions_dir.exists():
        return
    for path in sorted(promotions_dir.glob("*.json")):
        payload = _load_json(path)
        if not isinstance(payload, list):
            continue
        rel_path = _relative_to(path, project_root)
        for candidate in payload:
            if not isinstance(candidate, dict):
                continue
            candidate_id = str(candidate.get("candidate_id", ""))
            if not candidate_id:
                continue
            promotion_node = f"promotion:{candidate_id}"
            packet_id = str(candidate.get("packet_id", ""))
            builder.add_node(
                promotion_node,
                "promotion",
                candidate_id,
                source_path=rel_path,
                metadata={"status": str(candidate.get("status", "")), "target_page": str(candidate.get("target_page", ""))},
            )
            if packet_id:
                packet_node = f"packet:{packet_id}"
                builder.add_node(packet_node, "packet", packet_id)
                builder.add_edge(packet_node, promotion_node, "has_promotion")
            for evidence in [str(ref) for ref in candidate.get("evidence", []) if ref]:
                claim_id = _claim_id_from_ref(evidence)
                if claim_id:
                    claim_node = f"claim:{claim_id}"
                    builder.add_node(claim_node, "claim", claim_id)
                    builder.add_edge(claim_node, promotion_node, "promoted_as")
                else:
                    evidence_node = f"evidence:{evidence}"
                    builder.add_node(evidence_node, "evidence", evidence, metadata={"ref": evidence})
                    builder.add_edge(promotion_node, evidence_node, "supported_by")


def _add_wiki_patches(builder: _TopicMapBuilder, project_root: Path) -> None:
    patches_dir = project_root / "data" / "wiki_patches"
    if not patches_dir.exists():
        return
    for path in sorted(patches_dir.glob("*.json")):
        proposal = _load_json_object(path)
        if not proposal:
            continue
        rel_path = _relative_to(path, project_root)
        packet_id = str(proposal.get("packet_id", ""))
        for operation in proposal.get("operations", []):
            if not isinstance(operation, dict):
                continue
            patch_id = str(operation.get("patch_id", ""))
            if not patch_id:
                continue
            patch_node = f"wiki_patch:{patch_id}"
            candidate_id = str(operation.get("candidate_id", ""))
            target = str(operation.get("target", ""))
            builder.add_node(
                patch_node,
                "wiki_patch",
                patch_id,
                source_path=rel_path,
                metadata={"status": str(operation.get("status", "")), "operation": str(operation.get("operation", ""))},
            )
            if packet_id:
                packet_node = f"packet:{packet_id}"
                builder.add_node(packet_node, "packet", packet_id)
                builder.add_edge(packet_node, patch_node, "has_wiki_patch")
            if candidate_id:
                promotion_node = f"promotion:{candidate_id}"
                builder.add_node(promotion_node, "promotion", candidate_id)
                builder.add_edge(promotion_node, patch_node, "planned_as")
            if target:
                page_node = f"wiki_page:{target}"
                builder.add_node(page_node, "wiki_page", Path(target).stem, source_path=target)
                builder.add_edge(patch_node, page_node, "targets")
            for evidence in [str(ref) for ref in operation.get("evidence", []) if ref]:
                claim_id = _claim_id_from_ref(evidence)
                if claim_id:
                    claim_node = f"claim:{claim_id}"
                    builder.add_node(claim_node, "claim", claim_id)
                    builder.add_edge(claim_node, patch_node, "supports_patch")


def _add_applied_patch_log(builder: _TopicMapBuilder, project_root: Path) -> None:
    applied_path = project_root / "data" / "wiki_patches" / "applied.jsonl"
    if not applied_path.exists():
        return
    rel_path = _relative_to(applied_path, project_root)
    for index, record in enumerate(_load_jsonl_objects(applied_path)):
        patch_id = str(record.get("patch_id", ""))
        node_key = patch_id or str(index)
        applied_node = f"applied_patch:{node_key}"
        builder.add_node(
            applied_node,
            "applied_patch",
            node_key,
            source_path=rel_path,
            metadata={"target": str(record.get("target", "")), "created_at": str(record.get("created_at", ""))},
        )
        if patch_id:
            patch_node = f"wiki_patch:{patch_id}"
            builder.add_node(patch_node, "wiki_patch", patch_id)
            builder.add_edge(patch_node, applied_node, "applied_as")
        candidate_id = str(record.get("candidate_id", ""))
        if candidate_id:
            promotion_node = f"promotion:{candidate_id}"
            builder.add_node(promotion_node, "promotion", candidate_id)
            builder.add_edge(promotion_node, applied_node, "applied_from")


def _add_wiki_pages(builder: _TopicMapBuilder, wiki_root: Path) -> None:
    if not wiki_root.exists():
        return
    pages = sorted(path for path in wiki_root.rglob("*.md") if _is_searchable_wiki_path(path, wiki_root))
    stem_index = {path.stem: path.relative_to(wiki_root).as_posix() for path in pages}
    for path in pages:
        rel_path = path.relative_to(wiki_root).as_posix()
        content = path.read_text(encoding="utf-8", errors="ignore")
        page_node = f"wiki_page:{rel_path}"
        builder.add_node(page_node, "wiki_page", _markdown_title(content) or path.stem, source_path=rel_path)
        for target in _WIKILINK_PATTERN.findall(content):
            resolved = _resolve_wikilink_target(str(target), stem_index)
            if not resolved:
                continue
            target_node = f"wiki_page:{resolved}"
            builder.add_node(target_node, "wiki_page", Path(resolved).stem, source_path=resolved)
            builder.add_edge(page_node, target_node, "links_to")


def _is_searchable_wiki_path(path: Path, wiki_root: Path) -> bool:
    try:
        resolved_root = wiki_root.resolve()
        resolved_path = path.resolve()
        parts = resolved_path.relative_to(resolved_root).parts
    except (OSError, ValueError):
        return False
    return bool(parts) and not any(part.startswith(".") for part in parts) and parts[0] not in {"_system", "90 보관"}


def _resolve_wikilink_target(target: str, stem_index: dict[str, str]) -> str | None:
    cleaned = target.strip().replace("\\", "/")
    if cleaned.endswith(".md"):
        cleaned = cleaned[:-3]
    stem = cleaned.split("/")[-1]
    if stem in stem_index:
        return stem_index[stem]
    if cleaned.endswith(".md"):
        return cleaned
    return None


def _markdown_title(content: str) -> str | None:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _packet_id_from_packet_ref(ref: str) -> str | None:
    if not ref.startswith("packet:"):
        return None
    return ref.split(":", 1)[1].split("#", 1)[0]


def _claim_id_from_ref(ref: str) -> str | None:
    if not ref.startswith("claim:"):
        return None
    return ref.split(":", 1)[1]


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_json_object(path: Path) -> dict[str, object] | None:
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else None


def _load_jsonl_objects(path: Path) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _relative_to(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
