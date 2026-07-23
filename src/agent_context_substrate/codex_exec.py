from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import subprocess

from .codex_cli import resolve_codex_command


CodexRunner = Callable[..., subprocess.CompletedProcess[str]]


class CodexExecRuntime:
    """Run isolated Codex workers behind one structured execution interface."""

    def __init__(
        self,
        *,
        codex_command: str | None = None,
        project_root: Path | str,
        timeout_seconds: int = 90,
        model: str | None = None,
        runner: CodexRunner | None = None,
    ) -> None:
        self.codex_command = codex_command
        self.project_root = Path(project_root).expanduser()
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.model = model
        self.runner = runner or subprocess.run

    def run_structured(
        self,
        *,
        prompt: str,
        schema: dict[str, object],
        schema_filename: str,
        error_label: str,
    ) -> dict[str, object]:
        self.project_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".acs-codex-worker-", dir=self.project_root) as temp_dir:
            schema_path = Path(temp_dir) / Path(schema_filename).name
            schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
            result = self._run(
                prompt=prompt,
                schema_path=schema_path,
                error_label=error_label,
                timeout_seconds=self.timeout_seconds,
            )
        return parse_codex_exec_json_payload(result.stdout, error_label=error_label)

    def run_text(self, *, prompt: str, error_label: str, timeout_seconds: int | None = None) -> str:
        result = self._run(
            prompt=prompt,
            schema_path=None,
            error_label=error_label,
            timeout_seconds=timeout_seconds or self.timeout_seconds,
        )
        return result.stdout

    def build_command(self, *, prompt: str, schema_path: Path | None = None) -> list[str]:
        command = [
            self._command_for_execution(),
            "exec",
            "--ephemeral",
            "--ignore-rules",
            "--ignore-user-config",
            "-C",
            str(self.project_root),
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "-c",
            "approval_policy=never",
            "-c",
            "service_tier=fast",
            "-c",
            "model_reasoning_effort=low",
            "-c",
            "features.hooks=false",
        ]
        if schema_path is not None:
            command.extend(["--json", "--output-schema", str(schema_path)])
        if self.model:
            command.extend(["--model", self.model])
        command.append(prompt)
        return command

    def _run(
        self,
        *,
        prompt: str,
        schema_path: Path | None,
        error_label: str,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        command = self.build_command(prompt=prompt, schema_path=schema_path)
        result = self.runner(
            command,
            cwd=str(self.project_root),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
            env=codex_exec_environment(),
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"{error_label} failed with exit_code={result.returncode}: {detail}")
        return result

    def _command_for_execution(self) -> str:
        command = resolve_codex_command(self.codex_command)
        if command:
            return command
        raise RuntimeError("codex worker unavailable: codex command was not found")


def codex_exec_environment() -> dict[str, str]:
    env = dict(os.environ)
    env["AGENT_CONTEXT_SUBSTRATE_CODEX_WORKER"] = "1"
    env["AGENT_CONTEXT_SUBSTRATE_CODEX_SUMMARY"] = "1"
    return env


def parse_codex_exec_json_payload(stdout: str, *, error_label: str) -> dict[str, object]:
    stripped = stdout.strip()
    if not stripped:
        raise ValueError(f"{error_label} returned empty stdout")
    try:
        direct_payload = _parse_json_text_object(stripped)
    except (ValueError, json.JSONDecodeError):
        direct_payload = None
    if direct_payload is not None and not _looks_like_codex_event(direct_payload):
        return direct_payload

    last_agent_text: str | None = None
    for line in stripped.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            last_agent_text = str(item["text"])
            continue
        if event.get("type") == "agent_message" and isinstance(event.get("text"), str):
            last_agent_text = str(event["text"])
    if last_agent_text is None:
        raise ValueError(f"{error_label} JSONL output did not include an agent_message item")
    return _parse_json_text_object(last_agent_text)


def _looks_like_codex_event(payload: dict[str, object]) -> bool:
    event_type = str(payload.get("type") or "")
    return event_type in {"thread.started", "turn.started", "turn.completed", "item.started", "item.completed"}


def _parse_json_text_object(text: str) -> dict[str, object]:
    parsed = json.loads(_strip_json_fence(text))
    if not isinstance(parsed, dict):
        raise ValueError("codex worker must return a JSON object")
    return parsed


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
