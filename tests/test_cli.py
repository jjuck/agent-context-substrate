import argparse
import json
import pytest
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import agent_context_substrate.cli as cli  # noqa: E402
from agent_context_substrate.cli import main  # noqa: E402
from agent_context_substrate.commands.artifacts import register_artifact_commands  # noqa: E402


def test_artifact_command_module_registers_artifact_parsers() -> None:
    parser = argparse.ArgumentParser(prog="agent-context-substrate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_project_root(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--project-root", default="project-root")

    register_artifact_commands(subparsers, add_project_root_argument=add_project_root)

    review_args = parser.parse_args(["review-promotion", "--candidate-id", "candidate-1"])
    assert review_args.command == "review-promotion"
    assert review_args.candidate_id == ["candidate-1"]
    assert review_args.project_root == "project-root"

    lint_args = parser.parse_args(["lint-promotions", "--fail-on-issues", "--report-id", "lint-1"])
    assert lint_args.command == "lint-promotions"
    assert lint_args.fail_on_issues is True
    assert lint_args.report_id == "lint-1"

    topic_args = parser.parse_args(["build-topic-map", "--wiki-root", "wiki", "--report-id", "topic-1"])
    assert topic_args.command == "build-topic-map"
    assert topic_args.wiki_root == "wiki"
    assert topic_args.report_id == "topic-1"


@pytest.mark.parametrize(
    ("handler_name", "argv"),
    [
        ("handle_init_wiki_command", ["init-wiki", "--wiki-root", "{wiki}"]),
        (
            "handle_install_plugin_command",
            ["install-plugin", "--hermes-home", "{home}", "--project-root", "{project}", "--wiki-root", "{wiki}"],
        ),
        (
            "handle_install_context_engine_command",
            ["install-context-engine", "--hermes-agent-root", "{agent}"],
        ),
        (
            "handle_doctor_command",
            [
                "doctor",
                "--hermes-home",
                "{home}",
                "--project-root",
                "{project}",
                "--wiki-root",
                "{wiki}",
                "--hermes-agent-root",
                "{agent}",
            ],
        ),
        (
            "handle_fresh_install_smoke_command",
            [
                "fresh-install-smoke",
                "--session-id",
                "session-1",
                "--hermes-home",
                "{home}",
                "--project-root",
                "{project}",
                "--wiki-root",
                "{wiki}",
            ],
        ),
        ("handle_extract_session_command", ["extract-session", "--session-id", "session-1", "--project-root", "{project}"]),
        ("handle_extract_atoms_command", ["extract-atoms", "--packet-id", "packet-1", "--project-root", "{project}"]),
        ("handle_propose_promotions_command", ["propose-promotions", "--packet-id", "packet-1", "--project-root", "{project}"]),
        (
            "handle_plan_wiki_patches_command",
            ["plan-wiki-patches", "--promotion-file", "{promotion}", "--project-root", "{project}"],
        ),
        ("handle_apply_wiki_patch_command", ["apply-wiki-patch", "--patch-file", "{patch}", "--project-root", "{project}"]),
        ("handle_list_promotions_command", ["list-promotions", "--project-root", "{project}"]),
        (
            "handle_review_promotion_command",
            [
                "review-promotion",
                "--candidate-id",
                "packet-1-candidate-1",
                "--status",
                "accepted",
                "--note",
                "looks useful",
                "--project-root",
                "{project}",
            ],
        ),
        ("handle_list_wiki_patches_command", ["list-wiki-patches", "--project-root", "{project}"]),
        ("handle_lint_promotions_command", ["lint-promotions", "--project-root", "{project}"]),
        ("handle_build_topic_map_command", ["build-topic-map", "--project-root", "{project}"]),
        (
            "handle_build_context_packet_command",
            [
                "build-context-packet",
                "--session-id",
                "session-1",
                "--packet-id",
                "packet-1",
                "--task-title",
                "Task",
                "--macro-context",
                "Context",
                "--unit-title",
                "Unit",
                "--goal",
                "Goal",
                "--project-root",
                "{project}",
            ],
        ),
        (
            "handle_promote_packet_query_command",
            [
                "promote-packet-query",
                "--packet-json",
                "{packet}",
                "--slug",
                "slug",
                "--title",
                "Title",
                "--summary",
                "Summary",
                "--project-root",
                "{project}",
            ],
        ),
        (
            "handle_promote_packet_plan_command",
            [
                "promote-packet-plan",
                "--packet-json",
                "{packet}",
                "--slug",
                "slug",
                "--title",
                "Title",
                "--summary",
                "Summary",
                "--project-root",
                "{project}",
            ],
        ),
        (
            "handle_promote_unit_concept_command",
            [
                "promote-unit-concept",
                "--packet-json",
                "{packet}",
                "--slug",
                "slug",
                "--title",
                "Title",
                "--summary",
                "Summary",
                "--project-root",
                "{project}",
            ],
        ),
        (
            "handle_promote_unit_architecture_command",
            [
                "promote-unit-architecture",
                "--packet-json",
                "{packet}",
                "--slug",
                "slug",
                "--title",
                "Title",
                "--summary",
                "Summary",
                "--project-root",
                "{project}",
            ],
        ),
        (
            "handle_run_e2e_pipeline_command",
            [
                "run-e2e-pipeline",
                "--session-id",
                "session-1",
                "--packet-id",
                "packet-1",
                "--task-title",
                "Task",
                "--macro-context",
                "Context",
                "--unit-title",
                "Unit",
                "--goal",
                "Goal",
                "--project-root",
                "{project}",
            ],
        ),
        ("handle_lint_wiki_command", ["lint-wiki", "--project-root", "{project}"]),
    ],
)
def test_cli_delegates_remaining_commands_to_extracted_handlers(
    monkeypatch, tmp_path: Path, handler_name: str, argv: list[str]
) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    home = tmp_path / "home"
    agent_root = tmp_path / "agent"
    promotion_file = tmp_path / "promotion.json"
    patch_file = tmp_path / "patch.json"
    packet_file = tmp_path / "packet.json"
    calls = []

    def fake_handler(**kwargs):
        calls.append(kwargs)
        return 37

    monkeypatch.setattr(cli, handler_name, fake_handler, raising=True)
    rendered_argv = [
        item.format(
            project=project_root,
            wiki=wiki_root,
            home=home,
            agent=agent_root,
            promotion=promotion_file,
            patch=patch_file,
            packet=packet_file,
        )
        for item in argv
    ]

    assert cli.main(rendered_argv) == 37
    assert calls


def _build_sample_state_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            user_id TEXT,
            model TEXT,
            model_config TEXT,
            system_prompt TEXT,
            parent_session_id TEXT,
            started_at REAL NOT NULL,
            ended_at REAL,
            end_reason TEXT,
            message_count INTEGER DEFAULT 0,
            tool_call_count INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            cache_write_tokens INTEGER DEFAULT 0,
            reasoning_tokens INTEGER DEFAULT 0,
            billing_provider TEXT,
            billing_base_url TEXT,
            billing_mode TEXT,
            estimated_cost_usd REAL,
            actual_cost_usd REAL,
            cost_status TEXT,
            cost_source TEXT,
            pricing_version TEXT,
            title TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_call_id TEXT,
            tool_calls TEXT,
            tool_name TEXT,
            timestamp REAL NOT NULL,
            token_count INTEGER,
            finish_reason TEXT,
            reasoning TEXT,
            reasoning_details TEXT,
            codex_reasoning_items TEXT
        )
        """
    )
    cur.execute(
        "INSERT INTO sessions (id, source, started_at, message_count, title) VALUES (?, ?, ?, ?, ?)",
        ("session-1", "telegram", 1776395277.0, 2, "Harness planning"),
    )
    cur.executemany(
        "INSERT INTO messages (id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        [
            (
                1,
                "session-1",
                "user",
                "Create the project scaffold with pyproject.toml and src/agent_context_substrate/models.py",
                1776395278.0,
            ),
            (
                2,
                "session-1",
                "assistant",
                "I will bootstrap the project structure and add tests/test_models.py for the scaffold.",
                1776395280.0,
            ),
        ],
    )
    conn.commit()
    conn.close()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_cli_build_context_packet_delegates_to_command_handler(tmp_path, monkeypatch) -> None:
    import agent_context_substrate.cli as cli_module

    project_root = tmp_path / "project"
    project_root.mkdir()
    calls = []

    def fake_handler(
        *,
        args,
        parser,
        paths,
        build_packet_from_session,
        export_v2_summary_artifacts,
        summary_routing_hints,
        llm_safety_options,
    ):
        calls.append(
            {
                "command": args.command,
                "packet_id": args.packet_id,
                "project_root": paths.project_root,
                "has_build_callback": callable(build_packet_from_session),
                "has_v2_callback": callable(export_v2_summary_artifacts),
                "has_routing_callback": callable(summary_routing_hints),
                "has_llm_safety_callback": callable(llm_safety_options),
            }
        )
        return 37

    monkeypatch.setattr(cli_module, "handle_build_context_packet_command", fake_handler)

    exit_code = cli_module.main(
        [
            "build-context-packet",
            "--session-id",
            "session-1",
            "--packet-id",
            "packet-1",
            "--task-title",
            "Task",
            "--macro-context",
            "Context",
            "--unit-title",
            "Unit",
            "--goal",
            "Goal",
            "--project-root",
            str(project_root),
        ]
    )

    assert exit_code == 37
    assert calls == [
        {
            "command": "build-context-packet",
            "packet_id": "packet-1",
            "project_root": project_root.resolve(),
            "has_build_callback": True,
            "has_v2_callback": True,
            "has_routing_callback": True,
            "has_llm_safety_callback": True,
        }
    ]


def test_cli_build_context_packet_validates_summary_mode_before_export(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "build-context-packet",
                "--session-id",
                "session-1",
                "--packet-id",
                "packet-1",
                "--task-title",
                "Task",
                "--macro-context",
                "Context",
                "--unit-title",
                "Unit",
                "--goal",
                "Goal",
                "--summary-mode",
                "custom-command",
                "--project-root",
                str(project_root),
            ]
        )

    assert exc_info.value.code == 2
    assert not (project_root / "data").exists()


def test_cli_extract_session_exports_bundle_and_prints_path(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    exit_code = main(
        [
            "extract-session",
            "--session-id",
            "session-1",
            "--project-root",
            str(project_root),
        ]
    )

    captured = capsys.readouterr()
    export_path = project_root / "data" / "exports" / "session-1.json"

    assert exit_code == 0
    assert str(export_path) in captured.out
    assert export_path.exists()


def test_cli_build_topic_map_exports_json_and_markdown(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))
    _write(wiki_root / "concepts" / "summarization.md", "# Summarization\n\nSee [[agent-context-substrate]].\n")
    _write(wiki_root / "concepts" / "agent-context-substrate.md", "# Agent Context Substrate\n")
    _write(
        project_root / "data" / "atoms" / "claims.jsonl",
        json.dumps(
            {
                "atom_id": "packet-1-claim-1",
                "text": "Hybrid summarizer keeps heuristic evidence spine.",
                "type": "design_claim",
                "subjects": ["summarization"],
                "source_refs": ["packet:packet-1#packet-1-micro-1"],
                "confidence": 0.8,
                "status": "active",
                "first_seen": "2026-05-07T00:00:00+00:00",
                "last_seen": "2026-05-07T00:00:00+00:00",
                "supports": [],
                "contradicts": [],
                "supersedes": [],
            },
            ensure_ascii=False,
        )
        + "\n",
    )

    exit_code = main(["build-topic-map", "--project-root", str(project_root)])

    captured = capsys.readouterr()
    json_path = project_root / "data" / "index" / "topic_map.json"
    md_path = project_root / "data" / "index" / "topic_map.md"

    assert exit_code == 0
    assert str(json_path) in captured.out
    assert str(md_path) in captured.out
    assert "nodes=" in captured.out
    assert "edges=" in captured.out
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "topic_map_v1"
    assert any(node["node_id"] == "claim:packet-1-claim-1" for node in payload["nodes"])
    assert "# Topic Map" in md_path.read_text(encoding="utf-8")


def test_cli_extract_atoms_writes_all_atom_files(tmp_path, monkeypatch, capsys) -> None:
    from dataclasses import replace

    from agent_context_substrate.models import EvidenceBackedText
    from agent_context_substrate.summarizer import build_micro_summary_v2

    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))
    raw_bundle = {
        "session": {"id": "session-atoms", "source": "telegram", "title": "Atoms"},
        "messages": [
            {"id": 1, "role": "user", "content": "Decide packet-only and mention Hermes Agent."},
            {"id": 2, "role": "assistant", "content": "Done.\n- Claims cite evidence"},
        ],
    }
    micro = replace(
        build_micro_summary_v2(raw_bundle=raw_bundle, micro_id="packet-1-micro-1"),
        decisions=[EvidenceBackedText("Keep packet-only default", [1], 0.8)],
        entities=["Hermes Agent"],
        concepts=["packet-only"],
        open_questions=["Should semantic lint detect stale claims?"],
    )
    summary_dir = project_root / "data" / "exports" / "summaries"
    summary_dir.mkdir(parents=True)
    (summary_dir / "packet-1-micro-v2.json").write_text(json.dumps(micro.to_dict()), encoding="utf-8")

    exit_code = main(["extract-atoms", "--packet-id", "packet-1", "--project-root", str(project_root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    for filename in ["claims.jsonl", "decisions.jsonl", "entities.jsonl", "concepts.jsonl", "questions.jsonl"]:
        atom_path = project_root / "data" / "atoms" / filename
        assert atom_path.exists()
        assert str(atom_path) in captured.out
    assert "packet-1-decision-1" in (project_root / "data" / "atoms" / "decisions.jsonl").read_text(encoding="utf-8")
    assert "packet-1-entity-1" in (project_root / "data" / "atoms" / "entities.jsonl").read_text(encoding="utf-8")
    assert "packet-1-concept-1" in (project_root / "data" / "atoms" / "concepts.jsonl").read_text(encoding="utf-8")
    assert "packet-1-question-1" in (project_root / "data" / "atoms" / "questions.jsonl").read_text(encoding="utf-8")


def test_cli_lint_promotions_includes_atom_semantic_checks(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))
    _write(
        project_root / "data" / "atoms" / "claims.jsonl",
        json.dumps({"atom_id": "claim-1", "text": "No source", "source_refs": []}) + "\n",
    )
    _write(
        project_root / "data" / "atoms" / "concepts.jsonl",
        json.dumps({"atom_id": "concept-1", "name": "Packet Only", "status": "active"}) + "\n"
        + json.dumps({"atom_id": "concept-2", "name": "packet only", "status": "active"}) + "\n",
    )

    exit_code = main(["lint-promotions", "--project-root", str(project_root), "--report-id", "atom-lint"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "claim_without_source" in captured.out
    assert "duplicate_concept" in captured.out
    payload = json.loads((project_root / "data" / "lint" / "atom-lint.json").read_text(encoding="utf-8"))
    assert {issue["code"] for issue in payload["issues"]} == {"claim_without_source", "duplicate_concept"}


def test_cli_lint_wiki_exports_report_and_prints_summary(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    _write(wiki_root / "SCHEMA.md", "# Wiki Schema\n\n## Tag Taxonomy\n- question\n")
    _write(wiki_root / "index.md", "# Wiki Index\n\n## Queries\n<!-- empty -->\n")
    _write(wiki_root / "log.md", "# Wiki Log\n")
    _write(
        wiki_root / "queries" / "page.md",
        """---
title: Page
created: 2026-04-22
updated: 2026-04-22
type: query
tags: [question]
sources: [\"hermes-session:session-1#messages=1\"]
---

# Page

## Provenance
- `hermes-session:session-1#messages=1`
""",
    )

    exit_code = main(
        [
            "lint-wiki",
            "--project-root",
            str(project_root),
            "--report-id",
            "cli-lint",
        ]
    )

    captured = capsys.readouterr()
    json_path = project_root / "data" / "exports" / "lint" / "cli-lint.json"
    md_path = project_root / "data" / "exports" / "lint" / "cli-lint.md"

    assert exit_code == 0
    assert str(json_path) in captured.out
    assert str(md_path) in captured.out
    assert "checked_pages=1" in captured.out
    assert "orphan_pages=1" in captured.out
    assert json_path.exists()
    assert md_path.exists()


def test_cli_lint_wiki_include_promotions_exports_semantic_lint_report(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    _write(wiki_root / "SCHEMA.md", "# Wiki Schema\n\n## Tag Taxonomy\n- question\n")
    _write(wiki_root / "index.md", "# Wiki Index\n\n## Queries\n<!-- empty -->\n")
    _write(wiki_root / "log.md", "# Wiki Log\n")
    _write(
        wiki_root / "queries" / "page.md",
        """---
title: Page
created: 2026-04-22
updated: 2026-04-22
type: query
tags: [question]
sources: [\"hermes-session:session-1#messages=1\"]
---

# Page

## Provenance
- `hermes-session:session-1#messages=1`
""",
    )
    _write(
        project_root / "data" / "promotions" / "packet-1.json",
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "",
                    "reason": "Missing target.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "Untriaged change.",
                    "proposed_action": "review_required",
                    "confidence": 0.4,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
    )

    exit_code = main([
        "lint-wiki",
        "--include-promotions",
        "--project-root",
        str(project_root),
        "--report-id",
        "combined-lint",
    ])

    captured = capsys.readouterr()
    wiki_json_path = project_root / "data" / "exports" / "lint" / "combined-lint.json"
    promotion_json_path = project_root / "data" / "lint" / "promotions-lint.json"
    promotion_md_path = project_root / "data" / "lint" / "promotions-lint.md"

    assert exit_code == 0
    assert str(wiki_json_path) in captured.out
    assert str(promotion_json_path) in captured.out
    assert str(promotion_md_path) in captured.out
    assert "semantic_lint ok=False issues=1" in captured.out
    assert "promotion_issues=1" in captured.out
    assert promotion_json_path.exists()
    assert promotion_md_path.exists()


def test_cli_lint_wiki_include_atoms_exports_atom_semantic_issues(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    _write(wiki_root / "SCHEMA.md", "# Wiki Schema\n\n## Tag Taxonomy\n- question\n")
    _write(wiki_root / "index.md", "# Wiki Index\n\n## Queries\n<!-- empty -->\n")
    _write(wiki_root / "log.md", "# Wiki Log\n")
    _write(
        project_root / "data" / "atoms" / "claims.jsonl",
        json.dumps({"atom_id": "claim-1", "text": "No source", "source_refs": []}) + "\n",
    )
    _write(
        project_root / "data" / "atoms" / "concepts.jsonl",
        json.dumps({"atom_id": "concept-1", "name": "Packet Only", "status": "active"}) + "\n"
        + json.dumps({"atom_id": "concept-2", "name": "packet only", "status": "active"}) + "\n",
    )

    exit_code = main([
        "lint-wiki",
        "--include-atoms",
        "--project-root",
        str(project_root),
        "--report-id",
        "atom-combined-lint",
    ])

    captured = capsys.readouterr()
    semantic_json_path = project_root / "data" / "lint" / "promotions-lint.json"

    assert exit_code == 0
    assert "semantic_lint ok=False issues=2" in captured.out
    assert "claim_without_source" in captured.out
    assert "duplicate_concept" in captured.out
    assert "semantic_issues=2" in captured.out
    payload = json.loads(semantic_json_path.read_text(encoding="utf-8"))
    assert {issue["code"] for issue in payload["issues"]} == {"claim_without_source", "duplicate_concept"}


def test_cli_lint_wiki_semantic_defaults_to_promotions_and_atoms(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    _write(wiki_root / "SCHEMA.md", "# Wiki Schema\n\n## Tag Taxonomy\n- question\n")
    _write(wiki_root / "index.md", "# Wiki Index\n\n## Queries\n<!-- empty -->\n")
    _write(wiki_root / "log.md", "# Wiki Log\n")
    _write(
        project_root / "data" / "promotions" / "packet-1.json",
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "",
                    "reason": "Missing target.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "Untriaged change.",
                    "proposed_action": "review_required",
                    "confidence": 0.4,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
    )
    _write(
        project_root / "data" / "atoms" / "claims.jsonl",
        json.dumps({"atom_id": "claim-1", "text": "No source", "source_refs": []}) + "\n",
    )

    exit_code = main([
        "lint-wiki",
        "--semantic",
        "--project-root",
        str(project_root),
        "--report-id",
        "semantic-combined-lint",
    ])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "semantic_lint ok=False issues=2" in captured.out
    assert "promotion_missing_target_page" in captured.out
    assert "claim_without_source" in captured.out
    assert "semantic_issues=2" in captured.out


def test_cli_build_context_packet_exports_raw_and_packet_artifacts(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    exit_code = main(
        [
            "build-context-packet",
            "--session-id",
            "session-1",
            "--packet-id",
            "packet-1",
            "--task-title",
            "Resume harness work",
            "--macro-context",
            "Need a durable packet for future session recovery.",
            "--unit-title",
            "Bootstrap project scaffold",
            "--goal",
            "Create the first usable harness substrate.",
            "--related-page",
            "architectures/agent-context-substrate.md",
            "--project-root",
            str(project_root),
        ]
    )

    captured = capsys.readouterr()
    raw_export_path = project_root / "data" / "exports" / "session-1.json"
    packet_json_path = project_root / "data" / "exports" / "context_packets" / "packet-1.json"
    packet_md_path = project_root / "data" / "exports" / "context_packets" / "packet-1.md"

    assert exit_code == 0
    assert str(raw_export_path) in captured.out
    assert str(packet_json_path) in captured.out
    assert str(packet_md_path) in captured.out
    assert raw_export_path.exists()
    assert packet_json_path.exists()
    assert packet_md_path.exists()

    payload = json.loads(packet_json_path.read_text(encoding="utf-8"))
    assert payload["packet_id"] == "packet-1"
    assert payload["task_title"] == "Resume harness work"
    assert payload["unit_summaries"][0]["title"] == "Bootstrap project scaffold"
    assert payload["micro_summaries"][0]["session_id"] == "session-1"
    assert "pyproject.toml" in payload["critical_files"]


def test_cli_build_context_packet_summary_mode_exports_v2_summary_artifacts(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    exit_code = main(
        [
            "build-context-packet",
            "--session-id",
            "session-1",
            "--packet-id",
            "packet-1",
            "--task-title",
            "Resume harness work",
            "--macro-context",
            "Need a durable packet for future session recovery.",
            "--unit-title",
            "Bootstrap project scaffold",
            "--goal",
            "Create the first usable harness substrate.",
            "--summary-mode",
            "heuristic",
            "--project-root",
            str(project_root),
        ]
    )

    captured = capsys.readouterr()
    micro_v2_path = project_root / "data" / "exports" / "summaries" / "packet-1-micro-v2.json"
    unit_v2_path = project_root / "data" / "exports" / "summaries" / "packet-1-unit-v2.json"
    evidence_path = project_root / "data" / "exports" / "evidence" / "session-1" / "packet-1-micro-1.json"

    assert exit_code == 0
    assert str(micro_v2_path) in captured.out
    assert str(unit_v2_path) in captured.out
    assert str(evidence_path) in captured.out
    assert micro_v2_path.exists()
    assert unit_v2_path.exists()
    assert evidence_path.exists()

    micro_payload = json.loads(micro_v2_path.read_text(encoding="utf-8"))
    unit_payload = json.loads(unit_v2_path.read_text(encoding="utf-8"))
    evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert micro_payload["metadata"]["mode"] == "heuristic"
    assert micro_payload["metadata"]["schema_version"] == "micro_summary_v2"
    assert unit_payload["metadata"]["schema_version"] == "unit_summary_v2"
    assert evidence_payload["session_id"] == "session-1"
    assert evidence_payload["micro_id"] == "packet-1-micro-1"


def test_cli_build_context_packet_summary_cache_reuses_cached_custom_command_result(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")
    counter_path = tmp_path / "counter.txt"
    script_path = tmp_path / "custom_summarizer.py"
    _write(
        script_path,
        f'''
import json
from pathlib import Path
import sys
counter = Path({str(counter_path)!r})
count = int(counter.read_text() or "0") if counter.exists() else 0
counter.write_text(str(count + 1))
payload = json.loads(sys.stdin.read())
if payload["kind"] == "micro":
    message_ids = payload["message_ids"]
    print(json.dumps({{
        "micro_id": payload["micro_id"],
        "session_id": payload["session_id"],
        "message_ids": message_ids,
        "recovery_summary": "cached custom recovery",
        "knowledge_summary": "cached custom knowledge",
        "retrieval_summary": "cached custom retrieval pyproject.toml",
        "user_intent": "cached custom intent",
        "assistant_outcome": "cached custom outcome",
        "decisions": [{{"text": "cached custom decision", "evidence_message_ids": message_ids, "confidence": 0.9}}],
        "claims": [],
        "action_items": [],
        "open_questions": [],
        "files": ["pyproject.toml"],
        "entities": [],
        "concepts": [],
        "metadata": {{
            "mode": "custom-command",
            "schema_version": "micro_summary_v2",
            "prompt_version": None,
            "model": None,
            "input_hash": "sha256:custom-cache",
            "created_at": "2026-05-07T00:00:00+00:00",
            "confidence": 0.9
        }},
        "provenance": None,
    }}, ensure_ascii=False))
else:
    micro = payload["micro_summaries"][0]
    print(json.dumps({{
        "unit_id": payload["unit_id"],
        "session_id": payload["session_id"],
        "title": payload["title"],
        "goal": payload["goal"],
        "state": "completed",
        "decisions": micro["decisions"],
        "progress": ["cached custom outcome"],
        "next_actions": [],
        "open_questions": [],
        "risk_notes": [],
        "wiki_candidates": [],
        "micro_ids": [micro["micro_id"]],
        "related_pages": [],
        "metadata": {{
            "mode": "custom-command",
            "schema_version": "unit_summary_v2",
            "prompt_version": None,
            "model": None,
            "input_hash": "sha256:custom-cache-unit",
            "created_at": "2026-05-07T00:00:00+00:00",
            "confidence": 0.9
        }},
        "provenance": None,
    }}, ensure_ascii=False))
'''.strip(),
    )

    args = [
        "build-context-packet",
        "--session-id", "session-1",
        "--packet-id", "packet-cache",
        "--task-title", "Resume harness work",
        "--macro-context", "Need a durable packet for future session recovery.",
        "--unit-title", "Bootstrap project scaffold",
        "--goal", "Create the first usable harness substrate.",
        "--summary-mode", "custom-command",
        "--summarizer-command", f"{sys.executable} {script_path}",
        "--summary-cache", "on",
        "--project-root", str(project_root),
    ]

    assert main(args) == 0
    capsys.readouterr()
    assert counter_path.read_text() == "2"
    assert list((project_root / "data" / "cache" / "summaries").glob("*.json"))

    assert main(args) == 0
    captured = capsys.readouterr()

    assert counter_path.read_text() == "2"
    assert "packet-cache-micro-v2.json" in captured.out
    micro_payload = json.loads((project_root / "data" / "exports" / "summaries" / "packet-cache-micro-v2.json").read_text(encoding="utf-8"))
    assert micro_payload["recovery_summary"] == "cached custom recovery"


def test_cli_build_context_packet_summary_routing_hints_are_stored_in_cache_input(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    exit_code = main(
        [
            "build-context-packet",
            "--session-id", "session-1",
            "--packet-id", "packet-routing-hints",
            "--task-title", "Resume harness work",
            "--macro-context", "Need a durable packet for future session recovery.",
            "--unit-title", "Bootstrap project scaffold",
            "--goal", "Create the first usable harness substrate.",
            "--summary-mode", "heuristic",
            "--summary-cache", "on",
            "--summary-model", "claude-sonnet-4",
            "--summary-budget", "cheap",
            "--project-root", str(project_root),
        ]
    )

    capsys.readouterr()
    cache_files = list((project_root / "data" / "cache" / "summaries").glob("*.json"))

    assert exit_code == 0
    assert len(cache_files) == 1
    payload = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert payload["cache_input"]["routing_hints"] == {
        "model": "claude-sonnet-4",
        "budget": "cheap",
    }


def test_cli_build_context_packet_agent_llm_mode_requires_host_agent_router(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    try:
        main(
            [
                "build-context-packet",
                "--session-id",
                "session-1",
                "--packet-id",
                "packet-agent-llm",
                "--task-title",
                "Resume harness work",
                "--macro-context",
                "Need a durable packet for future session recovery.",
                "--unit-title",
                "Bootstrap project scaffold",
                "--goal",
                "Create the first usable harness substrate.",
                "--summary-mode",
                "agent-llm",
                "--project-root",
                str(project_root),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("standalone CLI should require an injected Agent LLM router")

    captured = capsys.readouterr()
    assert "requires host Agent integration with an injected Agent LLM router" in captured.err


def test_cli_extract_atoms_writes_claims_jsonl_from_v2_summary(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    assert main(
        [
            "build-context-packet",
            "--session-id",
            "session-1",
            "--packet-id",
            "packet-1",
            "--task-title",
            "Resume harness work",
            "--macro-context",
            "Need a durable packet for future session recovery.",
            "--unit-title",
            "Bootstrap project scaffold",
            "--goal",
            "Create the first usable harness substrate.",
            "--summary-mode",
            "heuristic",
            "--project-root",
            str(project_root),
        ]
    ) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "extract-atoms",
            "--packet-id",
            "packet-1",
            "--project-root",
            str(project_root),
        ]
    )

    captured = capsys.readouterr()
    claims_path = project_root / "data" / "atoms" / "claims.jsonl"

    assert exit_code == 0
    assert str(claims_path) in captured.out
    assert claims_path.exists()
    claim_lines = [json.loads(line) for line in claims_path.read_text(encoding="utf-8").splitlines()]
    assert claim_lines
    assert claim_lines[0]["atom_id"].startswith("packet-1-claim-")
    assert claim_lines[0]["source_refs"][0] == "packet:packet-1#packet-1-micro-1"


def test_cli_propose_promotions_writes_json_and_markdown_from_claim_atoms(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "wiki"))

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    assert main(
        [
            "build-context-packet",
            "--session-id",
            "session-1",
            "--packet-id",
            "packet-1",
            "--task-title",
            "Resume harness work",
            "--macro-context",
            "Need a durable packet for future session recovery.",
            "--unit-title",
            "Bootstrap project scaffold",
            "--goal",
            "Create the first usable harness substrate.",
            "--summary-mode",
            "heuristic",
            "--project-root",
            str(project_root),
        ]
    ) == 0
    capsys.readouterr()
    assert main(["extract-atoms", "--packet-id", "packet-1", "--project-root", str(project_root)]) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "propose-promotions",
            "--packet-id",
            "packet-1",
            "--project-root",
            str(project_root),
        ]
    )

    captured = capsys.readouterr()
    promotion_json_path = project_root / "data" / "promotions" / "packet-1.json"
    promotion_md_path = project_root / "data" / "promotions" / "packet-1.md"

    assert exit_code == 0
    assert str(promotion_json_path) in captured.out
    assert str(promotion_md_path) in captured.out
    assert promotion_json_path.exists()
    assert promotion_md_path.exists()

    candidates = json.loads(promotion_json_path.read_text(encoding="utf-8"))
    assert candidates
    assert candidates[0]["candidate_id"].startswith("packet-1-candidate-")
    assert candidates[0]["status"] == "pending"
    assert "# Promotion Candidates: packet-1" in promotion_md_path.read_text(encoding="utf-8")


def test_cli_plan_wiki_patches_writes_json_and_markdown_from_promotion_file(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    _write(wiki_root / "concepts" / "summarization.md", "# Summarization\n\nExisting human prose.\n")
    promotion_file = project_root / "data" / "promotions" / "packet-1.json"
    _write(
        promotion_file,
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "summarization",
                    "reason": "Claim atom packet-1-claim-1 may update durable wiki knowledge.",
                    "evidence": ["claim:packet-1-claim-1", "packet:packet-1#micro-1"],
                    "proposed_change": "Heuristic summarizer should remain the default for privacy.",
                    "proposed_action": "update_existing",
                    "confidence": 0.75,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
    )

    exit_code = main(
        [
            "plan-wiki-patches",
            "--promotion-file",
            str(promotion_file),
            "--project-root",
            str(project_root),
            "--wiki-root",
            str(wiki_root),
        ]
    )

    captured = capsys.readouterr()
    patch_json_path = project_root / "data" / "wiki_patches" / "packet-1.json"
    patch_md_path = project_root / "data" / "wiki_patches" / "packet-1.md"

    assert exit_code == 0
    assert str(patch_json_path) in captured.out
    assert str(patch_md_path) in captured.out
    assert patch_json_path.exists()
    assert patch_md_path.exists()

    proposal = json.loads(patch_json_path.read_text(encoding="utf-8"))
    assert proposal["proposal_id"] == "packet-1-wiki-patch-proposal"
    assert proposal["operations"][0]["target"] == "concepts/summarization.md"
    assert proposal["operations"][0]["operation"] == "insert_claim_block"
    assert "# Wiki Patch Proposal: packet-1" in patch_md_path.read_text(encoding="utf-8")


def test_cli_plan_wiki_patches_can_emit_flexible_page_revisions(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))
    _write(wiki_root / "summarization.md", "# Summarization\n\nExisting prose.\n")
    promotion_file = project_root / "data" / "promotions" / "packet-1.json"
    _write(
        promotion_file,
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "summarization",
                    "reason": "Flexible maintainer revision.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "LLM wiki writes should use rubric-guided prose.",
                    "proposed_action": "update_existing",
                    "confidence": 0.8,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
    )

    exit_code = main(
        [
            "plan-wiki-patches",
            "--promotion-file",
            str(promotion_file),
            "--write-mode",
            "flexible",
            "--project-root",
            str(project_root),
            "--wiki-root",
            str(wiki_root),
        ]
    )

    captured = capsys.readouterr()
    patch_json_path = project_root / "data" / "wiki_patches" / "packet-1.json"
    proposal = json.loads(patch_json_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert str(patch_json_path) in captured.out
    assert proposal["metadata"]["write_mode"] == "flexible"
    assert proposal["metadata"]["judge_verdict"] == "not_requested"
    assert proposal["operations"][0]["target"] == "summarization.md"
    assert proposal["operations"][0]["operation"] == "replace_page"
    assert proposal["operations"][0]["diff"]["base_sha256"]
    assert "rubric-guided prose" in proposal["operations"][0]["diff"]["after"]


def test_cli_list_promotions_prints_queue_summary(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(
        project_root / "data" / "promotions" / "packet-1.json",
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "summarization",
                    "reason": "Keep heuristic default.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "Heuristic summarizer should remain default.",
                    "proposed_action": "update_existing",
                    "confidence": 0.75,
                    "status": "pending",
                },
                {
                    "candidate_id": "packet-1-candidate-2",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "wiki-patches",
                    "reason": "Applied patch exists.",
                    "evidence": ["claim:packet-1-claim-2"],
                    "proposed_change": "Wiki patch writes are managed block updates.",
                    "proposed_action": "update_existing",
                    "confidence": 0.8,
                    "status": "applied",
                },
            ],
            ensure_ascii=False,
        ),
    )

    exit_code = main(["list-promotions", "--project-root", str(project_root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "promotions total=2 pending=1 applied=1" in captured.out
    assert "packet-1-candidate-1" in captured.out
    assert "pending" in captured.out
    assert "summarization" in captured.out
    assert "packet-1-candidate-2" in captured.out
    assert "applied" in captured.out


def test_cli_list_promotions_can_filter_status(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(
        project_root / "data" / "promotions" / "packet-1.json",
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "summarization",
                    "reason": "Pending candidate.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "Pending change.",
                    "proposed_action": "update_existing",
                    "confidence": 0.75,
                    "status": "pending",
                },
                {
                    "candidate_id": "packet-1-candidate-2",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "wiki-patches",
                    "reason": "Applied candidate.",
                    "evidence": ["claim:packet-1-claim-2"],
                    "proposed_change": "Applied change.",
                    "proposed_action": "update_existing",
                    "confidence": 0.8,
                    "status": "applied",
                },
            ],
            ensure_ascii=False,
        ),
    )

    exit_code = main(["list-promotions", "--status", "pending", "--project-root", str(project_root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "promotions total=1 pending=1" in captured.out
    assert "packet-1-candidate-1" in captured.out
    assert "packet-1-candidate-2" not in captured.out


def test_cli_review_promotion_accepts_action_and_prints_evidence_preview(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    promotion_path = project_root / "data" / "promotions" / "packet-1.json"
    _write(
        promotion_path,
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "summarization",
                    "reason": "Keep heuristic default.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "Heuristic summarizer should remain default.",
                    "proposed_action": "update_existing",
                    "confidence": 0.75,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
    )

    exit_code = main(
        [
            "review-promotion",
            "--candidate-id",
            "packet-1-candidate-1",
            "--action",
            "accept",
            "--reviewer",
            "reviewer-1",
            "--note",
            "ship it",
            "--preview-evidence",
            "--project-root",
            str(project_root),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(promotion_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload[0]["status"] == "accepted"
    assert payload[0]["reviewer"] == "reviewer-1"
    assert "promotion packet-1-candidate-1 packet=packet-1 status=pending kind=concept_update" in captured.out
    assert "evidence:" in captured.out
    assert "updated packet-1-candidate-1 status=accepted" in captured.out


def test_cli_review_promotion_preview_evidence_is_read_only(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    promotion_path = project_root / "data" / "promotions" / "packet-1.json"
    _write(
        promotion_path,
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "summarization",
                    "reason": "Review before promoting.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "Add review-first queue UX.",
                    "proposed_action": "update_existing",
                    "confidence": 0.75,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
    )

    exit_code = main(
        [
            "review-promotion",
            "--candidate-id",
            "packet-1-candidate-1",
            "--preview-evidence",
            "--project-root",
            str(project_root),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(promotion_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload[0]["status"] == "pending"
    assert "proposed_change: Add review-first queue UX." in captured.out
    assert "updated packet-1-candidate-1" not in captured.out


def test_cli_review_promotion_supports_reject_supersede_and_apply_actions(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    promotion_path = project_root / "data" / "promotions" / "packet-1.json"
    base_candidate = {
        "candidate_id": "packet-1-candidate-1",
        "packet_id": "packet-1",
        "kind": "concept_update",
        "target_page": "summarization",
        "reason": "Review status transitions.",
        "evidence": ["claim:packet-1-claim-1"],
        "proposed_change": "Transition status.",
        "proposed_action": "update_existing",
        "confidence": 0.75,
        "status": "pending",
    }
    _write(promotion_path, json.dumps([base_candidate], ensure_ascii=False))

    for action, expected_status in [("reject", "rejected"), ("supersede", "superseded"), ("apply", "applied")]:
        exit_code = main(
            [
                "review-promotion",
                "--candidate-id",
                "packet-1-candidate-1",
                "--action",
                action,
                "--project-root",
                str(project_root),
            ]
        )
        captured = capsys.readouterr()
        payload = json.loads(promotion_path.read_text(encoding="utf-8"))
        assert exit_code == 0
        assert payload[0]["status"] == expected_status
        assert f"updated packet-1-candidate-1 status={expected_status}" in captured.out


def test_cli_review_promotion_updates_multiple_candidate_ids(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    promotion_path = project_root / "data" / "promotions" / "packet-1.json"
    _write(
        promotion_path,
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "summarization",
                    "reason": "Batch review candidate 1.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "First batch change.",
                    "proposed_action": "update_existing",
                    "confidence": 0.75,
                    "status": "pending",
                },
                {
                    "candidate_id": "packet-1-candidate-2",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "wiki-patches",
                    "reason": "Batch review candidate 2.",
                    "evidence": ["claim:packet-1-claim-2"],
                    "proposed_change": "Second batch change.",
                    "proposed_action": "update_existing",
                    "confidence": 0.8,
                    "status": "pending",
                },
            ],
            ensure_ascii=False,
        ),
    )

    exit_code = main(
        [
            "review-promotion",
            "--candidate-id",
            "packet-1-candidate-1",
            "--candidate-id",
            "packet-1-candidate-2",
            "--action",
            "reject",
            "--reviewer",
            "reviewer-1",
            "--note",
            "batch reject",
            "--project-root",
            str(project_root),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(promotion_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert [item["status"] for item in payload] == ["rejected", "rejected"]
    assert [item["reviewer"] for item in payload] == ["reviewer-1", "reviewer-1"]
    assert "updated packet-1-candidate-1 status=rejected" in captured.out
    assert "updated packet-1-candidate-2 status=rejected" in captured.out


def test_cli_list_wiki_patches_prints_proposal_summary(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(
        project_root / "data" / "wiki_patches" / "packet-1.json",
        json.dumps(
            {
                "proposal_id": "packet-1-wiki-patch-proposal",
                "packet_id": "packet-1",
                "status": "proposed",
                "operations": [
                    {
                        "patch_id": "packet-1-patch-1",
                        "candidate_id": "packet-1-candidate-1",
                        "target": "concepts/summarization.md",
                        "operation": "insert_claim_block",
                        "rationale": "Add generated claim block.",
                        "evidence": ["claim:packet-1-claim-1"],
                        "risk": "low",
                        "diff": {"before": "", "after": "managed block"},
                        "status": "proposed",
                    }
                ],
            },
            ensure_ascii=False,
        ),
    )
    _write(
        project_root / "data" / "wiki_patches" / "applied.jsonl",
        json.dumps(
            {
                "created_at": "2026-05-07T00:00:00+00:00",
                "proposal_id": "packet-0-wiki-patch-proposal",
                "packet_id": "packet-0",
                "patch_id": "packet-0-patch-1",
                "candidate_id": "packet-0-candidate-1",
                "target": "concepts/context-packet.md",
                "operation": "insert_claim_block",
            },
            ensure_ascii=False,
        )
        + "\n",
    )

    exit_code = main(["list-wiki-patches", "--project-root", str(project_root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "wiki_patches proposals=1 operations=1 applied=1" in captured.out
    assert "packet-1-patch-1" in captured.out
    assert "proposed" in captured.out
    assert "concepts/summarization.md" in captured.out
    assert "packet-0-patch-1" in captured.out
    assert "applied" in captured.out


def test_cli_list_wiki_patches_can_filter_status(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(
        project_root / "data" / "wiki_patches" / "packet-1.json",
        json.dumps(
            {
                "proposal_id": "packet-1-wiki-patch-proposal",
                "packet_id": "packet-1",
                "status": "proposed",
                "operations": [
                    {
                        "patch_id": "packet-1-patch-1",
                        "candidate_id": "packet-1-candidate-1",
                        "target": "concepts/summarization.md",
                        "operation": "insert_claim_block",
                        "rationale": "Add generated claim block.",
                        "evidence": ["claim:packet-1-claim-1"],
                        "risk": "low",
                        "diff": {"before": "", "after": "managed block"},
                        "status": "proposed",
                    }
                ],
            },
            ensure_ascii=False,
        ),
    )
    _write(
        project_root / "data" / "wiki_patches" / "applied.jsonl",
        json.dumps(
            {
                "created_at": "2026-05-07T00:00:00+00:00",
                "proposal_id": "packet-0-wiki-patch-proposal",
                "packet_id": "packet-0",
                "patch_id": "packet-0-patch-1",
                "candidate_id": "packet-0-candidate-1",
                "target": "concepts/context-packet.md",
                "operation": "insert_claim_block",
            },
            ensure_ascii=False,
        )
        + "\n",
    )

    exit_code = main(["list-wiki-patches", "--status", "applied", "--project-root", str(project_root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "wiki_patches proposals=1 operations=1 applied=1" in captured.out
    assert "packet-0-patch-1" in captured.out
    assert "packet-1-patch-1" not in captured.out


def test_cli_lint_promotions_reports_semantic_issues(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(
        project_root / "data" / "promotions" / "packet-1.json",
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "",
                    "reason": "Missing evidence and target.",
                    "evidence": [],
                    "proposed_change": "Untriaged change.",
                    "proposed_action": "review_required",
                    "confidence": 0.4,
                    "status": "pending",
                },
                {
                    "candidate_id": "packet-1-candidate-2",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "summarization",
                    "reason": "Marked applied without log.",
                    "evidence": ["claim:packet-1-claim-2"],
                    "proposed_change": "Applied but not logged.",
                    "proposed_action": "update_existing",
                    "confidence": 0.8,
                    "status": "applied",
                },
            ],
            ensure_ascii=False,
        ),
    )

    exit_code = main(["lint-promotions", "--project-root", str(project_root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "semantic_lint ok=False issues=3" in captured.out
    json_path = project_root / "data" / "lint" / "promotions-lint.json"
    md_path = project_root / "data" / "lint" / "promotions-lint.md"

    assert "promotion_missing_evidence" in captured.out
    assert "promotion_missing_target_page" in captured.out
    assert "applied_promotion_without_applied_patch" in captured.out
    assert str(json_path) in captured.out
    assert str(md_path) in captured.out
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert len(payload["issues"]) == 3
    assert "semantic_lint ok=False issues=3" in md_path.read_text(encoding="utf-8")


def test_cli_lint_promotions_report_id_changes_export_filenames(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(
        project_root / "data" / "promotions" / "packet-1.json",
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "",
                    "reason": "Missing target.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "Untriaged change.",
                    "proposed_action": "review_required",
                    "confidence": 0.4,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
    )

    exit_code = main([
        "lint-promotions",
        "--report-id",
        "nightly-promotions",
        "--project-root",
        str(project_root),
    ])

    captured = capsys.readouterr()
    json_path = project_root / "data" / "lint" / "nightly-promotions.json"
    md_path = project_root / "data" / "lint" / "nightly-promotions.md"

    assert exit_code == 0
    assert str(json_path) in captured.out
    assert str(md_path) in captured.out
    assert json_path.exists()
    assert md_path.exists()
    assert not (project_root / "data" / "lint" / "promotions-lint.json").exists()


def test_cli_lint_promotions_fail_on_issues_returns_nonzero(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(
        project_root / "data" / "promotions" / "packet-1.json",
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "",
                    "reason": "Missing target.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "Untriaged change.",
                    "proposed_action": "review_required",
                    "confidence": 0.4,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
    )

    exit_code = main(["lint-promotions", "--project-root", str(project_root), "--fail-on-issues"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "promotion_missing_target_page" in captured.out


def test_cli_apply_wiki_patch_defaults_to_dry_run(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    target = wiki_root / "concepts" / "summarization.md"
    original = "# Summarization\n\nHuman text.\n"
    _write(target, original)
    patch_file = project_root / "data" / "wiki_patches" / "packet-1.json"
    _write(
        patch_file,
        json.dumps(
            {
                "proposal_id": "packet-1-wiki-patch-proposal",
                "packet_id": "packet-1",
                "status": "proposed",
                "operations": [
                    {
                        "patch_id": "packet-1-patch-1",
                        "candidate_id": "packet-1-candidate-1",
                        "target": "concepts/summarization.md",
                        "operation": "insert_claim_block",
                        "rationale": "Add generated claim block.",
                        "evidence": ["claim:packet-1-claim-1"],
                        "risk": "low",
                        "diff": {
                            "before": "",
                            "after": "<!-- acs:auto:claims:start -->\n- New generated claim. `claim:packet-1-claim-1`\n<!-- acs:auto:claims:end -->",
                        },
                        "status": "proposed",
                    }
                ],
            },
            ensure_ascii=False,
        ),
    )

    exit_code = main(
        [
            "apply-wiki-patch",
            "--patch-file",
            str(patch_file),
            "--project-root",
            str(project_root),
            "--wiki-root",
            str(wiki_root),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "dry_run=True" in captured.out
    assert "planned=1" in captured.out
    assert "applied=0" in captured.out
    assert target.read_text(encoding="utf-8") == original


def test_cli_apply_wiki_patch_with_apply_updates_managed_block(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    target = wiki_root / "concepts" / "summarization.md"
    _write(target, "# Summarization\n\nHuman text.\n")
    patch_file = project_root / "data" / "wiki_patches" / "packet-1.json"
    _write(
        patch_file,
        json.dumps(
            {
                "proposal_id": "packet-1-wiki-patch-proposal",
                "packet_id": "packet-1",
                "status": "proposed",
                "operations": [
                    {
                        "patch_id": "packet-1-patch-1",
                        "candidate_id": "packet-1-candidate-1",
                        "target": "concepts/summarization.md",
                        "operation": "insert_claim_block",
                        "rationale": "Add generated claim block.",
                        "evidence": ["claim:packet-1-claim-1"],
                        "risk": "low",
                        "diff": {
                            "before": "",
                            "after": "<!-- acs:auto:claims:start -->\n- New generated claim. `claim:packet-1-claim-1`\n<!-- acs:auto:claims:end -->",
                        },
                        "status": "proposed",
                    }
                ],
            },
            ensure_ascii=False,
        ),
    )
    promotion_file = project_root / "data" / "promotions" / "packet-1.json"
    _write(
        promotion_file,
        json.dumps(
            [
                {
                    "candidate_id": "packet-1-candidate-1",
                    "packet_id": "packet-1",
                    "kind": "concept_update",
                    "target_page": "summarization",
                    "reason": "Add generated claim block.",
                    "evidence": ["claim:packet-1-claim-1"],
                    "proposed_change": "New generated claim.",
                    "proposed_action": "update_existing",
                    "confidence": 0.75,
                    "status": "pending",
                }
            ],
            ensure_ascii=False,
        ),
    )

    exit_code = main(
        [
            "apply-wiki-patch",
            "--patch-file",
            str(patch_file),
            "--apply",
            "--project-root",
            str(project_root),
            "--wiki-root",
            str(wiki_root),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "dry_run=False" in captured.out
    assert "applied=1" in captured.out
    updated = target.read_text(encoding="utf-8")
    assert "Human text." in updated
    assert "New generated claim." in updated

    applied_log = project_root / "data" / "wiki_patches" / "applied.jsonl"
    assert applied_log.exists()
    applied_records = [json.loads(line) for line in applied_log.read_text(encoding="utf-8").splitlines()]
    assert applied_records[0]["patch_id"] == "packet-1-patch-1"
    assert applied_records[0]["candidate_id"] == "packet-1-candidate-1"
    assert applied_records[0]["target"] == "concepts/summarization.md"

    promotions = json.loads(promotion_file.read_text(encoding="utf-8"))
    assert promotions[0]["status"] == "applied"


def test_cli_promote_packet_query_and_unit_concept_from_packet_json(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    packet_exit_code = main(
        [
            "build-context-packet",
            "--session-id",
            "session-1",
            "--packet-id",
            "packet-1",
            "--task-title",
            "Resume harness work",
            "--macro-context",
            "Need a durable packet for future session recovery.",
            "--unit-title",
            "Bootstrap project scaffold",
            "--goal",
            "Create the first usable harness substrate.",
            "--related-page",
            "architectures/agent-context-substrate.md",
            "--project-root",
            str(project_root),
        ]
    )
    assert packet_exit_code == 0
    capsys.readouterr()

    packet_json_path = project_root / "data" / "exports" / "context_packets" / "packet-1.json"

    query_exit_code = main(
        [
            "promote-packet-query",
            "--packet-json",
            str(packet_json_path),
            "--slug",
            "resume-harness-work",
            "--title",
            "Resume Harness Work",
            "--summary",
            "Reusable recovery note for resuming the harness pipeline.",
            "--related-page",
            "context-packet",
            "--tag",
            "question",
            "--tag",
            "context-packet",
            "--project-root",
            str(project_root),
        ]
    )
    query_captured = capsys.readouterr()

    concept_exit_code = main(
        [
            "promote-unit-concept",
            "--packet-json",
            str(packet_json_path),
            "--slug",
            "bootstrap-project-scaffold",
            "--title",
            "Bootstrap Project Scaffold",
            "--summary",
            "Concept page for the harness bootstrap workflow.",
            "--related-page",
            "hierarchical-summaries",
            "--tag",
            "implementation",
            "--tag",
            "knowledge-base",
            "--project-root",
            str(project_root),
        ]
    )
    concept_captured = capsys.readouterr()

    query_path = wiki_root / "queries" / "resume-harness-work.md"
    concept_path = wiki_root / "concepts" / "bootstrap-project-scaffold.md"

    assert query_exit_code == 0
    assert concept_exit_code == 0
    assert str(query_path) in query_captured.out
    assert str(concept_path) in concept_captured.out
    assert query_path.exists()
    assert concept_path.exists()

    query_markdown = query_path.read_text(encoding="utf-8")
    concept_markdown = concept_path.read_text(encoding="utf-8")

    assert "## Evidence and Provenance" in query_markdown
    assert "[[context-packet]]" in query_markdown
    assert "hermes-session:session-1#messages=1,2" in query_markdown
    assert "## Evidence and Provenance" in concept_markdown
    assert "[[hierarchical-summaries]]" in concept_markdown
    assert "Bootstrap project scaffold" in concept_markdown


def test_cli_promote_packet_plan_and_unit_architecture_from_packet_json(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    packet_exit_code = main(
        [
            "build-context-packet",
            "--session-id",
            "session-1",
            "--packet-id",
            "packet-2",
            "--task-title",
            "Resume harness work",
            "--macro-context",
            "Need a durable packet for future session recovery.",
            "--unit-title",
            "Bootstrap project scaffold",
            "--goal",
            "Create the first usable harness substrate.",
            "--related-page",
            "architectures/agent-context-substrate.md",
            "--project-root",
            str(project_root),
        ]
    )
    assert packet_exit_code == 0
    capsys.readouterr()

    packet_json_path = project_root / "data" / "exports" / "context_packets" / "packet-2.json"

    plan_exit_code = main(
        [
            "promote-packet-plan",
            "--packet-json",
            str(packet_json_path),
            "--slug",
            "resume-harness-plan",
            "--title",
            "Resume Harness Plan",
            "--summary",
            "Actionable plan page for resuming the harness work.",
            "--related-page",
            "context-packet",
            "--tag",
            "plan",
            "--tag",
            "implementation",
            "--project-root",
            str(project_root),
        ]
    )
    plan_captured = capsys.readouterr()

    architecture_exit_code = main(
        [
            "promote-unit-architecture",
            "--packet-json",
            str(packet_json_path),
            "--slug",
            "bootstrap-system-architecture",
            "--title",
            "Bootstrap System Architecture",
            "--summary",
            "Architecture page for the harness bootstrap workflow.",
            "--related-page",
            "hierarchical-summaries",
            "--tag",
            "implementation",
            "--tag",
            "architecture",
            "--project-root",
            str(project_root),
        ]
    )
    architecture_captured = capsys.readouterr()

    plan_path = wiki_root / "plans" / "resume-harness-plan.md"
    architecture_path = wiki_root / "architectures" / "bootstrap-system-architecture.md"

    assert plan_exit_code == 0
    assert architecture_exit_code == 0
    assert str(plan_path) in plan_captured.out
    assert str(architecture_path) in architecture_captured.out
    assert plan_path.exists()
    assert architecture_path.exists()

    plan_markdown = plan_path.read_text(encoding="utf-8")
    architecture_markdown = architecture_path.read_text(encoding="utf-8")

    assert "type: plan" in plan_markdown
    assert "## Current Understanding" in plan_markdown
    assert "Resume harness work" in plan_markdown
    assert "type: architecture" in architecture_markdown
    assert "## Current Understanding" in architecture_markdown
    assert "## Evidence and Provenance" in architecture_markdown


def test_cli_promotion_commands_auto_register_index_and_log(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    _write(
        wiki_root / "SCHEMA.md",
        "# Wiki Schema\n\n## Tag Taxonomy\n- question\n- implementation\n- plan\n- architecture\n- knowledge-base\n",
    )
    _write(
        wiki_root / "index.md",
        "# Wiki Index\n\n## Architectures\n- [[agent-context-substrate]] — Existing architecture page\n\n## Concepts\n- [[context-packet]] — Existing concept page\n- [[hierarchical-summaries]] — Existing concept page\n\n## Queries\n<!-- empty -->\n\n## Plans\n<!-- empty -->\n",
    )
    _write(wiki_root / "log.md", "# Wiki Log\n")
    _write(
        wiki_root / "architectures" / "agent-context-substrate.md",
        """---
title: Agent Context Substrate
created: 2026-04-22
updated: 2026-04-22
type: architecture
tags: [implementation]
sources: [\"raw/articles/example.md\"]
---

# Agent Context Substrate
""",
    )
    _write(
        wiki_root / "concepts" / "context-packet.md",
        """---
title: Context Packet
created: 2026-04-22
updated: 2026-04-22
type: concept
tags: [knowledge-base]
sources: [\"raw/articles/example.md\"]
---

# Context Packet
""",
    )
    _write(
        wiki_root / "concepts" / "hierarchical-summaries.md",
        """---
title: Hierarchical Summaries
created: 2026-04-22
updated: 2026-04-22
type: concept
tags: [knowledge-base]
sources: [\"raw/articles/example.md\"]
---

# Hierarchical Summaries
""",
    )

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    packet_exit_code = main(
        [
            "build-context-packet",
            "--session-id",
            "session-1",
            "--packet-id",
            "packet-ops",
            "--task-title",
            "Resume harness work",
            "--macro-context",
            "Need a durable packet for future session recovery.",
            "--unit-title",
            "Bootstrap project scaffold",
            "--goal",
            "Create the first usable harness substrate.",
            "--related-page",
            "architectures/agent-context-substrate.md",
            "--project-root",
            str(project_root),
        ]
    )
    assert packet_exit_code == 0
    capsys.readouterr()
    packet_json_path = project_root / "data" / "exports" / "context_packets" / "packet-ops.json"

    query_exit_code = main(
        [
            "promote-packet-query",
            "--packet-json",
            str(packet_json_path),
            "--slug",
            "resume-harness-work",
            "--title",
            "Resume Harness Work",
            "--summary",
            "Reusable recovery note for resuming the harness pipeline.",
            "--related-page",
            "context-packet",
            "--tag",
            "question",
            "--project-root",
            str(project_root),
        ]
    )
    assert query_exit_code == 0
    capsys.readouterr()

    plan_exit_code = main(
        [
            "promote-packet-plan",
            "--packet-json",
            str(packet_json_path),
            "--slug",
            "resume-harness-plan",
            "--title",
            "Resume Harness Plan",
            "--summary",
            "Actionable plan page for resuming the harness work.",
            "--related-page",
            "context-packet",
            "--tag",
            "plan",
            "--project-root",
            str(project_root),
        ]
    )
    assert plan_exit_code == 0
    capsys.readouterr()

    architecture_exit_code = main(
        [
            "promote-unit-architecture",
            "--packet-json",
            str(packet_json_path),
            "--slug",
            "bootstrap-system-architecture",
            "--title",
            "Bootstrap System Architecture",
            "--summary",
            "Architecture page for the harness bootstrap workflow.",
            "--related-page",
            "hierarchical-summaries",
            "--tag",
            "architecture",
            "--project-root",
            str(project_root),
        ]
    )
    assert architecture_exit_code == 0
    capsys.readouterr()

    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    log_text = (wiki_root / "log.md").read_text(encoding="utf-8")

    assert "[[resume-harness-work]] — Reusable recovery note for resuming the harness pipeline." in index_text
    assert "[[resume-harness-plan]] — Actionable plan page for resuming the harness work." in index_text
    assert "[[bootstrap-system-architecture]] — Architecture page for the harness bootstrap workflow." in index_text
    assert "<!-- empty -->\n\n- [[resume-harness-work]]" not in index_text
    assert "<!-- empty -->\n- [[resume-harness-plan]]" not in index_text
    assert "promote-packet-query" in log_text
    assert "promote-packet-plan" in log_text
    assert "promote-unit-architecture" in log_text


def test_cli_lint_wiki_fail_on_issues_returns_nonzero(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    _write(wiki_root / "SCHEMA.md", "# Wiki Schema\n\n## Tag Taxonomy\n- question\n")
    _write(wiki_root / "index.md", "# Wiki Index\n\n## Queries\n<!-- empty -->\n")
    _write(wiki_root / "log.md", "# Wiki Log\n")
    _write(
        wiki_root / "queries" / "page.md",
        """---
title: Page
created: 2026-04-22
updated: 2026-04-22
type: query
tags: [question]
sources: [\"hermes-session:session-1#messages=1\"]
---

# Page

[[missing-page]]
""",
    )

    exit_code = main(
        [
            "lint-wiki",
            "--project-root",
            str(project_root),
            "--report-id",
            "strict-lint",
            "--fail-on-issues",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "broken_wikilinks=1" in captured.out


def test_cli_run_e2e_pipeline_creates_packet_promotions_and_lint_report(tmp_path, monkeypatch, capsys) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    _write(wiki_root / "SCHEMA.md", "# Wiki Schema\n\n## Tag Taxonomy\n- question\n- implementation\n- knowledge-base\n- plan\n- architecture\n\n")
    _write(
        wiki_root / "index.md",
        "# Wiki Index\n\n## Architectures\n- [[agent-context-substrate]] — Existing architecture page\n\n## Concepts\n- [[context-packet]] — Existing concept page\n- [[hierarchical-summaries]] — Existing concept page\n\n## Queries\n<!-- empty -->\n\n## Plans\n<!-- empty -->\n",
    )
    _write(wiki_root / "log.md", "# Wiki Log\n")
    _write(
        wiki_root / "architectures" / "agent-context-substrate.md",
        """---
title: Agent Context Substrate
created: 2026-04-22
updated: 2026-04-22
type: architecture
tags: [implementation]
sources: [\"raw/articles/example.md\"]
---

# Agent Context Substrate

Links to [[context-packet]] and [[hierarchical-summaries]].
""",
    )
    _write(
        wiki_root / "concepts" / "context-packet.md",
        """---
title: Context Packet
created: 2026-04-22
updated: 2026-04-22
type: concept
tags: [knowledge-base]
sources: [\"raw/articles/example.md\"]
---

# Context Packet

Links to [[agent-context-substrate]].
""",
    )
    _write(
        wiki_root / "concepts" / "hierarchical-summaries.md",
        """---
title: Hierarchical Summaries
created: 2026-04-22
updated: 2026-04-22
type: concept
tags: [knowledge-base]
sources: [\"raw/articles/example.md\"]
---

# Hierarchical Summaries

Links to [[agent-context-substrate]].
""",
    )

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    exit_code = main(
        [
            "run-e2e-pipeline",
            "--session-id",
            "session-1",
            "--packet-id",
            "packet-e2e",
            "--task-title",
            "Resume harness work",
            "--macro-context",
            "Need a durable packet for future session recovery.",
            "--unit-title",
            "Bootstrap project scaffold",
            "--goal",
            "Create the first usable harness substrate.",
            "--packet-related-page",
            "architectures/agent-context-substrate.md",
            "--query-related-page",
            "context-packet",
            "--query-tag",
            "question",
            "--concept-related-page",
            "hierarchical-summaries",
            "--concept-tag",
            "implementation",
            "--concept-tag",
            "knowledge-base",
            "--plan-related-page",
            "context-packet",
            "--plan-tag",
            "plan",
            "--architecture-related-page",
            "hierarchical-summaries",
            "--architecture-tag",
            "architecture",
            "--report-id",
            "e2e-lint",
            "--project-root",
            str(project_root),
        ]
    )

    captured = capsys.readouterr()
    raw_export_path = project_root / "data" / "exports" / "session-1.json"
    packet_json_path = project_root / "data" / "exports" / "context_packets" / "packet-e2e.json"
    packet_md_path = project_root / "data" / "exports" / "context_packets" / "packet-e2e.md"
    query_path = wiki_root / "queries" / "packet-e2e.md"
    concept_path = wiki_root / "concepts" / "bootstrap-project-scaffold.md"
    plan_path = wiki_root / "plans" / "packet-e2e-plan.md"
    architecture_path = wiki_root / "architectures" / "bootstrap-project-scaffold-architecture.md"
    lint_json_path = project_root / "data" / "exports" / "lint" / "e2e-lint.json"
    lint_md_path = project_root / "data" / "exports" / "lint" / "e2e-lint.md"

    assert exit_code == 0
    for path in [
        raw_export_path,
        packet_json_path,
        packet_md_path,
        query_path,
        concept_path,
        plan_path,
        architecture_path,
        lint_json_path,
        lint_md_path,
    ]:
        assert path.exists()
        assert str(path) in captured.out

    query_markdown = query_path.read_text(encoding="utf-8")
    concept_markdown = concept_path.read_text(encoding="utf-8")
    plan_markdown = plan_path.read_text(encoding="utf-8")
    architecture_markdown = architecture_path.read_text(encoding="utf-8")
    lint_payload = json.loads(lint_json_path.read_text(encoding="utf-8"))

    assert "## Evidence and Provenance" in query_markdown
    assert "[[context-packet]]" in query_markdown
    assert "## Current Understanding" in concept_markdown
    assert concept_markdown.count("Bootstrap project scaffold") >= 1
    assert "type: plan" in plan_markdown
    assert "## Current Understanding" in plan_markdown
    assert "[[context-packet]]" in plan_markdown
    assert "type: architecture" in architecture_markdown
    assert "## Current Understanding" in architecture_markdown
    assert "## Evidence and Provenance" in architecture_markdown
    assert "[[hierarchical-summaries]]" in architecture_markdown
    assert lint_payload["broken_wikilinks"] == []
    assert lint_payload["missing_provenance_pages"] == []
    assert lint_payload["pages_missing_from_index"] == []

    index_text = (wiki_root / "index.md").read_text(encoding="utf-8")
    log_text = (wiki_root / "log.md").read_text(encoding="utf-8")
    assert "[[packet-e2e]]" in index_text
    assert "[[bootstrap-project-scaffold]]" in index_text
    assert "[[packet-e2e-plan]]" in index_text
    assert "[[bootstrap-project-scaffold-architecture]]" in index_text
    assert "e2e pipeline" in log_text.lower()


def test_cli_distribution_install_and_doctor_commands(tmp_path, capsys) -> None:
    hermes_home = tmp_path / "hermes-home"
    hermes_agent_root = tmp_path / "hermes-agent"
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    (hermes_home).mkdir()
    (hermes_home / "state.db").write_bytes(b"")
    (project_root / "src" / "agent_context_substrate").mkdir(parents=True)

    init_exit = main(["init-wiki", "--wiki-root", str(wiki_root)])
    plugin_exit = main(
        [
            "install-plugin",
            "--hermes-home",
            str(hermes_home),
            "--project-root",
            str(project_root),
            "--wiki-root",
            str(wiki_root),
        ]
    )
    engine_exit = main(
        [
            "install-context-engine",
            "--hermes-agent-root",
            str(hermes_agent_root),
        ]
    )
    doctor_exit = main(
        [
            "doctor",
            "--hermes-home",
            str(hermes_home),
            "--project-root",
            str(project_root),
            "--wiki-root",
            str(wiki_root),
            "--hermes-agent-root",
            str(hermes_agent_root),
            "--fail-on-issues",
        ]
    )

    captured = capsys.readouterr()

    assert init_exit == 0
    assert plugin_exit == 0
    assert engine_exit == 0
    assert doctor_exit == 0
    assert "initialized" in captured.out
    assert "user plugin installed" in captured.out
    assert "context engine installed" in captured.out
    assert "doctor ok=True" in captured.out
    assert (wiki_root / "_system" / "config.yaml").exists()
    assert (hermes_home / "plugins" / "agent-context-substrate" / "plugin.yaml").exists()
    assert (
        hermes_agent_root / "plugins" / "context_engine" / "agent_context_substrate" / "engine.py"
    ).exists()


def test_cli_doctor_fail_on_issues_returns_nonzero(tmp_path, capsys) -> None:
    exit_code = main(
        [
            "doctor",
            "--hermes-home",
            str(tmp_path / "missing-home"),
            "--project-root",
            str(tmp_path / "missing-project"),
            "--wiki-root",
            str(tmp_path / "missing-wiki"),
            "--hermes-agent-root",
            str(tmp_path / "missing-agent"),
            "--fail-on-issues",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "doctor ok=False" in captured.out
    assert "state_db_exists=missing" in captured.out


def test_cli_fresh_install_smoke_command(tmp_path, capsys) -> None:
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    hermes_agent_root = tmp_path / "hermes-agent"

    exit_code = main(
        [
            "fresh-install-smoke",
            "--session-id",
            "session-1",
            "--hermes-home",
            str(hermes_home),
            "--project-root",
            str(project_root),
            "--wiki-root",
            str(wiki_root),
            "--hermes-agent-root",
            str(hermes_agent_root),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "fresh-install-smoke ok=True" in captured.out
    assert "retrieval_hit_count=" in captured.out
    assert "lint_issue_count=0" in captured.out
    assert "packet_json_path=" in captured.out
