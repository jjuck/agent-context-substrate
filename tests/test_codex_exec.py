import json
from pathlib import Path
import subprocess

from agent_context_substrate.codex_exec import CodexExecRuntime


def test_codex_exec_runtime_owns_isolated_structured_execution(tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command: list[str], **kwargs):
        calls.append((command, kwargs))
        schema_path = Path(command[command.index("--output-schema") + 1])
        assert json.loads(schema_path.read_text(encoding="utf-8"))["required"] == ["decision"]
        stdout = json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": json.dumps({"decision": "approved"})},
            }
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    runtime = CodexExecRuntime(
        codex_command=str(tmp_path / "codex.exe"),
        project_root=tmp_path,
        timeout_seconds=17,
        model="gpt-test",
        runner=runner,
    )

    payload = runtime.run_structured(
        prompt="Return a decision.",
        schema={"type": "object", "required": ["decision"]},
        schema_filename="decision-schema.json",
        error_label="decision worker",
    )

    command, kwargs = calls[0]
    assert payload == {"decision": "approved"}
    assert command[:2] == [str(tmp_path / "codex.exe"), "exec"]
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert "approval_policy=never" in command
    assert "service_tier=fast" in command
    assert "model_reasoning_effort=low" in command
    assert "features.hooks=false" in command
    assert command[-3:-1] == ["--model", "gpt-test"]
    assert command[-1] == "Return a decision."
    assert kwargs["timeout"] == 17
    assert kwargs["shell"] is False
    assert kwargs["env"]["AGENT_CONTEXT_SUBSTRATE_CODEX_WORKER"] == "1"


def test_codex_exec_runtime_reports_nonzero_exit_with_worker_label(tmp_path: Path) -> None:
    def runner(command: list[str], **_kwargs):
        return subprocess.CompletedProcess(command, 9, stdout="", stderr="not logged in")

    runtime = CodexExecRuntime(
        codex_command=str(tmp_path / "codex.exe"),
        project_root=tmp_path,
        runner=runner,
    )

    try:
        runtime.run_structured(
            prompt="Return JSON.",
            schema={"type": "object"},
            schema_filename="schema.json",
            error_label="summary worker",
        )
    except RuntimeError as exc:
        assert str(exc) == "summary worker failed with exit_code=9: not logged in"
    else:
        raise AssertionError("Expected CodexExecRuntime to raise RuntimeError")
