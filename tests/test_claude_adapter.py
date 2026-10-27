from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import json
import os
import subprocess
import sys

import pytest

import agent_context_substrate.claude_hook as claude_hook
from agent_context_substrate.claude_hook import (
    build_claude_stop_finalize_decision,
    default_claude_hook_event_log_path,
    default_claude_jobs_path,
    run_claude_stop_finalize_hook,
)
from agent_context_substrate.claude_integration import (
    ClaudeSessionChangedError,
    run_claude_session_finalize_pipeline,
)
from agent_context_substrate.claude_runtime_config import load_claude_runtime_config
from agent_context_substrate.claude_source import (
    build_claude_session_bundle,
    discover_claude_sessions,
    resolve_claude_session,
)
from agent_context_substrate.claude_worker import read_claude_worker_status, run_claude_worker
from agent_context_substrate.codex_hook import CodexHookCommandRunnerResult
from agent_context_substrate.codex_jobs import CodexJobQueue, default_codex_jobs_path, encode_rollout_fingerprint
from agent_context_substrate.codex_runtime_config import codex_config_digest


SESSION_ID = "0b6f0c3e-1111-4222-8333-944445555666"


def _entry(entry_type: str, content: object, **extra: object) -> dict[str, object]:
    return {
        "type": entry_type,
        "sessionId": SESSION_ID,
        "uuid": f"uuid-{len(json.dumps(content))}",
        "timestamp": extra.pop("timestamp", "2026-10-27T00:00:00Z"),
        "cwd": "C:\\work\\프로젝트",
        "gitBranch": "main",
        "isSidechain": extra.pop("isSidechain", False),
        "message": {"role": entry_type, "content": content},
        **extra,
    }


def _write_transcript(claude_home: Path, *, session_id: str = SESSION_ID, extra_text: str = "") -> Path:
    path = claude_home / "projects" / "C--work" / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        {"type": "custom-title", "customTitle": "Claude 어댑터 작업", "sessionId": session_id},
        _entry("user", "Claude Code 어댑터를 추가해줘 token=abc123 me@example.com"),
        _entry("user", "<local-command-caveat>meta</local-command-caveat>", isMeta=True),
        _entry(
            "assistant",
            [
                {"type": "thinking", "thinking": "", "signature": "sig"},
                {"type": "text", "text": "Adding the Claude adapter."},
                {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "pytest"}},
            ],
            timestamp="2026-10-27T00:01:00Z",
        ),
        _entry(
            "user",
            [{"type": "tool_result", "tool_use_id": "toolu_1", "content": [{"type": "text", "text": "470 passed"}]}],
        ),
        _entry("assistant", [{"type": "text", "text": "sidechain noise"}], isSidechain=True),
        {"type": "file-history-snapshot", "snapshot": {}},
        _entry(
            "assistant",
            [{"type": "text", "text": f"Claude adapter is implemented. {extra_text}".strip()}],
            timestamp="2026-10-27T00:02:00Z",
        ),
    ]
    path.write_text("\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\nnot-json\n", encoding="utf-8")
    return path


def _write_config(path: Path, *, project_root: Path, wiki_root: Path, claude_home: Path, **overrides: object) -> dict:
    config: dict[str, object] = {
        "adapter": "claude-code",
        "project_root": str(project_root),
        "wiki_root": str(wiki_root),
        "wiki_root_source": "explicit",
        "claude_home": str(claude_home),
        "trigger_strategy": "hook-enqueue",
        "worker_idle_grace_seconds": 0,
        "worker_lease_seconds": 600,
        "worker_max_attempts": 3,
        "worker_retry_base_seconds": 60,
    }
    config.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return config


def _stop_payload(transcript_path: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "session_id": SESSION_ID,
        "transcript_path": str(transcript_path),
        "cwd": str(transcript_path.parent),
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def env(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "사용자"
    paths = {
        "claude_home": root / ".claude",
        "project_root": root / "acs",
        "wiki_root": root / "wiki",
        "config_path": root / ".claude" / "agent-context-substrate" / "local_config.json",
    }
    paths["wiki_root"].mkdir(parents=True)
    paths["transcript"] = _write_transcript(paths["claude_home"])
    return paths


def test_claude_transcript_becomes_session_bundle(env: dict[str, Path]) -> None:
    bundle = build_claude_session_bundle(session_id=SESSION_ID, transcript_path=env["transcript"])

    assert bundle.source == "claude-code"
    assert bundle.title == "Claude 어댑터 작업"
    assert bundle.started_at == "2026-10-27T00:00:00Z"
    assert bundle.ended_at == "2026-10-27T00:02:00Z"
    assert [(message.role, message.content) for message in bundle.messages] == [
        ("user", "Claude Code 어댑터를 추가해줘 token=[REDACTED] [REDACTED_EMAIL]"),
        ("assistant", "Adding the Claude adapter."),
        ("tool", 'function_call name=Bash call_id=toolu_1 arguments={"command": "pytest"}'),
        ("tool", "470 passed"),
        ("assistant", "Claude adapter is implemented."),
    ]
    assert bundle.messages[2].metadata["tool_name"] == "Bash"
    assert bundle.messages[3].metadata["call_id"] == "toolu_1"
    assert bundle.metadata["cwd"] == "C:\\work\\프로젝트"
    assert bundle.metadata["provenance"] == f"claude-session:{SESSION_ID}#messages=1,2,3,4,5"


def test_claude_sessions_are_discovered_by_session_id(env: dict[str, Path]) -> None:
    sessions = discover_claude_sessions(claude_home=env["claude_home"])

    assert [session.session_id for session in sessions] == [SESSION_ID]
    record = resolve_claude_session(session_id=SESSION_ID, claude_home=env["claude_home"])
    assert record.transcript_path == env["transcript"]
    assert record.fingerprint["rollout_path"] == str(env["transcript"])
    with pytest.raises(KeyError):
        resolve_claude_session(session_id="missing", claude_home=env["claude_home"])


def test_claude_config_follows_canonical_path(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.json"
    canonical.write_text(json.dumps({"project_root": "canonical"}), encoding="utf-8")
    bootstrap = tmp_path / "bootstrap.json"
    bootstrap.write_text(json.dumps({"canonical_config_path": str(canonical)}), encoding="utf-8")

    assert load_claude_runtime_config(bootstrap) == {"project_root": "canonical"}
    assert load_claude_runtime_config(tmp_path / "missing.json") == {}


def test_stop_hook_active_does_nothing(env: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(env["config_path"], project_root=env["project_root"], wiki_root=env["wiki_root"], claude_home=env["claude_home"])
    monkeypatch.setattr(claude_hook, "_start_claude_worker", lambda **_kwargs: pytest.fail("worker started"))

    output = run_claude_stop_finalize_hook(
        payload=_stop_payload(env["transcript"], stop_hook_active=True),
        config_path=env["config_path"],
    )

    assert output == {}
    assert not default_claude_jobs_path(env["project_root"]).exists()
    assert not default_claude_hook_event_log_path(env["project_root"]).exists()


def test_stop_hook_enqueues_durable_job_and_starts_worker(
    env: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _write_config(
        env["config_path"], project_root=env["project_root"], wiki_root=env["wiki_root"], claude_home=env["claude_home"]
    )
    launches: list[dict[str, object]] = []
    monkeypatch.setattr(claude_hook, "_start_claude_worker", lambda **kwargs: launches.append(kwargs))

    output = run_claude_stop_finalize_hook(payload=_stop_payload(env["transcript"]), config_path=env["config_path"])

    assert output == {"continue": True, "suppressOutput": True}
    assert "decision" not in output
    jobs = CodexJobQueue(default_claude_jobs_path(env["project_root"])).list_jobs()
    assert len(jobs) == 1
    assert jobs[0].thread_id == SESSION_ID
    assert jobs[0].payload["transcript_path"] == str(env["transcript"])
    assert jobs[0].config_digest == codex_config_digest(config)
    assert launches and launches[0]["config_path"] == env["config_path"]
    assert not default_codex_jobs_path(env["project_root"]).exists()
    events = default_claude_hook_event_log_path(env["project_root"]).read_text(encoding="utf-8").splitlines()
    assert json.loads(events[-1])["status"] == "enqueued"


def test_stop_hook_failures_never_block(env: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    missing = run_claude_stop_finalize_hook(
        payload=_stop_payload(env["transcript"]),
        config_path=env["config_path"],
    )
    assert missing["continue"] is True
    assert "configuration error" in missing["systemMessage"]
    assert "decision" not in missing

    _write_config(env["config_path"], project_root=env["project_root"], wiki_root=env["wiki_root"], claude_home=env["claude_home"])
    monkeypatch.setattr(
        claude_hook,
        "enqueue_claude_stop_job",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    failed = run_claude_stop_finalize_hook(payload=_stop_payload(env["transcript"]), config_path=env["config_path"])
    assert failed["continue"] is True
    assert "disk full" in failed["systemMessage"]

    skipped = run_claude_stop_finalize_hook(
        payload=_stop_payload(env["transcript"], hook_event_name="SubagentStop"),
        config_path=env["config_path"],
    )
    assert skipped == {"continue": True, "suppressOutput": True}


def test_decision_builds_claude_finalize_command(env: dict[str, Path]) -> None:
    config = _write_config(
        env["config_path"],
        project_root=env["project_root"],
        wiki_root=env["wiki_root"],
        claude_home=env["claude_home"],
        summary_mode="auto",
        codex_cli_command="codex.exe",
        wiki_auto_mode="apply-flexible",
    )

    decision = build_claude_stop_finalize_decision(
        payload=_stop_payload(env["transcript"]),
        config=config,
        python_executable="python",
    )

    assert decision.should_finalize
    assert decision.command[:4] == ["python", "-m", "agent_context_substrate.cli", "claude-finalize"]
    assert decision.command[decision.command.index("--transcript-path") + 1] == str(env["transcript"])
    assert decision.command[decision.command.index("--codex-cli-command") + 1] == "codex.exe"
    assert decision.command[decision.command.index("--wiki-auto-mode") + 1] == "apply-flexible"


def test_worker_drains_claude_job_with_expected_fingerprint(env: dict[str, Path]) -> None:
    config = _write_config(
        env["config_path"], project_root=env["project_root"], wiki_root=env["wiki_root"], claude_home=env["claude_home"]
    )
    record = resolve_claude_session(session_id=SESSION_ID, transcript_path=env["transcript"])
    queue = CodexJobQueue(default_claude_jobs_path(env["project_root"]))
    job = queue.enqueue(
        thread_id=SESSION_ID,
        rollout_fingerprint=encode_rollout_fingerprint(record.fingerprint),
        config_digest=codex_config_digest(config),
        payload={"transcript_path": str(env["transcript"]), "cwd": ""},
    )
    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs: object) -> CodexHookCommandRunnerResult:
        calls.append(command)
        return CodexHookCommandRunnerResult(returncode=0)

    result = run_claude_worker(config_path=env["config_path"], command_runner=runner)

    assert result.lock_acquired and result.completed_count == 1
    assert queue.get(job.id).status == "completed"
    command = calls[0]
    assert "claude-finalize" in command
    assert command[command.index("--expected-transcript-size") + 1] == str(record.fingerprint["size"])
    assert command[command.index("--runtime-config-path") + 1] == str(env["config_path"].resolve())
    assert command[command.index("--expected-config-digest") + 1] == job.config_digest
    status = read_claude_worker_status(env["project_root"])
    assert status["status"] == "idle"
    assert status["queue_pending_count"] == 0


def test_worker_refreshes_job_when_transcript_grew(env: dict[str, Path]) -> None:
    config = _write_config(
        env["config_path"], project_root=env["project_root"], wiki_root=env["wiki_root"], claude_home=env["claude_home"]
    )
    record = resolve_claude_session(session_id=SESSION_ID, transcript_path=env["transcript"])
    queue = CodexJobQueue(default_claude_jobs_path(env["project_root"]))
    stale = queue.enqueue(
        thread_id=SESSION_ID,
        rollout_fingerprint=encode_rollout_fingerprint(record.fingerprint),
        config_digest=codex_config_digest(config),
        payload={"transcript_path": str(env["transcript"]), "cwd": ""},
    )
    _write_transcript(env["claude_home"], extra_text="More work landed.")

    result = run_claude_worker(
        config_path=env["config_path"],
        command_runner=lambda *_args, **_kwargs: CodexHookCommandRunnerResult(returncode=0),
    )

    assert result.refreshed_count == 1 and result.completed_count == 1
    assert queue.get(stale.id).status == "completed"
    assert len(queue.list_jobs(status="completed")) == 2


def test_claude_finalize_exports_packet_and_recovery(env: dict[str, Path]) -> None:
    result = run_claude_session_finalize_pipeline(
        session_id=SESSION_ID,
        transcript_path=env["transcript"],
        project_root=env["project_root"],
        wiki_root=env["wiki_root"],
    )

    assert result.raw_export_path == env["project_root"].resolve() / "data" / "exports" / "raw" / "claude" / f"{SESSION_ID}.json"
    packet = json.loads(result.packet_json_path.read_text(encoding="utf-8"))
    assert packet["raw_pointers"][0]["source"] == "claude-code"
    recovery = json.loads(result.recovery_json_path.read_text(encoding="utf-8"))
    assert recovery["provenance"] == [f"claude-session:{SESSION_ID}#messages=1,2,3,4,5"]
    ledger = json.loads((env["project_root"] / "data" / "index" / "session_ledger.json").read_text(encoding="utf-8"))
    assert SESSION_ID in json.dumps(ledger)


def test_claude_finalize_rejects_stale_snapshot(env: dict[str, Path]) -> None:
    stale = resolve_claude_session(session_id=SESSION_ID, transcript_path=env["transcript"]).fingerprint
    _write_transcript(env["claude_home"], extra_text="Changed after enqueue.")

    with pytest.raises(ClaudeSessionChangedError):
        run_claude_session_finalize_pipeline(
            session_id=SESSION_ID,
            transcript_path=env["transcript"],
            project_root=env["project_root"],
            wiki_root=env["wiki_root"],
            expected_transcript_fingerprint=stale,
        )


def _hook_script() -> Path:
    asset = files("agent_context_substrate") / "assets" / "claude_plugin" / "agent-context-substrate"
    return Path(str(asset / "hooks" / "claude_stop_finalize.py"))


def _run_hook_script(payload: dict[str, object], *, config_path: Path) -> subprocess.CompletedProcess[bytes]:
    hook_env = dict(os.environ)
    hook_env["ACS_CLAUDE_CONFIG"] = str(config_path)
    hook_env["CLAUDE_PLUGIN_ROOT"] = str(_hook_script().parents[1])
    hook_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run(
        [sys.executable, str(_hook_script())],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        env=hook_env,
        timeout=60,
        check=False,
    )


def test_hook_script_is_inert_when_stop_hook_active(env: dict[str, Path]) -> None:
    completed = _run_hook_script(_stop_payload(env["transcript"], stop_hook_active=True), config_path=env["config_path"])

    assert completed.returncode == 0
    assert completed.stdout.strip() == b""


def test_hook_script_reports_missing_config_without_blocking(env: dict[str, Path]) -> None:
    completed = _run_hook_script(_stop_payload(env["transcript"]), config_path=env["config_path"])

    assert completed.returncode == 0
    output = json.loads(completed.stdout.decode("utf-8"))
    assert output["continue"] is True
    assert "decision" not in output
    assert "configuration error" in output["systemMessage"]


def test_plugin_manifest_and_hooks_are_claude_shaped() -> None:
    root = files("agent_context_substrate") / "assets" / "claude_plugin"
    marketplace = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    plugin = json.loads((root / "agent-context-substrate" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    hooks = json.loads((root / "agent-context-substrate" / "hooks" / "hooks.json").read_text(encoding="utf-8"))

    assert marketplace["plugins"][0]["name"] == plugin["name"] == "agent-context-substrate"
    assert marketplace["plugins"][0]["source"] == "./agent-context-substrate"
    command = hooks["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/claude_stop_finalize.py" in command
