from __future__ import annotations

from datetime import date
from pathlib import Path
import re

from .models import ContextPacket, MicroSummary, RawSessionReference, UnitSummary
from .paths import HarnessPaths
from .safe_paths import is_safe_wiki_page_path, safe_child_path

_RELATED_SECTION_HEADING = "## Related Pages"
_UPDATED_PATTERN = re.compile(r"^updated:\s*.+$", re.MULTILINE)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _normalize_page_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return cleaned
    cleaned = cleaned.replace("\\", "/")
    if cleaned.endswith(".md"):
        cleaned = cleaned[:-3]
    if "/" in cleaned:
        cleaned = cleaned.split("/")[-1]
    return cleaned


def _format_inline_list(values: list[str], quote: bool = False) -> str:
    items = [value for value in values if value]
    if quote:
        rendered = ", ".join(f'"{value}"' for value in items)
    else:
        rendered = ", ".join(items)
    return f"[{rendered}]"


def _format_provenance_reference(reference: RawSessionReference) -> str:
    return reference.source_ref()


def _render_related_pages(related_pages: list[str]) -> list[str]:
    normalized = _dedupe([_normalize_page_name(page) for page in related_pages])
    return [f"[[{page}]]" for page in normalized]


def _find_existing_page(wiki_root: Path, slug: str) -> Path | None:
    normalized_slug = _normalize_page_name(slug)
    if not normalized_slug:
        return None
    matches = sorted(
        path for path in wiki_root.rglob("*.md") if path.stem == normalized_slug and is_safe_wiki_page_path(path, wiki_root)
    )
    return matches[0] if matches else None


def _update_frontmatter_updated(text: str, today: str) -> str:
    if not text.startswith("---\n"):
        return text
    updated_line = f"updated: {today}"
    if _UPDATED_PATTERN.search(text):
        return _UPDATED_PATTERN.sub(updated_line, text, count=1)
    parts = text.split("\n", 2)
    if len(parts) >= 2:
        return f"---\n{updated_line}\n{text[4:]}"
    return text


def _append_backlink(page_path: Path, backlink_slug: str) -> None:
    if not page_path.exists():
        return
    backlink = f"[[{backlink_slug}]]"
    text = page_path.read_text(encoding="utf-8")
    if backlink in text:
        return

    today = date.today().isoformat()
    updated_text = _update_frontmatter_updated(text, today)
    lines = updated_text.splitlines()
    try:
        section_index = lines.index(_RELATED_SECTION_HEADING)
    except ValueError:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend([_RELATED_SECTION_HEADING, f"- {backlink}"])
    else:
        insert_at = section_index + 1
        while insert_at < len(lines) and not lines[insert_at].startswith("## "):
            insert_at += 1
        lines.insert(insert_at, f"- {backlink}")
    page_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sync_backlinks(wiki_root: Path, related_pages: list[str], backlink_slug: str) -> None:
    for page_name in _dedupe([_normalize_page_name(page) for page in related_pages]):
        existing_page = _find_existing_page(wiki_root, page_name)
        if existing_page is None:
            continue
        _append_backlink(existing_page, backlink_slug)


def _write_markdown_page(
    *,
    root_dir: Path,
    slug: str,
    title: str,
    page_type: str,
    tags: list[str],
    source_refs: list[str],
    body_lines: list[str],
) -> Path:
    output_path = safe_child_path(root_dir, slug, ".md", label="wiki promotion slug")
    root_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    markdown = "\n".join(
        [
            "---",
            f"title: {title}",
            f"created: {today}",
            f"updated: {today}",
            f"type: {page_type}",
            f"tags: {_format_inline_list(_dedupe(tags))}",
            f"sources: {_format_inline_list(_dedupe(source_refs), quote=True)}",
            "---",
            "",
            *body_lines,
            "",
        ]
    )
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def _relevant_micro_summaries(
    unit_summary: UnitSummary,
    micro_summaries: list[MicroSummary],
) -> list[MicroSummary]:
    return [
        summary_item
        for summary_item in micro_summaries
        if summary_item.micro_id in unit_summary.micro_ids
    ]


def _unit_source_refs(unit_summary: UnitSummary, micro_summaries: list[MicroSummary]) -> list[str]:
    source_refs: list[str] = []
    if unit_summary.provenance is not None:
        source_refs.append(_format_provenance_reference(unit_summary.provenance))
    source_refs.extend(
        _format_provenance_reference(summary_item.provenance)
        for summary_item in micro_summaries
        if summary_item.provenance is not None
    )
    return _dedupe(source_refs)


def _collect_files_from_micros(micro_summaries: list[MicroSummary]) -> list[str]:
    return _dedupe(
        [
            file_path
            for summary_item in micro_summaries
            for file_path in summary_item.files
        ]
    )


def _render_micro_evidence(summary_item: MicroSummary) -> str:
    parts: list[str] = []
    if summary_item.request:
        parts.append(f"Request: {summary_item.request}")
    if summary_item.outcome:
        parts.append(f"Outcome: {summary_item.outcome}")
    if not parts:
        parts.append(summary_item.summary)
    if summary_item.key_points:
        parts.append(f"Key points: {'; '.join(summary_item.key_points[:3])}")
    files = ", ".join(f"`{file_path}`" for file_path in summary_item.files)
    file_suffix = f" | files: {files}" if files else ""
    return f"- `{summary_item.micro_id}`: {' | '.join(parts)}{file_suffix}"


def _render_rubric_body(
    *,
    title: str,
    summary: str,
    understanding: list[str],
    evidence: list[str],
    related_links: list[str],
    open_questions: list[str],
) -> list[str]:
    body_lines = [
        f"# {title}",
        "",
        "## Current Understanding",
        summary,
    ]
    body_lines.extend(_prefixed_lines(understanding))

    if evidence:
        body_lines.extend(["", "## Evidence and Provenance"])
        body_lines.extend(evidence)

    if related_links:
        body_lines.extend(["", "## Connections"])
        for link in related_links:
            body_lines.append(f"- {link}")

    if open_questions:
        body_lines.extend(["", "## Open Questions"])
        for question in open_questions:
            body_lines.append(f"- {question}")

    return body_lines


def _prefixed_lines(lines: list[str]) -> list[str]:
    return [line if line.startswith(("- ", "- [ ] ")) else f"- {line}" for line in lines if line]


def promote_context_packet_to_query(
    *,
    packet: ContextPacket,
    paths: HarnessPaths,
    slug: str,
    title: str,
    summary: str,
    related_pages: list[str] | None = None,
    tags: list[str] | None = None,
) -> Path:
    related_links = _render_related_pages(list(related_pages or []))
    source_refs = [f"context-packet:{packet.packet_id}"]
    source_refs.extend(
        _format_provenance_reference(pointer) for pointer in packet.raw_pointers
    )

    understanding = [f"Task: {packet.task_title}", f"Context: {packet.macro_context}"]

    if packet.critical_files:
        for file_path in packet.critical_files:
            understanding.append(f"Relevant file: `{file_path}`")

    evidence = [f"- Context packet: `{packet.packet_id}`"]
    for pointer in packet.raw_pointers:
        evidence.append(
            "- "
            f"`{_format_provenance_reference(pointer)}`"
            f" ({pointer.source}; title={pointer.title or 'unknown'})"
        )
    body_lines = _render_rubric_body(
        title=title,
        summary=summary,
        understanding=understanding,
        evidence=evidence,
        related_links=related_links,
        open_questions=list(packet.open_questions),
    )

    output_path = _write_markdown_page(
        root_dir=paths.wiki_root / "queries",
        slug=slug,
        title=title,
        page_type="query",
        tags=list(tags or []),
        source_refs=source_refs,
        body_lines=body_lines,
    )
    _sync_backlinks(paths.wiki_root, list(related_pages or []), slug)
    return output_path


def promote_context_packet_to_plan(
    *,
    packet: ContextPacket,
    paths: HarnessPaths,
    slug: str,
    title: str,
    summary: str,
    related_pages: list[str] | None = None,
    tags: list[str] | None = None,
) -> Path:
    related_links = _render_related_pages(list(related_pages or []))
    source_refs = [f"context-packet:{packet.packet_id}"]
    source_refs.extend(
        _format_provenance_reference(pointer) for pointer in packet.raw_pointers
    )

    understanding = [f"Objective: {packet.task_title}", f"Context: {packet.macro_context}"]
    for unit in packet.unit_summaries:
        understanding.append(f"- [ ] **{unit.title}** - {unit.goal}")
    for file_path in packet.critical_files:
        understanding.append(f"Relevant file: `{file_path}`")
    evidence = [f"- Context packet: `{packet.packet_id}`"]
    for pointer in packet.raw_pointers:
        evidence.append(
            "- "
            f"`{_format_provenance_reference(pointer)}`"
            f" ({pointer.source}; title={pointer.title or 'unknown'})"
        )
    body_lines = _render_rubric_body(
        title=title,
        summary=summary,
        understanding=understanding,
        evidence=evidence,
        related_links=related_links,
        open_questions=list(packet.open_questions),
    )

    output_path = _write_markdown_page(
        root_dir=paths.wiki_root / "plans",
        slug=slug,
        title=title,
        page_type="plan",
        tags=list(tags or []),
        source_refs=source_refs,
        body_lines=body_lines,
    )
    _sync_backlinks(paths.wiki_root, list(related_pages or []), slug)
    return output_path


def promote_unit_summary_to_concept(
    *,
    unit_summary: UnitSummary,
    micro_summaries: list[MicroSummary],
    paths: HarnessPaths,
    slug: str,
    title: str,
    summary: str,
    related_pages: list[str] | None = None,
    tags: list[str] | None = None,
) -> Path:
    relevant_micro_summaries = _relevant_micro_summaries(unit_summary, micro_summaries)
    related_links = _render_related_pages(
        list(unit_summary.related_pages) + list(related_pages or [])
    )
    source_refs = _unit_source_refs(unit_summary, relevant_micro_summaries)

    understanding = [f"Source unit: {unit_summary.title}", f"Goal: {unit_summary.goal}"]
    for decision in unit_summary.decisions:
        understanding.append(f"Decision: {decision}")
    for item in unit_summary.progress:
        understanding.append(f"Progress: {item}")
    evidence: list[str] = []
    for summary_item in relevant_micro_summaries:
        files = ", ".join(f"`{file_path}`" for file_path in summary_item.files)
        file_suffix = f" | files: {files}" if files else ""
        evidence.append(f"- `{summary_item.micro_id}`: {summary_item.summary}{file_suffix}")
    if unit_summary.provenance is not None:
        evidence.append(f"- Unit summary: `{_format_provenance_reference(unit_summary.provenance)}`")
    for summary_item in relevant_micro_summaries:
        if summary_item.provenance is None:
            continue
        evidence.append(f"- Micro `{summary_item.micro_id}`: `{_format_provenance_reference(summary_item.provenance)}`")
    body_lines = _render_rubric_body(
        title=title,
        summary=summary,
        understanding=understanding,
        evidence=evidence,
        related_links=related_links,
        open_questions=list(unit_summary.open_questions),
    )

    output_path = _write_markdown_page(
        root_dir=paths.wiki_root / "concepts",
        slug=slug,
        title=title,
        page_type="concept",
        tags=list(tags or []),
        source_refs=source_refs,
        body_lines=body_lines,
    )
    _sync_backlinks(
        paths.wiki_root,
        list(unit_summary.related_pages) + list(related_pages or []),
        slug,
    )
    return output_path


def promote_unit_summary_to_architecture(
    *,
    unit_summary: UnitSummary,
    micro_summaries: list[MicroSummary],
    paths: HarnessPaths,
    slug: str,
    title: str,
    summary: str,
    related_pages: list[str] | None = None,
    tags: list[str] | None = None,
) -> Path:
    relevant_micro_summaries = _relevant_micro_summaries(unit_summary, micro_summaries)
    related_links = _render_related_pages(
        list(unit_summary.related_pages) + list(related_pages or [])
    )
    source_refs = _unit_source_refs(unit_summary, relevant_micro_summaries)
    key_artifacts = _collect_files_from_micros(relevant_micro_summaries)

    understanding = [f"Scope: {unit_summary.title}", f"Goal: {unit_summary.goal}"]
    for decision in unit_summary.decisions:
        understanding.append(f"Decision: {decision}")
    for file_path in key_artifacts:
        understanding.append(f"Artifact: `{file_path}`")
    evidence = [_render_micro_evidence(summary_item) for summary_item in relevant_micro_summaries]
    if unit_summary.provenance is not None:
        evidence.append(f"- Unit summary: `{_format_provenance_reference(unit_summary.provenance)}`")
    for summary_item in relevant_micro_summaries:
        if summary_item.provenance is None:
            continue
        evidence.append(f"- Micro `{summary_item.micro_id}`: `{_format_provenance_reference(summary_item.provenance)}`")
    body_lines = _render_rubric_body(
        title=title,
        summary=summary,
        understanding=understanding,
        evidence=evidence,
        related_links=related_links,
        open_questions=list(unit_summary.open_questions),
    )

    output_path = _write_markdown_page(
        root_dir=paths.wiki_root / "architectures",
        slug=slug,
        title=title,
        page_type="architecture",
        tags=list(tags or []),
        source_refs=source_refs,
        body_lines=body_lines,
    )
    _sync_backlinks(
        paths.wiki_root,
        list(unit_summary.related_pages) + list(related_pages or []),
        slug,
    )
    return output_path
