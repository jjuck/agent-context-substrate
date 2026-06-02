import json
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import agent_context_substrate.integration as integration_module  # noqa: E402
from agent_context_substrate.integration import (  # noqa: E402
    PipelineRetryExhaustedError,
    run_session_finalize_pipeline,
    should_process_session,
)
from agent_context_substrate.ledger import SessionLedger  # noqa: E402
from agent_context_substrate.naming import (  # noqa: E402
    derive_goal,
    derive_task_title,
    derive_unit_title,
)
from agent_context_substrate.policy import should_process_bundle  # noqa: E402
from agent_context_substrate.session_bundle import SessionBundle, SessionMessage  # noqa: E402
from agent_context_substrate.summarizer import build_micro_summary  # noqa: E402


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
        ("session-1", "telegram", 1776395277.0, 4, "Harness integration planning"),
    )
    cur.executemany(
        "INSERT INTO messages (id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "session-1", "user", "Attach agent-context-substrate to Hermes Agent and design the integration path.", 1776395278.0),
            (2, "session-1", "assistant", "I will inspect state.db, gateway hooks, and plugin/context-engine extension points.", 1776395280.0),
            (3, "session-1", "assistant", "Key files: /home/example/.hermes/hermes-agent/hermes_state.py, gateway/run.py, hermes_cli/plugins.py, agent/context_engine.py", 1776395282.0),
            (4, "session-1", "user", "Create docs/plans/2026-04-23-hermes-agent-integration-plan.md and wire integration.py next.", 1776395284.0),
        ],
    )
    conn.commit()
    conn.close()


def test_run_session_finalize_pipeline_defaults_to_packet_only_without_wiki_promotion(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    result = run_session_finalize_pipeline(
        session_id="session-1",
        project_root=project_root,
        wiki_root=wiki_root,
    )

    assert result.session_id == "session-1"
    assert result.packet_id == "session-1"
    assert result.raw_export_path.exists()
    assert result.packet_json_path.exists()
    assert result.packet_markdown_path.exists()
    assert result.promoted_paths == {}
    assert result.lint_json_path.exists()
    assert result.lint_markdown_path.exists()
    assert result.recovery_json_path.exists()
    assert not (wiki_root / "queries").exists()
    assert not (wiki_root / "concepts").exists()
    assert not (wiki_root / "plans").exists()
    assert not (wiki_root / "architectures").exists()

    payload = json.loads(result.packet_json_path.read_text(encoding="utf-8"))
    assert payload["packet_id"] == "session-1"
    assert payload["unit_summaries"][0]["session_id"] == "session-1"


class IntegrationRecordingRouter:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: dict[str, object]) -> dict[str, object]:
        self.requests.append(request)
        if request["kind"] == "micro":
            evidence = request["evidence"]
            return {
                "micro_id": evidence["micro_id"],
                "session_id": evidence["session_id"],
                "message_ids": evidence["message_ids"],
                "recovery_summary": "agent recovery summary",
                "knowledge_summary": "agent knowledge summary",
                "retrieval_summary": "Agent LLM router integration agent-context-substrate",
                "user_intent": "use agent llm router",
                "assistant_outcome": "exported agent llm summary",
                "decisions": [
                    {
                        "text": "Use host Agent LLM router",
                        "evidence_message_ids": evidence["message_ids"],
                        "confidence": 0.9,
                    }
                ],
                "claims": [],
                "action_items": [],
                "open_questions": [],
                "files": [],
                "entities": [],
                "concepts": ["agent-context-substrate"],
                "metadata": {
                    "mode": "agent-llm",
                    "schema_version": "micro_summary_v2",
                    "prompt_version": "agent_llm_v1",
                    "model": None,
                    "input_hash": "sha256:integration-micro",
                    "created_at": "2026-05-15T00:00:00+00:00",
                    "confidence": 0.9,
                },
                "provenance": None,
            }
        micro = request["micro_summaries"][0]
        return {
            "unit_id": request["unit_id"],
            "session_id": request["session_id"],
            "title": request["title"],
            "goal": request["goal"],
            "state": "completed",
            "decisions": micro["decisions"],
            "progress": ["exported agent llm summary"],
            "next_actions": [],
            "open_questions": [],
            "risk_notes": [],
            "wiki_candidates": [],
            "micro_ids": [micro["micro_id"]],
            "related_pages": request["related_pages"],
            "metadata": {
                "mode": "agent-llm",
                "schema_version": "unit_summary_v2",
                "prompt_version": "agent_llm_v1",
                "model": None,
                "input_hash": "sha256:integration-unit",
                "created_at": "2026-05-15T00:00:00+00:00",
                "confidence": 0.9,
            },
            "provenance": None,
        }


class JudgeIntegrationRouter(IntegrationRecordingRouter):
    def __call__(self, request: dict[str, object]) -> dict[str, object]:
        if request["kind"] == "summary-judge":
            self.requests.append(request)
            recovery_gate = request["recovery_quality_gate"]
            return {
                "ok": True,
                "score": 0.91,
                "decision": "accept",
                "issues": [],
                "rationale": f"Recovery gate score {recovery_gate['score']} is good enough for alpha.",
                "metadata": {"mode": "integration"},
            }
        return super().__call__(request)


def test_run_session_finalize_pipeline_exports_agent_llm_v2_summaries_with_injected_router(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")
    router = IntegrationRecordingRouter()

    result = run_session_finalize_pipeline(
        session_id="session-1",
        project_root=project_root,
        wiki_root=wiki_root,
        summary_mode="agent-llm",
        agent_llm_router=router,
        summary_model="host-default",
        summary_budget="cheap",
    )

    assert result.summary_micro_path is not None
    assert result.summary_unit_path is not None
    assert result.summary_evidence_path is not None
    micro_payload = json.loads(result.summary_micro_path.read_text(encoding="utf-8"))
    unit_payload = json.loads(result.summary_unit_path.read_text(encoding="utf-8"))
    assert micro_payload["metadata"]["mode"] == "agent-llm"
    assert unit_payload["metadata"]["mode"] == "agent-llm"
    assert [request["kind"] for request in router.requests] == ["micro", "unit"]
    assert router.requests[0]["routing_hints"] == {"model": "host-default", "budget": "cheap"}

    ledger = SessionLedger(project_root / "data" / "index" / "session_ledger.json")
    record = ledger.get_record("session-1", "session_finalize")
    assert record is not None
    assert Path(record.artifact_paths["summary_micro_path"]) == result.summary_micro_path
    assert Path(record.artifact_paths["summary_unit_path"]) == result.summary_unit_path
    assert Path(record.artifact_paths["summary_evidence_path"]) == result.summary_evidence_path


def test_run_session_finalize_pipeline_exports_summary_judge_with_recovery_gate(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    _build_sample_state_db(hermes_home / "state.db")
    router = JudgeIntegrationRouter()

    result = run_session_finalize_pipeline(
        session_id="session-1",
        project_root=project_root,
        wiki_root=wiki_root,
        summary_mode="agent-llm",
        agent_llm_router=router,
        summary_judge_mode="hybrid",
    )

    assert result.summary_judge_path is not None
    payload = json.loads(result.summary_judge_path.read_text(encoding="utf-8"))
    assert payload["decision"] == "accept"
    assert payload["metadata"] == {
        "mode": "integration",
        "judge_mode": "hybrid",
        "schema_version": "summary_judge_v1",
    }
    assert [request["kind"] for request in router.requests] == ["micro", "unit", "summary-judge"]
    judge_request = router.requests[-1]
    assert judge_request["recovery_quality_gate"]["ok"] is True
    assert judge_request["recovery_quality_gate"]["score"] >= 0.8

    ledger = SessionLedger(project_root / "data" / "index" / "session_ledger.json")
    record = ledger.get_record("session-1", "session_finalize")
    assert record is not None
    assert Path(record.artifact_paths["summary_judge_path"]) == result.summary_judge_path


def test_run_session_finalize_pipeline_full_mode_writes_legacy_promotions(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    result = run_session_finalize_pipeline(
        session_id="session-1",
        project_root=project_root,
        wiki_root=wiki_root,
        promotion_mode="full",
    )

    assert result.promoted_paths["query"].exists()
    assert result.promoted_paths["concept"].exists()
    assert result.promoted_paths["plan"].exists()
    assert result.promoted_paths["architecture"].exists()


def test_default_promotion_plan_cross_links_all_generated_pages() -> None:
    plan = integration_module._build_default_promotion_plan(
        packet_id="session-1",
        session_id="session-1",
        task_title="Task Title",
        unit_title="My Unit",
        related_pages=["existing-page", "existing-page"],
    )

    assert plan.slugs == ["session-1", "my-unit", "session-1-plan", "my-unit-architecture"]
    assert plan.summaries["query"] == "Durable query page derived from session session-1."
    assert plan.summaries["concept"] == "Durable concept page derived from session session-1."
    assert plan.related_pages_by_kind["query"] == [
        "my-unit",
        "session-1-plan",
        "my-unit-architecture",
        "existing-page",
    ]
    assert plan.related_pages_by_kind["concept"] == [
        "session-1",
        "session-1-plan",
        "my-unit-architecture",
        "existing-page",
    ]
    assert plan.related_pages_by_kind["plan"] == [
        "session-1",
        "my-unit",
        "my-unit-architecture",
        "existing-page",
    ]
    assert plan.related_pages_by_kind["architecture"] == [
        "session-1",
        "my-unit",
        "session-1-plan",
        "existing-page",
    ]


def test_run_session_finalize_pipeline_links_default_promotions_to_avoid_orphans(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    result = run_session_finalize_pipeline(
        session_id="session-1",
        project_root=project_root,
        wiki_root=wiki_root,
        promotion_mode="full",
    )

    from agent_context_substrate.lint import lint_wiki  # noqa: E402
    from agent_context_substrate.paths import HarnessPaths  # noqa: E402

    report = lint_wiki(HarnessPaths(project_root=project_root))
    assert report.checked_pages == sorted(
        path.relative_to(wiki_root).as_posix()
        for path in result.promoted_paths.values()
    )
    assert report.orphan_pages == []
    assert report.broken_wikilinks == []


def test_run_session_finalize_pipeline_rebuilds_when_requested_promotion_mode_changes(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    full_result = run_session_finalize_pipeline(
        session_id="session-1",
        project_root=project_root,
        wiki_root=wiki_root,
        promotion_mode="full",
    )
    assert full_result.promoted_paths

    packet_only_result = run_session_finalize_pipeline(
        session_id="session-1",
        project_root=project_root,
        wiki_root=wiki_root,
        promotion_mode="packet-only",
    )

    assert not packet_only_result.skipped
    assert packet_only_result.promoted_paths == {}
    ledger = SessionLedger(project_root / "data" / "index" / "session_ledger.json")
    record = ledger.get_record("session-1", "session_finalize")
    assert record is not None
    assert record.artifact_paths["promotion_mode"] == "packet-only"


def test_run_session_finalize_pipeline_marks_failure_for_retryable_errors(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    try:
        run_session_finalize_pipeline(
            session_id="missing-session",
            project_root=project_root,
            wiki_root=wiki_root,
        )
    except KeyError:
        pass
    else:  # pragma: no cover - defensive assertion for test clarity
        raise AssertionError("missing sessions must still raise to the plugin boundary")

    ledger = SessionLedger(project_root / "data" / "index" / "session_ledger.json")
    record = ledger.get_record("missing-session", "session_finalize")
    assert record is not None
    assert record.status == "failed"
    assert record.attempt_count == 1
    assert "KeyError" in record.last_error


def test_run_session_finalize_pipeline_stops_after_retry_budget_is_exhausted(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    for _ in range(2):
        try:
            run_session_finalize_pipeline(
                session_id="missing-session",
                project_root=project_root,
                wiki_root=wiki_root,
                max_retry_attempts=2,
            )
        except KeyError:
            pass

    try:
        run_session_finalize_pipeline(
            session_id="missing-session",
            project_root=project_root,
            wiki_root=wiki_root,
            max_retry_attempts=2,
        )
    except PipelineRetryExhaustedError as exc:
        assert "missing-session" in str(exc)
    else:  # pragma: no cover - defensive assertion for test clarity
        raise AssertionError("exhausted retry budget must block repeated finalize attempts")

    ledger = SessionLedger(project_root / "data" / "index" / "session_ledger.json")
    record = ledger.get_record("missing-session", "session_finalize")
    assert record is not None
    assert record.status == "failed"
    assert record.attempt_count == 2


def test_run_session_finalize_pipeline_preserves_partial_artifacts_on_late_failure(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    def _raise_recovery_failure(*args, **kwargs):
        raise RuntimeError("synthetic recovery failure")

    monkeypatch.setattr(integration_module, "build_recovery_brief", _raise_recovery_failure)

    try:
        run_session_finalize_pipeline(
            session_id="session-1",
            project_root=project_root,
            wiki_root=wiki_root,
        )
    except RuntimeError as exc:
        assert "synthetic recovery failure" in str(exc)
    else:  # pragma: no cover - defensive assertion for test clarity
        raise AssertionError("late recovery failure must still raise to the plugin boundary")

    ledger = SessionLedger(project_root / "data" / "index" / "session_ledger.json")
    record = ledger.get_record("session-1", "session_finalize")
    assert record is not None
    assert record.status == "failed"
    assert record.attempt_count == 1
    assert "RuntimeError" in record.last_error
    assert Path(record.artifact_paths["packet_json_path"]).exists()
    assert Path(record.artifact_paths["lint_json_path"]).exists()
    assert "recovery_json_path" not in record.artifact_paths


def test_run_session_finalize_pipeline_rebuilds_stale_completed_records(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    stale_paths = {
        "raw_export_path": str(tmp_path / "missing" / "raw.json"),
        "packet_json_path": str(tmp_path / "missing" / "packet.json"),
        "packet_markdown_path": str(tmp_path / "missing" / "packet.md"),
        "query": str(tmp_path / "missing" / "query.md"),
        "concept": str(tmp_path / "missing" / "concept.md"),
        "plan": str(tmp_path / "missing" / "plan.md"),
        "architecture": str(tmp_path / "missing" / "architecture.md"),
        "lint_json_path": str(tmp_path / "missing" / "lint.json"),
        "lint_markdown_path": str(tmp_path / "missing" / "lint.md"),
        "recovery_json_path": str(tmp_path / "missing" / "recovery.json"),
    }
    ledger = SessionLedger(project_root / "data" / "index" / "session_ledger.json")
    ledger.mark_completed(
        session_id="session-1",
        pipeline="session_finalize",
        artifact_paths=stale_paths,
        issue_count=0,
    )

    result = run_session_finalize_pipeline(
        session_id="session-1",
        project_root=project_root,
        wiki_root=wiki_root,
        promotion_mode="full",
    )

    assert not result.skipped
    assert result.packet_json_path.exists()
    assert result.recovery_json_path.exists()
    assert result.packet_json_path != Path(stale_paths["packet_json_path"])


def test_should_process_session_applies_threshold_and_source_allowlist(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    assert should_process_session("session-1", min_message_count=3, allowed_sources=["telegram"])
    assert not should_process_session("session-1", min_message_count=5, allowed_sources=["telegram"])
    assert not should_process_session("session-1", min_message_count=3, allowed_sources=["cli"])


def test_should_process_session_uses_typed_session_boundary(monkeypatch) -> None:
    calls: list[str] = []
    typed_bundle = SessionBundle(
        session_id="session-typed",
        source="telegram",
        title="Typed integration",
        messages=[
            SessionMessage(id=1, role="user", content="Start"),
            SessionMessage(id=2, role="assistant", content="Done"),
        ],
    )

    def fake_build_typed_session_bundle(*, session_id, paths):
        calls.append(session_id)
        return typed_bundle

    monkeypatch.setattr(integration_module, "build_typed_session_bundle", fake_build_typed_session_bundle)

    assert should_process_session("session-typed", min_message_count=2, allowed_sources=["telegram"])
    assert calls == ["session-typed"]


def test_naming_helpers_derive_titles_goal_and_policy_from_raw_bundle(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    _build_sample_state_db(hermes_home / "state.db")

    from agent_context_substrate.paths import HarnessPaths  # noqa: E402
    from agent_context_substrate.raw_extract import build_session_bundle  # noqa: E402

    paths = HarnessPaths(project_root=project_root)
    raw_bundle = build_session_bundle("session-1", paths=paths)
    task_title = derive_task_title(raw_bundle, "session-1")
    unit_title = derive_unit_title(raw_bundle, task_title)
    micro_summary = build_micro_summary(
        raw_bundle=raw_bundle,
        micro_id="session-1-micro-1",
        parent_unit_id="session-1-unit-1",
    )
    goal = derive_goal(task_title, micro_summary)

    assert task_title == "Harness integration planning"
    assert unit_title.startswith("Attach agent-context-substrate to Hermes Agent")
    assert "Attach agent-context-substrate to Hermes Agent" in goal
    assert should_process_bundle(
        raw_bundle,
        min_message_count=3,
        allowed_sources=["telegram"],
        skip_title_patterns=[r"^scratch", r"^tmp"],
    )
    assert not should_process_bundle(
        raw_bundle,
        min_message_count=3,
        allowed_sources=["telegram"],
        skip_title_patterns=[r"^Harness integration planning$"],
    )
