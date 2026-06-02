from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import shutil
import sys

from .codex_source import (
    codex_hook_support_status,
    codex_installed_hook_status,
    resolve_codex_home,
)
from .distribution import init_wiki, install_codex_plugin
from .paths import HarnessPaths


CODEX_PLUGIN_NAME = "agent-context-substrate"
STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_MISSING = "missing"
REQUIRED_CODEX_CHECKS = {
    "python_version",
    "package_importable",
    "project_root_exists",
    "wiki_root_exists",
    "wiki_config_exists",
    "codex_home_exists",
    "codex_plugin_installed",
    "codex_local_config_exists",
    "hook_primary_installed",
    "data_dir_writable",
}


@dataclass(frozen=True)
class CodexDoctorReport:
    ok: bool
    checks: dict[str, str]
    messages: list[str] = field(default_factory=list)
    paths: dict[str, Path] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": dict(self.checks),
            "messages": list(self.messages),
            "paths": {name: str(path) for name, path in self.paths.items()},
        }


@dataclass(frozen=True)
class CodexSetupResult:
    ok: bool
    status: str
    paths: dict[str, Path] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    doctor_report: CodexDoctorReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "paths": {name: str(path) for name, path in self.paths.items()},
            "messages": list(self.messages),
            "actions": list(self.actions),
            "doctor_report": self.doctor_report.to_dict() if self.doctor_report is not None else None,
        }


@dataclass(frozen=True)
class CodexDiagnosticReport:
    ok: bool
    issues: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    doctor_report: CodexDoctorReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": list(self.issues),
            "actions": list(self.actions),
            "doctor_report": self.doctor_report.to_dict() if self.doctor_report is not None else None,
        }


def default_windows_wiki_root() -> Path:
    return Path.home() / "Documents" / "LLM Wiki"


def _resolve_user_path(path: Path | str) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def codex_plugin_dir(codex_home: Path | str | None = None) -> Path:
    return resolve_codex_home(codex_home) / "plugins" / CODEX_PLUGIN_NAME


def codex_config_paths(*, codex_home: Path | str | None, project_root: Path | str, wiki_root: Path | str) -> dict[str, Path]:
    codex_home_path = resolve_codex_home(codex_home)
    project_root_path = _resolve_user_path(project_root)
    wiki_root_path = _resolve_user_path(wiki_root)
    return {
        "codex_home": codex_home_path,
        "codex_sqlite": codex_home_path / "state_5.sqlite",
        "codex_rollouts": codex_home_path / "sessions",
        "llm_wiki_root": wiki_root_path,
        "acs_project_root": project_root_path,
        "acs_artifacts": project_root_path / "data",
        "codex_plugin": codex_home_path / "plugins" / CODEX_PLUGIN_NAME,
        "codex_user_hook": codex_home_path / "hooks.json",
    }


def setup_codex(
    *,
    codex_home: Path | str | None = None,
    project_root: Path | str,
    wiki_root: Path | str | None = None,
    personal_marketplace_root: Path | str | None = None,
    install_user_hook: bool = True,
    install_marketplace: bool = True,
    overwrite: bool = True,
    dry_run: bool = False,
) -> CodexSetupResult:
    codex_home_path = resolve_codex_home(codex_home)
    project_root_path = _resolve_user_path(project_root)
    wiki_root_path = _resolve_user_path(wiki_root) if wiki_root is not None else _resolve_user_path(default_windows_wiki_root())
    marketplace_root = _resolve_user_path(personal_marketplace_root) if personal_marketplace_root is not None else Path.home()
    paths = codex_config_paths(codex_home=codex_home_path, project_root=project_root_path, wiki_root=wiki_root_path)
    actions = [
        f"init-wiki --wiki-root {wiki_root_path}",
        (
            "install-codex-plugin "
            f"--codex-home {codex_home_path} --project-root {project_root_path} --wiki-root {wiki_root_path}"
        ),
        f"codex-status --codex-home {codex_home_path}",
        f"doctor-codex --codex-home {codex_home_path} --project-root {project_root_path} --wiki-root {wiki_root_path}",
        "Open Codex CLI and review /hooks for agent-context-substrate Stop hook trust.",
    ]
    if dry_run:
        return CodexSetupResult(
            ok=True,
            status="dry-run",
            paths=paths,
            messages=[
                "dry run only; no files were written",
                "non-managed hook trust is not bypassed",
            ],
            actions=actions,
        )

    HarnessPaths(project_root=project_root_path).ensure_project_dirs()
    init_result = init_wiki(wiki_root_path)
    install_result = install_codex_plugin(
        codex_home=codex_home_path,
        project_root=project_root_path,
        wiki_root=wiki_root_path,
        personal_marketplace_root=marketplace_root if install_marketplace else None,
        install_user_hook=install_user_hook,
        overwrite=overwrite,
    )
    doctor_report = doctor_codex(codex_home=codex_home_path, project_root=project_root_path, wiki_root=wiki_root_path)
    return CodexSetupResult(
        ok=doctor_report.ok,
        status=install_result.status,
        paths={**paths, **install_result.paths, **init_result.paths},
        messages=[
            *init_result.messages,
            *install_result.messages,
            "Codex source SQLite: %USERPROFILE%\\.codex\\state_5.sqlite",
            "Codex rollout JSONL: %USERPROFILE%\\.codex\\sessions\\...\\rollout-*.jsonl",
            "LLM Wiki default: %USERPROFILE%\\Documents\\LLM Wiki",
            "ACS artifacts: <PROJECT_ROOT>\\data\\...",
            "Review /hooks in Codex CLI; this is separate from Full Access or approval mode.",
        ],
        actions=actions,
        doctor_report=doctor_report,
    )


def setup_codex_wizard(
    *,
    codex_home: Path | str | None = None,
    project_root: Path | str,
    wiki_root: Path | str | None = None,
    personal_marketplace_root: Path | str | None = None,
    assume_yes: bool = False,
) -> CodexSetupResult:
    codex_home_path = resolve_codex_home(codex_home)
    project_root_path = _resolve_user_path(project_root)
    wiki_root_path = _resolve_user_path(wiki_root) if wiki_root is not None else _resolve_user_path(default_windows_wiki_root())
    if not assume_yes:
        print("Agent Context Substrate will use these paths:")
        for name, path in codex_config_paths(codex_home=codex_home_path, project_root=project_root_path, wiki_root=wiki_root_path).items():
            print(f"{name}={path}")
        answer = input("Continue with setup? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            return CodexSetupResult(
                ok=False,
                status="cancelled",
                paths=codex_config_paths(codex_home=codex_home_path, project_root=project_root_path, wiki_root=wiki_root_path),
                messages=["setup cancelled by user"],
            )
    return setup_codex(
        codex_home=codex_home_path,
        project_root=project_root_path,
        wiki_root=wiki_root_path,
        personal_marketplace_root=personal_marketplace_root,
        install_user_hook=True,
        install_marketplace=True,
        overwrite=True,
    )


def doctor_codex(*, codex_home: Path | str | None = None, project_root: Path | str, wiki_root: Path | str | None = None) -> CodexDoctorReport:
    codex_home_path = resolve_codex_home(codex_home)
    project_root_path = _resolve_user_path(project_root)
    wiki_root_path = _resolve_user_path(wiki_root) if wiki_root is not None else _resolve_user_path(default_windows_wiki_root())
    paths = codex_config_paths(codex_home=codex_home_path, project_root=project_root_path, wiki_root=wiki_root_path)
    plugin_dir = paths["codex_plugin"]
    local_config_path = plugin_dir / "local_config.json"
    checks: dict[str, str] = {}

    checks["python_version"] = STATUS_OK if sys.version_info >= (3, 11) else STATUS_MISSING
    checks["package_importable"] = STATUS_OK
    checks["project_root_exists"] = _exists_status(project_root_path)
    checks["project_src_exists"] = _exists_status(project_root_path / "src" / "agent_context_substrate", warn_if_missing=True)
    checks["codex_home_exists"] = _exists_status(codex_home_path)
    checks["codex_state_sqlite_exists"] = _exists_status(paths["codex_sqlite"], warn_if_missing=True)
    checks["codex_rollout_jsonl_exists"] = STATUS_OK if list(paths["codex_rollouts"].rglob("rollout-*.jsonl")) else STATUS_WARN
    checks["wiki_root_exists"] = _exists_status(wiki_root_path)
    checks["wiki_config_exists"] = _exists_status(wiki_root_path / "_system" / "config.yaml")
    checks["codex_plugin_installed"] = _exists_status(plugin_dir / "skills" / "agent-context-substrate" / "SKILL.md")
    checks["codex_local_config_exists"] = _local_config_status(
        local_config_path=local_config_path,
        project_root=project_root_path,
        wiki_root=wiki_root_path,
        codex_home=codex_home_path,
    )
    checks["codex_user_hook_installed"] = STATUS_OK if _hooks_json_has_acs_stop_hook(codex_home_path / "hooks.json") else STATUS_WARN
    checks["hook_support"] = STATUS_OK if codex_hook_support_status(codex_home=codex_home_path) == "supported" else STATUS_WARN
    checks["hook_primary_installed"] = (
        STATUS_OK if codex_installed_hook_status(codex_home=codex_home_path) == "installed" else STATUS_MISSING
    )
    checks["watcher_fallback_available"] = STATUS_OK
    checks["data_dir_writable"] = _data_dir_writable_status(project_root_path)
    checks["git_available"] = STATUS_OK if shutil.which("git") else STATUS_WARN
    checks["codex_cli_available"] = STATUS_OK if shutil.which("codex") else STATUS_WARN
    checks["obsidian_available"] = STATUS_OK if shutil.which("obsidian") or shutil.which("Obsidian") else STATUS_WARN

    ok = all(checks.get(name) == STATUS_OK for name in REQUIRED_CODEX_CHECKS)
    return CodexDoctorReport(
        ok=ok,
        checks=checks,
        paths=paths,
        messages=_doctor_messages(checks=checks, paths=paths),
    )


def diagnose_codex(
    *,
    codex_home: Path | str | None = None,
    project_root: Path | str,
    wiki_root: Path | str | None = None,
    personal_marketplace_root: Path | str | None = None,
    fix: bool = False,
) -> CodexDiagnosticReport:
    codex_home_path = resolve_codex_home(codex_home)
    project_root_path = _resolve_user_path(project_root)
    wiki_root_path = _resolve_user_path(wiki_root) if wiki_root is not None else _resolve_user_path(default_windows_wiki_root())
    report = doctor_codex(codex_home=codex_home_path, project_root=project_root_path, wiki_root=wiki_root_path)
    issues = [
        f"{name}={status}"
        for name, status in report.checks.items()
        if status in {STATUS_MISSING, STATUS_WARN}
    ]
    actions = _diagnostic_actions(report)
    if fix and not report.ok:
        setup_codex(
            codex_home=codex_home_path,
            project_root=project_root_path,
            wiki_root=wiki_root_path,
            personal_marketplace_root=personal_marketplace_root,
            install_user_hook=True,
            install_marketplace=True,
            overwrite=True,
        )
        report = doctor_codex(codex_home=codex_home_path, project_root=project_root_path, wiki_root=wiki_root_path)
        issues = [
            f"{name}={status}"
            for name, status in report.checks.items()
            if status in {STATUS_MISSING, STATUS_WARN}
        ]
        actions = _diagnostic_actions(report)
        actions.append("review /hooks in Codex CLI; hook trust cannot be safely auto-approved")
    return CodexDiagnosticReport(ok=report.ok, issues=issues, actions=actions, doctor_report=report)


def read_codex_local_config(plugin_dir: Path | str) -> dict[str, Any]:
    config_path = Path(plugin_dir).expanduser() / "local_config.json"
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{config_path} must contain a JSON object")
    return payload


def write_codex_local_config(plugin_dir: Path | str, config: dict[str, Any]) -> dict[str, Any]:
    config_path = Path(plugin_dir).expanduser() / "local_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dict(config)


def update_codex_local_config(plugin_dir: Path | str, updates: dict[str, Any]) -> dict[str, Any]:
    config = read_codex_local_config(plugin_dir)
    config.update(updates)
    return write_codex_local_config(plugin_dir, config)


def default_codex_local_config(*, codex_home: Path | str | None, project_root: Path | str, wiki_root: Path | str | None) -> dict[str, Any]:
    codex_home_path = resolve_codex_home(codex_home)
    project_root_path = _resolve_user_path(project_root)
    wiki_root_path = _resolve_user_path(wiki_root) if wiki_root is not None else _resolve_user_path(default_windows_wiki_root())
    return {
        "project_root": str(project_root_path),
        "wiki_root": str(wiki_root_path),
        "codex_home": str(codex_home_path),
        "python_executable": sys.executable,
        "python_path_entries": [str(project_root_path / "src")],
        "hook_event_log_path": str(project_root_path / "data" / "index" / "codex_hook_events.jsonl"),
        "trigger_strategy": "hook-primary",
        "watcher_fallback": True,
        "hook_timeout_seconds": 110,
    }


def _exists_status(path: Path, *, warn_if_missing: bool = False) -> str:
    if path.exists():
        return STATUS_OK
    return STATUS_WARN if warn_if_missing else STATUS_MISSING


def _local_config_status(*, local_config_path: Path, project_root: Path, wiki_root: Path, codex_home: Path) -> str:
    if not local_config_path.exists():
        return STATUS_MISSING
    try:
        payload = json.loads(local_config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return STATUS_MISSING
    if not isinstance(payload, dict):
        return STATUS_MISSING
    expected = {
        "project_root": str(project_root),
        "wiki_root": str(wiki_root),
        "codex_home": str(codex_home),
    }
    for key, value in expected.items():
        if str(payload.get(key) or "") != value:
            return STATUS_WARN
    return STATUS_OK


def _hooks_json_has_acs_stop_hook(hooks_path: Path) -> bool:
    if not hooks_path.exists():
        return False
    try:
        payload = json.loads(hooks_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return False
    stop_groups = payload.get("hooks", {}).get("Stop", []) if isinstance(payload, dict) else []
    if not isinstance(stop_groups, list):
        return False
    for group in stop_groups:
        if not isinstance(group, dict):
            continue
        handlers = group.get("hooks")
        if not isinstance(handlers, list):
            continue
        for handler in handlers:
            if not isinstance(handler, dict):
                continue
            command_text = f"{handler.get('command', '')} {handler.get('commandWindows', '')}"
            if CODEX_PLUGIN_NAME in command_text and "codex_stop_finalize.py" in command_text:
                return True
    return False


def _data_dir_writable_status(project_root: Path) -> str:
    try:
        data_dir = project_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".acs-write-test"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
    except OSError:
        return STATUS_MISSING
    return STATUS_OK


def _doctor_messages(*, checks: dict[str, str], paths: dict[str, Path]) -> list[str]:
    _ = checks
    return [
        f"Codex source SQLite: {paths['codex_sqlite']}",
        f"Codex rollout JSONL root: {paths['codex_rollouts']}",
        f"LLM Wiki root: {paths['llm_wiki_root']}",
        f"ACS artifacts: {paths['acs_artifacts']}",
        "Hook trust: open Codex CLI and run /hooks; this is separate from Full Access.",
    ]


def _diagnostic_actions(report: CodexDoctorReport) -> list[str]:
    actions: list[str] = []
    checks = report.checks
    if checks.get("wiki_config_exists") == STATUS_MISSING:
        actions.append("run setup-codex or init-wiki to create the LLM Wiki skeleton")
    if checks.get("codex_plugin_installed") == STATUS_MISSING or checks.get("codex_local_config_exists") == STATUS_MISSING:
        actions.append("run setup-codex to reinstall the Codex plugin and local_config.json")
    if checks.get("codex_user_hook_installed") == STATUS_WARN:
        actions.append("run setup-codex with user hook enabled to register ~/.codex/hooks.json fallback")
    if checks.get("codex_state_sqlite_exists") == STATUS_WARN:
        actions.append("start Codex once so %USERPROFILE%\\.codex\\state_5.sqlite exists")
    if checks.get("codex_rollout_jsonl_exists") == STATUS_WARN:
        actions.append("run at least one Codex thread so sessions\\...\\rollout-*.jsonl exists")
    if checks.get("obsidian_available") == STATUS_WARN:
        actions.append("optional: install Obsidian and open the LLM Wiki root as a vault")
    actions.append("review /hooks in Codex CLI; hook trust cannot be safely auto-approved")
    return actions
