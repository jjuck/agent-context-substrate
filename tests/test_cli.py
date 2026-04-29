import json
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.cli import main  # noqa: E402


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

    assert "## Provenance" in query_markdown
    assert "[[context-packet]]" in query_markdown
    assert "hermes-session:session-1#messages=1,2" in query_markdown
    assert "## Evidence" in concept_markdown
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
    assert "## Proposed Steps" in plan_markdown
    assert "Resume harness work" in plan_markdown
    assert "type: architecture" in architecture_markdown
    assert "## Goal" in architecture_markdown
    assert "## Key Artifacts" in architecture_markdown


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

    assert "## Provenance" in query_markdown
    assert "[[context-packet]]" in query_markdown
    assert "## Source Unit" in concept_markdown
    assert concept_markdown.count("Bootstrap project scaffold") >= 1
    assert "type: plan" in plan_markdown
    assert "## Proposed Steps" in plan_markdown
    assert "[[context-packet]]" in plan_markdown
    assert "type: architecture" in architecture_markdown
    assert "## Goal" in architecture_markdown
    assert "## Key Artifacts" in architecture_markdown
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
