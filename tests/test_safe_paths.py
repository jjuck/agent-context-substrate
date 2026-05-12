from __future__ import annotations

from pathlib import Path

import pytest

from agent_context_substrate.context_packet import export_context_packet
from agent_context_substrate.lint import WikiLintReport, export_lint_report
from agent_context_substrate.models import ContextPacket
from agent_context_substrate.paths import HarnessPaths
from agent_context_substrate.safe_paths import (
    is_safe_project_artifact_path,
    is_safe_wiki_page_path,
    safe_artifact_stem,
    safe_child_path,
    safe_wiki_target_path,
)
from agent_context_substrate.topic_map import TopicMap, export_topic_map


def test_safe_artifact_stem_rejects_path_like_values() -> None:
    for value in ["../escape", "/tmp/escape", "nested/name", r"nested\\name", "", ".hidden"]:
        with pytest.raises(ValueError):
            safe_artifact_stem(value, label="test id")


def test_safe_child_path_keeps_output_inside_directory(tmp_path: Path) -> None:
    base = tmp_path / "data"
    base.mkdir()
    assert safe_child_path(base, "report-1", ".json").parent == base
    with pytest.raises(ValueError):
        safe_child_path(base, "../escape", ".json")


def test_safe_project_artifact_path_rejects_symlink_escape(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    promotions_dir = project_root / "data" / "promotions"
    promotions_dir.mkdir(parents=True)
    inside = promotions_dir / "packet-1.json"
    inside.write_text("[]", encoding="utf-8")
    outside = tmp_path / "outside.json"
    outside.write_text("[]", encoding="utf-8")
    escaping_link = promotions_dir / "linked.json"
    escaping_link.symlink_to(outside)

    assert is_safe_project_artifact_path(inside, project_root, "data", "promotions") is True
    assert is_safe_project_artifact_path(escaping_link, project_root, "data", "promotions") is False


def test_safe_project_artifact_path_rejects_symlinked_allowed_directory(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True)
    outside_promotions = tmp_path / "outside-promotions"
    outside_promotions.mkdir()
    outside_artifact = outside_promotions / "packet-1.json"
    outside_artifact.write_text("[]", encoding="utf-8")
    (data_dir / "promotions").symlink_to(outside_promotions, target_is_directory=True)

    assert is_safe_project_artifact_path(outside_artifact, project_root, "data", "promotions") is False


def test_safe_wiki_page_path_rejects_system_hidden_non_markdown_and_escape(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    page = wiki_root / "concepts" / "summarization.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Summarization\n", encoding="utf-8")
    hidden = wiki_root / ".hidden" / "page.md"
    hidden.parent.mkdir(parents=True)
    hidden.write_text("# Hidden\n", encoding="utf-8")
    system = wiki_root / "_system" / "secret.md"
    system.parent.mkdir(parents=True)
    system.write_text("# Secret\n", encoding="utf-8")
    non_markdown = wiki_root / "concepts" / "data.json"
    non_markdown.write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    escaping_link = wiki_root / "concepts" / "linked.md"
    escaping_link.symlink_to(outside)

    assert is_safe_wiki_page_path(page, wiki_root) is True
    assert is_safe_wiki_page_path(hidden, wiki_root) is False
    assert is_safe_wiki_page_path(system, wiki_root) is False
    assert is_safe_wiki_page_path(non_markdown, wiki_root) is False
    assert is_safe_wiki_page_path(outside, wiki_root) is False
    assert is_safe_wiki_page_path(escaping_link, wiki_root) is False


def test_safe_wiki_target_path_rejects_system_hidden_non_markdown_and_escape(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"

    accepted = safe_wiki_target_path(wiki_root=wiki_root, target="concepts/summarization.md")

    assert accepted == (wiki_root / "concepts" / "summarization.md").resolve()
    for target in ["../outside.md", "/tmp/outside.md", "_system/secret.md", "90 보관/old.md", ".hidden/page.md", "concepts/data.json"]:
        assert safe_wiki_target_path(wiki_root=wiki_root, target=target) is None


def test_export_topic_map_rejects_unsafe_report_id(tmp_path: Path) -> None:
    topic_map = TopicMap(schema_version="topic_map_v1", nodes=[], edges=[])
    with pytest.raises(ValueError):
        export_topic_map(topic_map=topic_map, project_root=tmp_path, report_id=str(tmp_path / "escape"))
    assert not (tmp_path / "escape.json").exists()


def test_export_lint_report_rejects_unsafe_report_id(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    report = WikiLintReport(
        wiki_root=str(tmp_path / "wiki"),
        checked_pages=[],
        missing_provenance_pages=[],
        orphan_pages=[],
        pages_missing_from_index=[],
        broken_wikilinks=[],
        micro_summaries_missing_parent_unit=[],
        micro_summaries_with_unknown_parent_unit=[],
        unit_summaries_with_missing_micro_references=[],
        packet_micro_summaries_unreferenced=[],
        packets_missing_raw_pointers=[],
        numeric_slug_pages=[],
        session_id_slug_pages=[],
        generated_summary_only_pages=[],
        multiline_frontmatter_title_pages=[],
        transient_command_title_pages=[],
        smoke_or_test_pages=[],
        session_derived_plan_pages=[],
        excessive_critical_files_pages=[],
        missing_lang_pages=[],
        unsupported_lang_pages=[],
        missing_required_sections_pages=[],
        thin_content_pages=[],
        unexplained_english_terms_pages=[],
        insufficient_related_links_pages=[],
    )
    with pytest.raises(ValueError):
        export_lint_report(report, paths, report_id="../escape")


def test_export_context_packet_rejects_unsafe_packet_id(tmp_path: Path) -> None:
    paths = HarnessPaths(project_root=tmp_path / "project")
    packet = ContextPacket(packet_id="../escape", task_title="x", macro_context="x")
    with pytest.raises(ValueError):
        export_context_packet(packet, paths)
