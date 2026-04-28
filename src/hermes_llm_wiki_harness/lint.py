from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from .models import ContextPacket
from .paths import HarnessPaths

_DURABLE_DIRS = (
    "entities",
    "concepts",
    "comparisons",
    "queries",
    "architectures",
    "plans",
    "01 지식",
    "02 내 아이디어",
    "03 인물과 조직",
    "04 프로젝트",
    "05 계획",
    "06 원천 자료",
)
_WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:#[^\]]+)?(?:\|[^\]]+)?\]\]")
_SOURCES_PATTERN = re.compile(r"^sources:\s*\[(.*)\]\s*$", re.MULTILINE)
_FRONTMATTER_KEY_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", re.MULTILINE)
_SESSION_ID_SLUG_PATTERN = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{6,}(?:-plan)?$")
_GENERATED_SUMMARY_PATTERN = re.compile(r"Durable\s+\w+\s+page\s+derived\s+from\s+session", re.IGNORECASE)
_TRANSIENT_TITLE_PATTERN = re.compile(r"(진행해줘|다음\s*단계|\d+번\s*단계|확인해줘)")
_SMOKE_TEST_PATTERN = re.compile(r"(자동\s*finalize\s*테스트|테스트|\btest\b|\bsmoke\b)", re.IGNORECASE)
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_ACRONYM_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]{1,}(?:-[A-Z0-9]+)?\b")
_MIN_BODY_TEXT_CHARS = 80
_MIN_RELATED_WIKILINKS = 2
_REQUIRED_SECTIONS_BY_LANG_AND_TYPE = {
    "ko": {
        "knowledge": ("개요", "배경", "상세", "예시", "한계와 주의점", "관련 문서", "출처와 근거"),
        "idea": ("개요", "배경", "핵심 아이디어", "예시", "검토할 점", "관련 문서", "출처와 근거"),
        "person": ("개요", "주요 내용", "관련 인물과 조직", "관련 문서", "출처와 근거"),
        "organization": ("개요", "주요 내용", "관련 인물과 조직", "관련 문서", "출처와 근거"),
        "project": ("개요", "목표", "배경", "현재 상태", "구조", "주요 결정", "남은 과제", "관련 문서"),
        "spec": ("개요", "목표", "요구사항", "설계", "검증 방법", "관련 문서"),
        "plan": ("개요", "목표", "단계", "검토 기준", "관련 문서"),
        "source": ("개요", "원문 정보", "핵심 내용", "이 위키에서 중요한 이유", "연결되는 지식 문서", "출처"),
        "decision": ("개요", "배경", "결정", "근거", "영향", "관련 문서"),
    },
    "en": {
        "knowledge": ("Overview", "Background", "Details", "Example", "Limitations and Caveats", "Related Pages", "Sources and Evidence"),
        "idea": ("Overview", "Background", "Core Idea", "Example", "Questions to Examine", "Related Pages", "Sources and Evidence"),
        "person": ("Overview", "Key Points", "Related People and Organizations", "Related Pages", "Sources and Evidence"),
        "organization": ("Overview", "Key Points", "Related People and Organizations", "Related Pages", "Sources and Evidence"),
        "project": ("Overview", "Goal", "Background", "Current Status", "Structure", "Key Decisions", "Remaining Work", "Related Pages"),
        "spec": ("Overview", "Goal", "Requirements", "Design", "Verification", "Related Pages"),
        "plan": ("Overview", "Goal", "Steps", "Review Criteria", "Related Pages"),
        "source": ("Overview", "Source Information", "Key Points", "Why It Matters Here", "Connected Knowledge Pages", "Source"),
        "decision": ("Overview", "Background", "Decision", "Rationale", "Impact", "Related Pages"),
    },
}


@dataclass(frozen=True)
class BrokenWikilink:
    source_page: str
    target: str

    def to_dict(self) -> dict[str, str]:
        return {"source_page": self.source_page, "target": self.target}


@dataclass(frozen=True)
class WikiLintReport:
    wiki_root: str
    checked_pages: list[str]
    missing_provenance_pages: list[str]
    orphan_pages: list[str]
    pages_missing_from_index: list[str]
    broken_wikilinks: list[BrokenWikilink]
    micro_summaries_missing_parent_unit: list[str]
    micro_summaries_with_unknown_parent_unit: list[str]
    unit_summaries_with_missing_micro_references: list[str]
    packet_micro_summaries_unreferenced: list[str]
    packets_missing_raw_pointers: list[str]
    numeric_slug_pages: list[str]
    session_id_slug_pages: list[str]
    generated_summary_only_pages: list[str]
    multiline_frontmatter_title_pages: list[str]
    transient_command_title_pages: list[str]
    smoke_or_test_pages: list[str]
    session_derived_plan_pages: list[str]
    excessive_critical_files_pages: list[str]
    missing_lang_pages: list[str]
    unsupported_lang_pages: list[str]
    missing_required_sections_pages: list[str]
    thin_content_pages: list[str]
    unexplained_english_terms_pages: list[str]
    insufficient_related_links_pages: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "wiki_root": self.wiki_root,
            "checked_pages": list(self.checked_pages),
            "missing_provenance_pages": list(self.missing_provenance_pages),
            "orphan_pages": list(self.orphan_pages),
            "pages_missing_from_index": list(self.pages_missing_from_index),
            "broken_wikilinks": [link.to_dict() for link in self.broken_wikilinks],
            "micro_summaries_missing_parent_unit": list(self.micro_summaries_missing_parent_unit),
            "micro_summaries_with_unknown_parent_unit": list(self.micro_summaries_with_unknown_parent_unit),
            "unit_summaries_with_missing_micro_references": list(self.unit_summaries_with_missing_micro_references),
            "packet_micro_summaries_unreferenced": list(self.packet_micro_summaries_unreferenced),
            "packets_missing_raw_pointers": list(self.packets_missing_raw_pointers),
            "numeric_slug_pages": list(self.numeric_slug_pages),
            "session_id_slug_pages": list(self.session_id_slug_pages),
            "generated_summary_only_pages": list(self.generated_summary_only_pages),
            "multiline_frontmatter_title_pages": list(self.multiline_frontmatter_title_pages),
            "transient_command_title_pages": list(self.transient_command_title_pages),
            "smoke_or_test_pages": list(self.smoke_or_test_pages),
            "session_derived_plan_pages": list(self.session_derived_plan_pages),
            "excessive_critical_files_pages": list(self.excessive_critical_files_pages),
            "missing_lang_pages": list(self.missing_lang_pages),
            "unsupported_lang_pages": list(self.unsupported_lang_pages),
            "missing_required_sections_pages": list(self.missing_required_sections_pages),
            "thin_content_pages": list(self.thin_content_pages),
            "unexplained_english_terms_pages": list(self.unexplained_english_terms_pages),
            "insufficient_related_links_pages": list(self.insufficient_related_links_pages),
        }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _extract_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return ""
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return ""
    return parts[0][4:]


def _extract_frontmatter_fields(frontmatter: str) -> dict[str, str]:
    return {match.group(1): match.group(2).strip() for match in _FRONTMATTER_KEY_PATTERN.finditer(frontmatter)}


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    parts = text.split("\n---\n", 1)
    return parts[1] if len(parts) == 2 else text


def _strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return re.sub(r"`[^`]*`", "", text)


def _extract_heading_titles(text: str) -> set[str]:
    return {match.group(2).strip().rstrip("#").strip() for match in _HEADING_PATTERN.finditer(text)}


def _body_text_char_count(text: str) -> int:
    body = _strip_code(_strip_frontmatter(text))
    body = re.sub(r"^#{1,6}\s+.*$", "", body, flags=re.MULTILINE)
    body = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", r"\2", body)
    body = re.sub(r"[^0-9A-Za-z가-힣]+", "", body)
    return len(body)


def _missing_required_sections(page_type: str, text: str, lang: str) -> list[str]:
    required = _REQUIRED_SECTIONS_BY_LANG_AND_TYPE.get(lang, {}).get(page_type)
    if not required:
        return []
    headings = _extract_heading_titles(_strip_frontmatter(text))
    return [section for section in required if section not in headings]


def _has_explained_acronym(term: str, body: str) -> bool:
    parenthetical_pattern = re.compile(rf"\([^)]*\b{re.escape(term)}\b[^)]*\)")
    if parenthetical_pattern.search(body):
        return True
    expansion_pattern = re.compile(rf"\b{re.escape(term)}\b\s*\([^)]{{4,}}\)")
    return bool(expansion_pattern.search(body))


def _unexplained_acronyms(text: str) -> set[str]:
    body = _strip_code(_strip_frontmatter(text))
    body = re.sub(r"\[\[[^\]]+\]\]", "", body)
    terms = {match.group(0) for match in _ACRONYM_PATTERN.finditer(body)}
    return {term for term in terms if not _has_explained_acronym(term, body)}


def _frontmatter_has_multiline_title(frontmatter: str) -> bool:
    lines = frontmatter.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("title:"):
            continue
        next_index = index + 1
        while next_index < len(lines) and not lines[next_index].strip():
            next_index += 1
        return next_index < len(lines) and not _FRONTMATTER_KEY_PATTERN.match(lines[next_index])
    return False


def _extract_sources(frontmatter: str) -> list[str]:
    match = _SOURCES_PATTERN.search(frontmatter)
    if not match:
        return []
    raw_items = match.group(1).strip()
    if not raw_items:
        return []
    items: list[str] = []
    for item in raw_items.split(","):
        cleaned = item.strip().strip('"').strip("'")
        if cleaned:
            items.append(cleaned)
    return items


def _normalize_link_target(target: str) -> str:
    cleaned = target.strip()
    cleaned = cleaned.replace("\\", "/")
    if cleaned.endswith(".md"):
        cleaned = cleaned[:-3]
    if "/" in cleaned:
        cleaned = cleaned.split("/")[-1]
    return cleaned


def _extract_wikilinks(text: str) -> list[str]:
    return [_normalize_link_target(match) for match in _WIKILINK_PATTERN.findall(text)]


def _collect_durable_pages(wiki_root: Path) -> list[Path]:
    pages: list[Path] = []
    for directory_name in _DURABLE_DIRS:
        directory = wiki_root / directory_name
        if not directory.exists():
            continue
        pages.extend(sorted(directory.rglob("*.md")))
    return sorted(pages)


def _collect_packet_exports(paths: HarnessPaths) -> list[Path]:
    packet_dir = paths.exports_dir / "context_packets"
    if not packet_dir.exists():
        return []
    return sorted(packet_dir.glob("*.json"))


def _lint_internal_artifacts(paths: HarnessPaths) -> dict[str, list[str]]:
    issues = {
        "micro_summaries_missing_parent_unit": [],
        "micro_summaries_with_unknown_parent_unit": [],
        "unit_summaries_with_missing_micro_references": [],
        "packet_micro_summaries_unreferenced": [],
        "packets_missing_raw_pointers": [],
    }

    for packet_path in _collect_packet_exports(paths):
        payload = json.loads(packet_path.read_text(encoding="utf-8"))
        packet = ContextPacket.from_dict(payload)
        unit_ids = {unit.unit_id for unit in packet.unit_summaries}
        micro_ids = {micro.micro_id for micro in packet.micro_summaries}
        referenced_micro_ids = {micro_id for unit in packet.unit_summaries for micro_id in unit.micro_ids}

        if not packet.raw_pointers:
            issues["packets_missing_raw_pointers"].append(packet.packet_id)

        for micro in packet.micro_summaries:
            if not micro.parent_unit_id:
                issues["micro_summaries_missing_parent_unit"].append(
                    f"{packet.packet_id}::{micro.micro_id}"
                )
            elif micro.parent_unit_id not in unit_ids:
                issues["micro_summaries_with_unknown_parent_unit"].append(
                    f"{packet.packet_id}::{micro.micro_id} -> {micro.parent_unit_id}"
                )
            if micro.micro_id not in referenced_micro_ids:
                issues["packet_micro_summaries_unreferenced"].append(
                    f"{packet.packet_id}::{micro.micro_id}"
                )

        for unit in packet.unit_summaries:
            for micro_id in unit.micro_ids:
                if micro_id not in micro_ids:
                    issues["unit_summaries_with_missing_micro_references"].append(
                        f"{packet.packet_id}::{unit.unit_id} -> {micro_id}"
                    )

    for key, values in issues.items():
        issues[key] = sorted(values)
    return issues


def lint_wiki(paths: HarnessPaths) -> WikiLintReport:
    wiki_root = paths.wiki_root
    page_paths = _collect_durable_pages(wiki_root)
    checked_pages = [path.relative_to(wiki_root).as_posix() for path in page_paths]

    page_name_to_path = {
        path.stem: path.relative_to(wiki_root).as_posix() for path in page_paths
    }
    inbound_links: dict[str, set[str]] = {
        rel_path: set() for rel_path in page_name_to_path.values()
    }
    missing_provenance_pages: list[str] = []
    broken_link_pairs: set[tuple[str, str]] = set()
    numeric_slug_pages: list[str] = []
    session_id_slug_pages: list[str] = []
    generated_summary_only_pages: list[str] = []
    multiline_frontmatter_title_pages: list[str] = []
    transient_command_title_pages: list[str] = []
    smoke_or_test_pages: list[str] = []
    session_derived_plan_pages: list[str] = []
    excessive_critical_files_pages: list[str] = []
    missing_lang_pages: list[str] = []
    unsupported_lang_pages: list[str] = []
    missing_required_sections_pages: list[str] = []
    thin_content_pages: list[str] = []
    unexplained_english_terms_pages: list[str] = []
    insufficient_related_links_pages: list[str] = []

    for path in page_paths:
        relative_path = path.relative_to(wiki_root).as_posix()
        text = _read_text(path)
        frontmatter = _extract_frontmatter(text)
        fields = _extract_frontmatter_fields(frontmatter)
        sources = _extract_sources(frontmatter)
        lowered = text.lower()
        title = fields.get("title", "")
        lang = fields.get("lang", "")
        if path.stem.isdigit():
            numeric_slug_pages.append(relative_path)
        if _SESSION_ID_SLUG_PATTERN.match(path.stem):
            session_id_slug_pages.append(relative_path)
        if _GENERATED_SUMMARY_PATTERN.search(text):
            generated_summary_only_pages.append(relative_path)
        if _frontmatter_has_multiline_title(frontmatter):
            multiline_frontmatter_title_pages.append(relative_path)
        if _TRANSIENT_TITLE_PATTERN.search(title):
            transient_command_title_pages.append(relative_path)
        if _SMOKE_TEST_PATTERN.search(title) or _SMOKE_TEST_PATTERN.search(text):
            smoke_or_test_pages.append(relative_path)
        if relative_path.startswith("plans/") and _SESSION_ID_SLUG_PATTERN.match(path.stem):
            session_derived_plan_pages.append(relative_path)
        if text.count("- `") > 30 and "## Critical Files" in text:
            excessive_critical_files_pages.append(relative_path)
        if not lang:
            missing_lang_pages.append(relative_path)
        elif lang not in {"ko", "en"}:
            unsupported_lang_pages.append(relative_path)
        if not sources and "## provenance" not in lowered and "derived-from" not in lowered:
            missing_provenance_pages.append(relative_path)

        page_type = fields.get("type", fields.get("category", ""))
        if _missing_required_sections(page_type, text, lang):
            missing_required_sections_pages.append(relative_path)
        if _body_text_char_count(text) < _MIN_BODY_TEXT_CHARS:
            thin_content_pages.append(relative_path)
        if lang == "ko" and _unexplained_acronyms(text):
            unexplained_english_terms_pages.append(relative_path)
        if len(set(_extract_wikilinks(text))) < _MIN_RELATED_WIKILINKS:
            insufficient_related_links_pages.append(relative_path)

        for target in _extract_wikilinks(text):
            target_path = page_name_to_path.get(target)
            if target_path is None:
                broken_link_pairs.add((relative_path, target))
                continue
            inbound_links[target_path].add(relative_path)

    index_links = set(_extract_wikilinks(_read_text(wiki_root / "index.md")))
    pages_missing_from_index = sorted(
        relative_path
        for path, relative_path in zip(page_paths, checked_pages, strict=False)
        if path.stem not in index_links
    )
    orphan_pages = sorted(
        relative_path
        for relative_path, sources in inbound_links.items()
        if not sources
    )
    broken_wikilinks = [
        BrokenWikilink(source_page=source_page, target=target)
        for source_page, target in sorted(broken_link_pairs)
    ]
    internal_issues = _lint_internal_artifacts(paths)

    return WikiLintReport(
        wiki_root=str(wiki_root),
        checked_pages=checked_pages,
        missing_provenance_pages=sorted(missing_provenance_pages),
        orphan_pages=orphan_pages,
        pages_missing_from_index=pages_missing_from_index,
        broken_wikilinks=broken_wikilinks,
        micro_summaries_missing_parent_unit=internal_issues["micro_summaries_missing_parent_unit"],
        micro_summaries_with_unknown_parent_unit=internal_issues["micro_summaries_with_unknown_parent_unit"],
        unit_summaries_with_missing_micro_references=internal_issues["unit_summaries_with_missing_micro_references"],
        packet_micro_summaries_unreferenced=internal_issues["packet_micro_summaries_unreferenced"],
        packets_missing_raw_pointers=internal_issues["packets_missing_raw_pointers"],
        numeric_slug_pages=sorted(numeric_slug_pages),
        session_id_slug_pages=sorted(session_id_slug_pages),
        generated_summary_only_pages=sorted(generated_summary_only_pages),
        multiline_frontmatter_title_pages=sorted(multiline_frontmatter_title_pages),
        transient_command_title_pages=sorted(transient_command_title_pages),
        smoke_or_test_pages=sorted(smoke_or_test_pages),
        session_derived_plan_pages=sorted(session_derived_plan_pages),
        excessive_critical_files_pages=sorted(excessive_critical_files_pages),
        missing_lang_pages=sorted(missing_lang_pages),
        unsupported_lang_pages=sorted(unsupported_lang_pages),
        missing_required_sections_pages=sorted(missing_required_sections_pages),
        thin_content_pages=sorted(thin_content_pages),
        unexplained_english_terms_pages=sorted(unexplained_english_terms_pages),
        insufficient_related_links_pages=sorted(insufficient_related_links_pages),
    )


def render_lint_report_markdown(report: WikiLintReport) -> str:
    lines = [
        "# Wiki Lint Report",
        "",
        f"- Wiki root: `{report.wiki_root}`",
        f"- Checked pages: **{len(report.checked_pages)}**",
        f"- Missing provenance: **{len(report.missing_provenance_pages)}**",
        f"- Orphan pages: **{len(report.orphan_pages)}**",
        f"- Missing from index: **{len(report.pages_missing_from_index)}**",
        f"- Broken wikilinks: **{len(report.broken_wikilinks)}**",
        f"- Human-facing quality issues: **{sum(len(items) for items in [report.numeric_slug_pages, report.session_id_slug_pages, report.generated_summary_only_pages, report.multiline_frontmatter_title_pages, report.transient_command_title_pages, report.smoke_or_test_pages, report.session_derived_plan_pages, report.excessive_critical_files_pages, report.missing_lang_pages, report.unsupported_lang_pages, report.missing_required_sections_pages, report.thin_content_pages, report.unexplained_english_terms_pages, report.insufficient_related_links_pages])}**",
        f"- Internal graph issues: **{sum(len(items) for items in [report.micro_summaries_missing_parent_unit, report.micro_summaries_with_unknown_parent_unit, report.unit_summaries_with_missing_micro_references, report.packet_micro_summaries_unreferenced, report.packets_missing_raw_pointers])}**",
        "",
        "## Missing Provenance",
    ]

    if report.missing_provenance_pages:
        lines.extend(f"- `{page}`" for page in report.missing_provenance_pages)
    else:
        lines.append("- None")

    lines.extend(["", "## Orphan Pages"])
    if report.orphan_pages:
        lines.extend(f"- `{page}`" for page in report.orphan_pages)
    else:
        lines.append("- None")

    lines.extend(["", "## Pages Missing From Index"])
    if report.pages_missing_from_index:
        lines.extend(f"- `{page}`" for page in report.pages_missing_from_index)
    else:
        lines.append("- None")

    lines.extend(["", "## Broken Wikilinks"])
    if report.broken_wikilinks:
        for link in report.broken_wikilinks:
            lines.append(f"- `{link.source_page}` → `[[{link.target}]]`")
    else:
        lines.append("- None")

    quality_sections = [
        ("Numeric slugs", report.numeric_slug_pages),
        ("Session-id slugs", report.session_id_slug_pages),
        ("Generated summary only", report.generated_summary_only_pages),
        ("Multiline frontmatter titles", report.multiline_frontmatter_title_pages),
        ("Transient command titles", report.transient_command_title_pages),
        ("Smoke/test pages", report.smoke_or_test_pages),
        ("Session-derived plans", report.session_derived_plan_pages),
        ("Excessive critical files", report.excessive_critical_files_pages),
        ("Missing language", report.missing_lang_pages),
        ("Unsupported language", report.unsupported_lang_pages),
        ("Missing required sections", report.missing_required_sections_pages),
        ("Thin content", report.thin_content_pages),
        ("Unexplained English acronyms", report.unexplained_english_terms_pages),
        ("Insufficient related links", report.insufficient_related_links_pages),
    ]
    lines.extend(["", "## Human-Facing Quality"])
    any_quality_issue = False
    for heading, items in quality_sections:
        if not items:
            continue
        any_quality_issue = True
        lines.append(f"### {heading}")
        lines.extend(f"- `{item}`" for item in items)
    if not any_quality_issue:
        lines.append("- None")

    lines.extend(["", "## Internal Artifact Graph"])
    if report.micro_summaries_missing_parent_unit:
        lines.append("### Micro summaries missing parent unit")
        lines.extend(f"- `{item}`" for item in report.micro_summaries_missing_parent_unit)
    if report.micro_summaries_with_unknown_parent_unit:
        lines.append("### Micro summaries with unknown parent unit")
        lines.extend(f"- `{item}`" for item in report.micro_summaries_with_unknown_parent_unit)
    if report.unit_summaries_with_missing_micro_references:
        lines.append("### Unit summaries with missing micro references")
        lines.extend(f"- `{item}`" for item in report.unit_summaries_with_missing_micro_references)
    if report.packet_micro_summaries_unreferenced:
        lines.append("### Unreferenced micro summaries")
        lines.extend(f"- `{item}`" for item in report.packet_micro_summaries_unreferenced)
    if report.packets_missing_raw_pointers:
        lines.append("### Packets missing raw pointers")
        lines.extend(f"- `{item}`" for item in report.packets_missing_raw_pointers)
    if not any([
        report.micro_summaries_missing_parent_unit,
        report.micro_summaries_with_unknown_parent_unit,
        report.unit_summaries_with_missing_micro_references,
        report.packet_micro_summaries_unreferenced,
        report.packets_missing_raw_pointers,
    ]):
        lines.append("- None")

    lines.append("")
    return "\n".join(lines)


def export_lint_report(
    report: WikiLintReport,
    paths: HarnessPaths,
    report_id: str = "wiki-lint",
) -> tuple[Path, Path]:
    paths.ensure_project_dirs()
    export_dir = paths.exports_dir / "lint"
    export_dir.mkdir(parents=True, exist_ok=True)

    json_path = export_dir / f"{report_id}.json"
    markdown_path = export_dir / f"{report_id}.md"

    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(render_lint_report_markdown(report), encoding="utf-8")
    return json_path, markdown_path
