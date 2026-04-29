from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.context_packet import build_context_packet  # noqa: E402
from agent_context_substrate.models import MicroSummary, RawSessionReference, UnitSummary  # noqa: E402
from agent_context_substrate.paths import HarnessPaths  # noqa: E402
from agent_context_substrate.promotion import (  # noqa: E402
    promote_context_packet_to_plan,
    promote_context_packet_to_query,
    promote_unit_summary_to_architecture,
    promote_unit_summary_to_concept,
)


def _sample_reference(message_ids: list[int]) -> RawSessionReference:
    return RawSessionReference(
        session_id="session-1",
        message_ids=message_ids,
        source="telegram",
        started_at="1776395277.0",
        ended_at=None,
        title="Harness planning",
    )


def _sample_micro(
    micro_id: str,
    message_ids: list[int],
    files: list[str],
    concepts: list[str],
    parent_unit_id: str = "unit-1",
) -> MicroSummary:
    return MicroSummary(
        micro_id=micro_id,
        session_id="session-1",
        message_ids=message_ids,
        summary=f"Summary for {micro_id}",
        why_it_matters=f"Why {micro_id} matters",
        request=f"Request for {micro_id}",
        outcome=f"Outcome for {micro_id}",
        key_points=[f"Key point for {micro_id}"],
        follow_up_questions=[f"Open question for {micro_id}?"],
        artifacts=list(files),
        files=list(files),
        entities=["Hermes"],
        concepts=list(concepts),
        parent_unit_id=parent_unit_id,
        provenance=_sample_reference(message_ids),
    )


def _sample_unit(micro_ids: list[str]) -> UnitSummary:
    return UnitSummary(
        unit_id="unit-1",
        session_id="session-1",
        title="Build durable promotion layer",
        goal="Promote reusable outputs into the Obsidian wiki",
        decisions=["Keep promotion pages typed and provenance-rich"],
        progress=["Added query writer", "Added concept writer"],
        open_questions=["Should plans be promoted in the same module?"],
        micro_ids=list(micro_ids),
        related_pages=["agent-context-substrate", "context-packet"],
        provenance=_sample_reference([1, 2, 3]),
    )


def test_promote_context_packet_to_query_writes_frontmatter_provenance_and_wikilinks(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))
    paths = HarnessPaths(project_root=project_root)

    (wiki_root / "concepts").mkdir(parents=True, exist_ok=True)
    (wiki_root / "architectures").mkdir(parents=True, exist_ok=True)
    (wiki_root / "concepts" / "context-packet.md").write_text(
        "---\n"
        "title: Context Packet\n"
        "created: 2026-04-22\n"
        "updated: 2026-04-22\n"
        "type: concept\n"
        "tags: [knowledge-base]\n"
        "sources: [\"raw/articles/example.md\"]\n"
        "---\n\n"
        "# Context Packet\n\n"
        "Links to [[agent-context-substrate]].\n",
        encoding="utf-8",
    )
    (wiki_root / "architectures" / "agent-context-substrate.md").write_text(
        "---\n"
        "title: Agent Context Substrate\n"
        "created: 2026-04-22\n"
        "updated: 2026-04-22\n"
        "type: architecture\n"
        "tags: [implementation]\n"
        "sources: [\"raw/articles/example.md\"]\n"
        "---\n\n"
        "# Agent Context Substrate\n\n"
        "Links to [[context-packet]].\n",
        encoding="utf-8",
    )

    micro = _sample_micro(
        micro_id="micro-a",
        message_ids=[1, 2],
        files=["pyproject.toml", "src/agent_context_substrate/promotion.py"],
        concepts=["context-packet", "summarization"],
    )
    unit = _sample_unit(micro_ids=["micro-a"])
    packet = build_context_packet(
        packet_id="packet-1",
        task_title="Resume harness work",
        macro_context="Use the packet to restore context after a session reset.",
        unit_summary=unit,
        micro_summaries=[micro],
    )

    output_path = promote_context_packet_to_query(
        packet=packet,
        paths=paths,
        slug="resume-harness-work",
        title="Resume Harness Work",
        summary="Reusable recovery note for resuming the harness pipeline.",
        related_pages=["context-packet", "agent-context-substrate"],
        tags=["question", "context-packet", "implementation"],
    )

    assert output_path == wiki_root / "queries" / "resume-harness-work.md"
    markdown = output_path.read_text(encoding="utf-8")
    today = date.today().isoformat()

    assert markdown.startswith("---\n")
    assert "title: Resume Harness Work" in markdown
    assert f"created: {today}" in markdown
    assert f"updated: {today}" in markdown
    assert "type: query" in markdown
    assert 'tags: [question, context-packet, implementation]' in markdown
    assert 'context-packet:packet-1' in markdown
    assert 'hermes-session:session-1#messages=1,2' in markdown
    assert "## Summary" in markdown
    assert "## Related Pages" in markdown
    assert "[[context-packet]]" in markdown
    assert "[[agent-context-substrate]]" in markdown
    assert "## Provenance" in markdown
    assert "## Open Questions" in markdown
    assert "Should plans be promoted in the same module?" in markdown

    context_packet_page = (wiki_root / "concepts" / "context-packet.md").read_text(encoding="utf-8")
    architecture_page = (wiki_root / "architectures" / "agent-context-substrate.md").read_text(encoding="utf-8")
    assert "[[resume-harness-work]]" in context_packet_page
    assert "[[resume-harness-work]]" in architecture_page
    assert f"updated: {today}" in context_packet_page
    assert f"updated: {today}" in architecture_page


def test_promote_unit_summary_to_concept_writes_concept_page_with_micro_context(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))
    paths = HarnessPaths(project_root=project_root)

    (wiki_root / "concepts").mkdir(parents=True, exist_ok=True)
    (wiki_root / "architectures").mkdir(parents=True, exist_ok=True)
    (wiki_root / "concepts" / "context-packet.md").write_text(
        "---\n"
        "title: Context Packet\n"
        "created: 2026-04-22\n"
        "updated: 2026-04-22\n"
        "type: concept\n"
        "tags: [knowledge-base]\n"
        "sources: [\"raw/articles/example.md\"]\n"
        "---\n\n"
        "# Context Packet\n\n"
        "Links to [[agent-context-substrate]].\n",
        encoding="utf-8",
    )
    (wiki_root / "concepts" / "hierarchical-summaries.md").write_text(
        "---\n"
        "title: Hierarchical Summaries\n"
        "created: 2026-04-22\n"
        "updated: 2026-04-22\n"
        "type: concept\n"
        "tags: [knowledge-base]\n"
        "sources: [\"raw/articles/example.md\"]\n"
        "---\n\n"
        "# Hierarchical Summaries\n\n"
        "Links to [[agent-context-substrate]].\n",
        encoding="utf-8",
    )
    (wiki_root / "architectures" / "agent-context-substrate.md").write_text(
        "---\n"
        "title: Agent Context Substrate\n"
        "created: 2026-04-22\n"
        "updated: 2026-04-22\n"
        "type: architecture\n"
        "tags: [implementation]\n"
        "sources: [\"raw/articles/example.md\"]\n"
        "---\n\n"
        "# Agent Context Substrate\n\n"
        "Links to [[context-packet]].\n",
        encoding="utf-8",
    )

    micro_a = _sample_micro(
        micro_id="micro-a",
        message_ids=[1, 2],
        files=["src/agent_context_substrate/promotion.py"],
        concepts=["context-packet", "summarization"],
    )
    micro_b = _sample_micro(
        micro_id="micro-b",
        message_ids=[3],
        files=["tests/test_promotion.py"],
        concepts=["context-packet"],
    )
    unit = _sample_unit(micro_ids=["micro-a", "micro-b"])

    output_path = promote_unit_summary_to_concept(
        unit_summary=unit,
        micro_summaries=[micro_a, micro_b],
        paths=paths,
        slug="durable-promotion-layer",
        title="Durable Promotion Layer",
        summary="Concept page for the wiki promotion mechanism in the Hermes harness.",
        related_pages=["context-packet", "hierarchical-summaries"],
        tags=["summarization", "implementation", "knowledge-base"],
    )

    assert output_path == wiki_root / "concepts" / "durable-promotion-layer.md"
    markdown = output_path.read_text(encoding="utf-8")
    today = date.today().isoformat()

    assert "type: concept" in markdown
    assert 'tags: [summarization, implementation, knowledge-base]' in markdown
    assert 'hermes-session:session-1#messages=1,2,3' in markdown
    assert "## Summary" in markdown
    assert "## Goal" in markdown
    assert "Promote reusable outputs into the Obsidian wiki" in markdown
    assert "## Decisions" in markdown
    assert "Keep promotion pages typed and provenance-rich" in markdown
    assert "## Progress" in markdown
    assert "Added query writer" in markdown
    assert "## Evidence" in markdown
    assert "`micro-a`" in markdown
    assert "`micro-b`" in markdown
    assert "## Related Pages" in markdown
    assert "[[context-packet]]" in markdown
    assert "[[hierarchical-summaries]]" in markdown

    context_packet_page = (wiki_root / "concepts" / "context-packet.md").read_text(encoding="utf-8")
    hierarchical_page = (wiki_root / "concepts" / "hierarchical-summaries.md").read_text(encoding="utf-8")
    architecture_page = (wiki_root / "architectures" / "agent-context-substrate.md").read_text(encoding="utf-8")
    assert "[[durable-promotion-layer]]" in context_packet_page
    assert "[[durable-promotion-layer]]" in hierarchical_page
    assert "[[durable-promotion-layer]]" in architecture_page
    assert f"updated: {today}" in context_packet_page
    assert f"updated: {today}" in hierarchical_page
    assert f"updated: {today}" in architecture_page


def test_promote_context_packet_to_plan_writes_plan_page_with_steps_and_backlinks(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))
    paths = HarnessPaths(project_root=project_root)

    (wiki_root / "concepts").mkdir(parents=True, exist_ok=True)
    (wiki_root / "architectures").mkdir(parents=True, exist_ok=True)
    (wiki_root / "concepts" / "context-packet.md").write_text(
        "---\n"
        "title: Context Packet\n"
        "created: 2026-04-22\n"
        "updated: 2026-04-22\n"
        "type: concept\n"
        "tags: [knowledge-base]\n"
        "sources: [\"raw/articles/example.md\"]\n"
        "---\n\n"
        "# Context Packet\n",
        encoding="utf-8",
    )
    (wiki_root / "architectures" / "agent-context-substrate.md").write_text(
        "---\n"
        "title: Agent Context Substrate\n"
        "created: 2026-04-22\n"
        "updated: 2026-04-22\n"
        "type: architecture\n"
        "tags: [implementation]\n"
        "sources: [\"raw/articles/example.md\"]\n"
        "---\n\n"
        "# Agent Context Substrate\n",
        encoding="utf-8",
    )

    micro = _sample_micro(
        micro_id="micro-a",
        message_ids=[1, 2],
        files=["pyproject.toml", "src/agent_context_substrate/promotion.py"],
        concepts=["context-packet", "summarization"],
    )
    unit = _sample_unit(micro_ids=["micro-a"])
    packet = build_context_packet(
        packet_id="packet-plan-1",
        task_title="Resume harness execution plan",
        macro_context="Resume the promotion rollout without replaying the full session.",
        unit_summary=unit,
        micro_summaries=[micro],
    )

    output_path = promote_context_packet_to_plan(
        packet=packet,
        paths=paths,
        slug="resume-harness-plan",
        title="Resume Harness Plan",
        summary="Actionable plan page derived from the context packet.",
        related_pages=["context-packet", "agent-context-substrate"],
        tags=["plan", "implementation", "context-packet"],
    )

    markdown = output_path.read_text(encoding="utf-8")
    today = date.today().isoformat()

    assert output_path == wiki_root / "plans" / "resume-harness-plan.md"
    assert "type: plan" in markdown
    assert 'tags: [plan, implementation, context-packet]' in markdown
    assert "## Objective" in markdown
    assert "Resume harness execution plan" in markdown
    assert "## Proposed Steps" in markdown
    assert "- [ ] **Build durable promotion layer** — Promote reusable outputs into the Obsidian wiki" in markdown
    assert "## Critical Files" in markdown
    assert "## Provenance" in markdown
    assert "[[context-packet]]" in markdown
    assert "[[agent-context-substrate]]" in markdown

    context_packet_page = (wiki_root / "concepts" / "context-packet.md").read_text(encoding="utf-8")
    architecture_page = (wiki_root / "architectures" / "agent-context-substrate.md").read_text(encoding="utf-8")
    assert "[[resume-harness-plan]]" in context_packet_page
    assert "[[resume-harness-plan]]" in architecture_page
    assert f"updated: {today}" in context_packet_page
    assert f"updated: {today}" in architecture_page


def test_promote_unit_summary_to_architecture_writes_architecture_page_with_decisions_and_artifacts(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))
    paths = HarnessPaths(project_root=project_root)

    (wiki_root / "concepts").mkdir(parents=True, exist_ok=True)
    (wiki_root / "architectures").mkdir(parents=True, exist_ok=True)
    (wiki_root / "concepts" / "hierarchical-summaries.md").write_text(
        "---\n"
        "title: Hierarchical Summaries\n"
        "created: 2026-04-22\n"
        "updated: 2026-04-22\n"
        "type: concept\n"
        "tags: [knowledge-base]\n"
        "sources: [\"raw/articles/example.md\"]\n"
        "---\n\n"
        "# Hierarchical Summaries\n",
        encoding="utf-8",
    )
    (wiki_root / "architectures" / "agent-context-substrate.md").write_text(
        "---\n"
        "title: Agent Context Substrate\n"
        "created: 2026-04-22\n"
        "updated: 2026-04-22\n"
        "type: architecture\n"
        "tags: [implementation]\n"
        "sources: [\"raw/articles/example.md\"]\n"
        "---\n\n"
        "# Agent Context Substrate\n",
        encoding="utf-8",
    )

    micro_a = _sample_micro(
        micro_id="micro-a",
        message_ids=[1, 2],
        files=["src/agent_context_substrate/promotion.py"],
        concepts=["context-packet", "summarization"],
    )
    micro_b = _sample_micro(
        micro_id="micro-b",
        message_ids=[3],
        files=["tests/test_promotion.py"],
        concepts=["context-packet"],
    )
    unit = _sample_unit(micro_ids=["micro-a", "micro-b"])

    output_path = promote_unit_summary_to_architecture(
        unit_summary=unit,
        micro_summaries=[micro_a, micro_b],
        paths=paths,
        slug="promotion-system-architecture",
        title="Promotion System Architecture",
        summary="Architecture page for how packet outputs become durable wiki pages.",
        related_pages=["hierarchical-summaries", "agent-context-substrate"],
        tags=["implementation", "architecture", "summarization"],
    )

    markdown = output_path.read_text(encoding="utf-8")
    today = date.today().isoformat()

    assert output_path == wiki_root / "architectures" / "promotion-system-architecture.md"
    assert "type: architecture" in markdown
    assert 'tags: [implementation, architecture, summarization]' in markdown
    assert "## Goal" in markdown
    assert "Promote reusable outputs into the Obsidian wiki" in markdown
    assert "## Architectural Decisions" in markdown
    assert "Keep promotion pages typed and provenance-rich" in markdown
    assert "## Key Artifacts" in markdown
    assert "`src/agent_context_substrate/promotion.py`" in markdown
    assert "`tests/test_promotion.py`" in markdown
    assert "## Evidence" in markdown
    assert "Outcome for micro-a" in markdown
    assert "Request for micro-b" in markdown
    assert "[[hierarchical-summaries]]" in markdown
    assert "[[agent-context-substrate]]" in markdown

    hierarchical_page = (wiki_root / "concepts" / "hierarchical-summaries.md").read_text(encoding="utf-8")
    architecture_page = (wiki_root / "architectures" / "agent-context-substrate.md").read_text(encoding="utf-8")
    assert "[[promotion-system-architecture]]" in hierarchical_page
    assert "[[promotion-system-architecture]]" in architecture_page
    assert f"updated: {today}" in hierarchical_page
    assert f"updated: {today}" in architecture_page
