from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os
import shutil


STATUS_OK = "ok"
STATUS_WARN = "warn"


@dataclass(frozen=True)
class CodexCliDetection:
    status: str
    path_kind: str
    path_codex: Path | None = None
    path_codex_candidates: list[Path] = field(default_factory=list)
    standalone_cli_path: Path | None = None
    direct_app_cli_path: Path | None = None
    app_cli_path: Path | None = None
    versioned_app_cli_candidates: list[Path] = field(default_factory=list)
    windows_apps_candidates: list[Path] = field(default_factory=list)
    recommended_path: Path | None = None
    npm_precedes_openai_cli: bool = False
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "path_kind": self.path_kind,
            "path_codex": str(self.path_codex) if self.path_codex is not None else None,
            "path_codex_candidates": [str(path) for path in self.path_codex_candidates],
            "standalone_cli_path": str(self.standalone_cli_path) if self.standalone_cli_path is not None else None,
            "direct_app_cli_path": str(self.direct_app_cli_path) if self.direct_app_cli_path is not None else None,
            "app_cli_path": str(self.app_cli_path) if self.app_cli_path is not None else None,
            "versioned_app_cli_candidates": [str(path) for path in self.versioned_app_cli_candidates],
            "windows_apps_candidates": [str(path) for path in self.windows_apps_candidates],
            "recommended_path": str(self.recommended_path) if self.recommended_path is not None else None,
            "npm_precedes_openai_cli": self.npm_precedes_openai_cli,
            "messages": list(self.messages),
        }


def detect_codex_cli(
    *,
    path_entries: list[Path | str] | None = None,
    local_app_data: Path | str | None = None,
    windows_apps: Path | str | None = None,
) -> CodexCliDetection:
    local_app_data_path = Path(local_app_data).expanduser() if local_app_data is not None else default_local_app_data()
    windows_apps_path = Path(windows_apps).expanduser() if windows_apps is not None else default_windows_apps_dir()
    path_codex_candidates = _find_all_codex_on_path(path_entries=path_entries)
    path_codex = path_codex_candidates[0] if path_codex_candidates else None
    standalone_cli_path = _standalone_codex_cli_candidate(local_app_data=local_app_data_path)
    direct_app_cli_path = _direct_codex_app_cli_candidate(local_app_data=local_app_data_path)
    versioned_app_cli_candidates = _versioned_codex_app_cli_candidates(local_app_data=local_app_data_path)
    windows_apps_candidates = _windows_apps_codex_cli_candidates(windows_apps=windows_apps_path)
    app_cli_path = _preferred_codex_app_cli_candidate(
        standalone_cli_path=standalone_cli_path,
        direct_app_cli_path=direct_app_cli_path,
        versioned_app_cli_candidates=versioned_app_cli_candidates,
        windows_apps_candidates=windows_apps_candidates,
    )
    path_kind = classify_codex_cli_path(
        path_codex,
        local_app_data=local_app_data_path,
        windows_apps=windows_apps_path,
    )
    npm_precedes_openai_cli = _npm_precedes_openai_cli(
        path_codex_candidates,
        local_app_data=local_app_data_path,
        windows_apps=windows_apps_path,
    )
    messages = _detection_messages(
        path_codex=path_codex,
        path_codex_candidates=path_codex_candidates,
        standalone_cli_path=standalone_cli_path,
        direct_app_cli_path=direct_app_cli_path,
        app_cli_path=app_cli_path,
        versioned_app_cli_candidates=versioned_app_cli_candidates,
        windows_apps_candidates=windows_apps_candidates,
        path_kind=path_kind,
        npm_precedes_openai_cli=npm_precedes_openai_cli,
    )
    recommended_path = app_cli_path
    status = STATUS_OK
    if recommended_path is None and path_codex is not None and path_kind != "npm-shim":
        recommended_path = path_codex
    if recommended_path is None:
        status = STATUS_WARN
    return CodexCliDetection(
        status=status,
        path_kind=path_kind,
        path_codex=path_codex,
        path_codex_candidates=path_codex_candidates,
        standalone_cli_path=standalone_cli_path,
        direct_app_cli_path=direct_app_cli_path,
        app_cli_path=app_cli_path,
        versioned_app_cli_candidates=versioned_app_cli_candidates,
        windows_apps_candidates=windows_apps_candidates,
        recommended_path=recommended_path,
        npm_precedes_openai_cli=npm_precedes_openai_cli,
        messages=messages,
    )


def resolve_codex_command(configured: str | None = None) -> str | None:
    configured_command = str(configured or "").strip()
    if configured_command:
        if codex_command_available(configured_command):
            return configured_command
        if _is_rotating_codex_app_command(configured_command):
            detection = detect_codex_cli()
            if detection.recommended_path is not None:
                return str(detection.recommended_path)
        return None

    environment_command = str(os.environ.get("AGENT_CONTEXT_SUBSTRATE_CODEX_CLI") or "").strip()
    if environment_command:
        return environment_command if codex_command_available(environment_command) else None
    detection = detect_codex_cli()
    return str(detection.recommended_path) if detection.recommended_path is not None else None


def codex_command_available(command: str) -> bool:
    command_path = Path(command).expanduser()
    if command_path.is_absolute() or command_path.parent != Path("."):
        return command_path.exists()
    return shutil.which(command) is not None


def default_local_app_data() -> Path | None:
    value = os.environ.get("LOCALAPPDATA")
    return Path(value).expanduser() if value else None


def default_windows_apps_dir() -> Path | None:
    local_app_data = default_local_app_data()
    return local_app_data / "Microsoft" / "WindowsApps" if local_app_data is not None else None


def _is_rotating_codex_app_command(command: str) -> bool:
    command_path = Path(command).expanduser()
    if not command_path.is_absolute() and command_path.parent == Path("."):
        return False
    path_kind = classify_codex_cli_path(
        command_path,
        local_app_data=default_local_app_data(),
        windows_apps=default_windows_apps_dir(),
    )
    return path_kind in {"versioned-app-cli", "windowsapps-app-bundle"}


def classify_codex_cli_path(path: Path | None, *, local_app_data: Path | None, windows_apps: Path | None) -> str:
    if path is None:
        return "missing"
    normalized = path.as_posix().lower()
    if "/appdata/roaming/npm/" in normalized or normalized.endswith(("/npm/codex.ps1", "/npm/codex.cmd")):
        return "npm-shim"
    if local_app_data is not None:
        try:
            relative = path.resolve(strict=False).relative_to(local_app_data.resolve(strict=False))
        except ValueError:
            relative = None
        if relative is not None:
            relative_text = relative.as_posix().lower()
            if relative_text == "programs/openai/codex/bin/codex.exe":
                return "standalone-cli"
            if relative_text == "openai/codex/bin/codex.exe":
                return "direct-app-cli"
            if relative_text.startswith("openai/codex/bin/") and path.name.lower() == "codex.exe":
                return "versioned-app-cli"
            if relative_text.startswith("microsoft/windowsapps/openai.codex_") and path.name.lower() == "codex.exe":
                return "windowsapps-app-bundle"
    if windows_apps is not None:
        try:
            path.resolve(strict=False).relative_to(windows_apps.resolve(strict=False))
        except ValueError:
            pass
        else:
            return "windowsapps-app-bundle"
    return "other"


def _find_all_codex_on_path(*, path_entries: list[Path | str] | None = None) -> list[Path]:
    entries = path_entries
    if entries is None:
        entries = [Path(entry) for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
    candidate_names = ["codex.exe", "codex.cmd", "codex.bat", "codex.ps1", "codex"]
    candidates: list[Path] = []
    for entry in entries:
        directory = Path(entry).expanduser()
        for name in candidate_names:
            candidate = directory / name
            if candidate.exists():
                candidates.append(candidate)
                break
    return candidates


def _standalone_codex_cli_candidate(*, local_app_data: Path | None) -> Path | None:
    candidate = local_app_data / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe" if local_app_data else None
    return candidate if candidate is not None and candidate.exists() else None


def _direct_codex_app_cli_candidate(*, local_app_data: Path | None) -> Path | None:
    candidate = local_app_data / "OpenAI" / "Codex" / "bin" / "codex.exe" if local_app_data else None
    return candidate if candidate is not None and candidate.exists() else None


def _versioned_codex_app_cli_candidates(*, local_app_data: Path | None) -> list[Path]:
    if local_app_data is None:
        return []
    codex_bin = local_app_data / "OpenAI" / "Codex" / "bin"
    candidates = [path for path in codex_bin.glob("*/codex.exe") if path.exists()]
    return sorted(candidates, key=_codex_candidate_sort_key, reverse=True)


def _windows_apps_codex_cli_candidates(*, windows_apps: Path | None) -> list[Path]:
    if windows_apps is None:
        return []
    candidates = [path for path in sorted(windows_apps.glob("OpenAI.Codex_*/codex.exe")) if path.exists()]
    generic_candidate = windows_apps / "codex.exe"
    if generic_candidate.exists():
        candidates.append(generic_candidate)
    return candidates


def _codex_candidate_sort_key(path: Path) -> tuple[float, str]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (mtime, path.as_posix().lower())


def _preferred_codex_app_cli_candidate(
    *,
    standalone_cli_path: Path | None,
    direct_app_cli_path: Path | None,
    versioned_app_cli_candidates: list[Path],
    windows_apps_candidates: list[Path],
) -> Path | None:
    candidates = [
        *([standalone_cli_path] if standalone_cli_path is not None else []),
        *versioned_app_cli_candidates,
        *([direct_app_cli_path] if direct_app_cli_path is not None else []),
        *windows_apps_candidates,
    ]
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _npm_precedes_openai_cli(paths: list[Path], *, local_app_data: Path | None, windows_apps: Path | None) -> bool:
    npm_index: int | None = None
    openai_index: int | None = None
    direct_kinds = {"standalone-cli", "direct-app-cli", "versioned-app-cli", "windowsapps-app-bundle"}
    for index, path in enumerate(paths):
        path_kind = classify_codex_cli_path(path, local_app_data=local_app_data, windows_apps=windows_apps)
        if path_kind == "npm-shim" and npm_index is None:
            npm_index = index
        if path_kind in direct_kinds and openai_index is None:
            openai_index = index
    return npm_index is not None and openai_index is not None and npm_index < openai_index


def _detection_messages(
    *,
    path_codex: Path | None,
    path_codex_candidates: list[Path],
    standalone_cli_path: Path | None,
    direct_app_cli_path: Path | None,
    app_cli_path: Path | None,
    versioned_app_cli_candidates: list[Path],
    windows_apps_candidates: list[Path],
    path_kind: str,
    npm_precedes_openai_cli: bool,
) -> list[str]:
    messages = [f"Codex CLI on PATH: {path_codex}" if path_codex else "Codex CLI was not found on PATH."]
    if path_codex_candidates:
        messages.append("All PATH codex candidates: " + "; ".join(str(path) for path in path_codex_candidates))
    messages.append(
        f"Codex standalone CLI candidate: {standalone_cli_path}"
        if standalone_cli_path
        else "Codex standalone CLI candidate was not found under LOCALAPPDATA Programs OpenAI Codex paths."
    )
    messages.append(
        f"Codex direct app CLI candidate: {direct_app_cli_path}"
        if direct_app_cli_path
        else "Codex direct app CLI candidate was not found under LOCALAPPDATA OpenAI Codex paths."
    )
    messages.append(
        f"Codex recommended direct CLI candidate: {app_cli_path}"
        if app_cli_path
        else "Codex app CLI candidate was not found under LOCALAPPDATA OpenAI Codex paths."
    )
    if versioned_app_cli_candidates:
        messages.append("Versioned Codex app CLI candidates: " + "; ".join(map(str, versioned_app_cli_candidates)))
    else:
        messages.append("Versioned Codex app CLI candidates were not found under LOCALAPPDATA OpenAI Codex bin subdirectories.")
    if windows_apps_candidates:
        messages.append("WindowsApps Codex CLI candidates: " + "; ".join(map(str, windows_apps_candidates)))
    if path_kind == "npm-shim":
        messages.append("PATH codex appears to be an npm shim; prefer the Codex app CLI direct path for Windows hook review.")
    elif path_kind in {"standalone-cli", "direct-app-cli", "versioned-app-cli", "windowsapps-app-bundle"}:
        messages.append(f"PATH codex appears to be a direct Codex CLI ({path_kind}).")
    elif path_kind == "other":
        messages.append("PATH codex does not look like the Windows Codex app CLI; verify it can open Codex /hooks.")
    if npm_precedes_openai_cli:
        messages.append("An npm/global shim appears before a direct OpenAI Codex CLI on PATH.")
    return messages
