from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from contextlib import contextmanager
import json
import os
import re
import shutil
import sys
import tempfile

PERSONAL_PATH_PATTERNS = (
    re.compile(r"/mnt/[a-z]/Users/[^/\s'\"]+"),
    re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\s'\"]+"),
)
HUMAN_WIKI_FOLDERS = (
    "01 지식",
    "02 내 아이디어",
    "03 인물과 조직",
    "04 프로젝트",
    "05 계획",
    "06 원천 자료",
    "90 보관",
    "_system/templates/ko",
    "_system/templates/en",
    "_system/styles",
)


@dataclass(frozen=True)
class InstallResult:
    status: str
    paths: dict[str, Path] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FreshInstallSmokeResult:
    ok: bool
    artifacts: dict[str, Path] = field(default_factory=dict)
    retrieval_hit_count: int = 0
    expanded_content_length: int = 0
    lint_issue_count: int = 0
    messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DoctorReport:
    ok: bool
    checks: dict[str, bool]
    messages: list[str] = field(default_factory=list)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _asset_root():
    return files("agent_context_substrate") / "assets"


def _copy_resource_tree(source, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            _copy_resource_tree(child, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(child.read_bytes())


def _unique_backup_path(path: Path, *, backup_parent: Path | None = None) -> Path:
    if backup_parent is None:
        backup_path = path.with_name(f"{path.name}.bak-{_timestamp()}")
    else:
        backup_parent.mkdir(parents=True, exist_ok=True)
        backup_path = backup_parent / f"{path.name}.bak-{_timestamp()}"
    candidate = backup_path
    suffix = 1
    while candidate.exists():
        candidate = backup_path.with_name(f"{backup_path.name}-{suffix}")
        suffix += 1
    return candidate


def _backup_existing(path: Path, *, backup_parent: Path | None = None) -> Path | None:
    if not path.exists():
        return None
    backup_path = _unique_backup_path(path, backup_parent=backup_parent)
    shutil.copytree(path, backup_path)
    return backup_path


def _move_directory_to_backup(child: Path, backup_parent: Path) -> Path:
    backup_parent.mkdir(parents=True, exist_ok=True)
    destination = backup_parent / child.name
    if destination.exists():
        destination = backup_parent / f"{child.name}-migrated-{_timestamp()}"
    shutil.move(str(child), str(destination))
    return destination


def _move_legacy_user_plugin_backups(plugins_root: Path, plugin_name: str = "agent-context-substrate") -> None:
    backup_parent = plugins_root.parent / "_backups" / "plugins"
    for child in plugins_root.glob(f"{plugin_name}.bak-*"):
        if child.is_dir():
            _move_directory_to_backup(child, backup_parent)

    legacy_backup_namespace = plugins_root / "_backups"
    if legacy_backup_namespace.is_dir():
        for child in sorted(legacy_backup_namespace.iterdir()):
            if child.is_dir():
                _move_directory_to_backup(child, backup_parent)
        try:
            legacy_backup_namespace.rmdir()
        except OSError:
            pass


def _move_legacy_context_engine_backups(context_engine_root: Path, engine_name: str = "agent_context_substrate") -> None:
    backup_parent = context_engine_root / "_backups"
    for child in context_engine_root.glob(f"{engine_name}.bak-*"):
        if child.is_dir():
            _move_directory_to_backup(child, backup_parent)


def _contains_personal_path(path: Path) -> bool:
    if not path.exists():
        return False
    for file_path in path.rglob("*"):
        if file_path.name == "local_config.py":
            continue
        if not file_path.is_file() or file_path.suffix not in {".py", ".md", ".toml", ".yaml", ".yml", ".txt"}:
            continue
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in PERSONAL_PATH_PATTERNS):
            return True
    return False


def init_wiki(wiki_root: Path | str) -> InstallResult:
    wiki_root = Path(wiki_root).expanduser()
    for relative_path in HUMAN_WIKI_FOLDERS:
        (wiki_root / relative_path).mkdir(parents=True, exist_ok=True)

    config_path = wiki_root / "_system" / "config.yaml"
    if not config_path.exists():
        config_path.write_text(
            "\n".join(
                [
                    "wiki:",
                    "  default_language: ko",
                    "  supported_languages: [ko, en]",
                    "  filename_language: ko",
                    "  template_language: ko",
                    "  source_language_preserve: true",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    index_path = wiki_root / "index.md"
    if not index_path.exists():
        index_path.write_text(
            "\n".join(
                [
                    "---",
                    "title: Wiki Index",
                    "lang: ko",
                    "type: index",
                    "category: system",
                    "status: active",
                    "tags: [wiki, index]",
                    "---",
                    "# Wiki Index",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    log_path = wiki_root / "log.md"
    if not log_path.exists():
        log_path.write_text("# Wiki Log\n", encoding="utf-8")

    return InstallResult(
        status="initialized",
        paths={"wiki_root": wiki_root, "config_path": config_path, "index_path": index_path, "log_path": log_path},
        messages=["wiki skeleton initialized"],
    )


def _write_local_config(destination: Path, *, project_root: Path, wiki_root: Path) -> Path:
    local_config_path = destination / "local_config.py"
    local_config_path.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "",
                f"PROJECT_ROOT = Path({str(project_root)!r})",
                f"WIKI_ROOT = Path({str(wiki_root)!r})",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return local_config_path


def _write_codex_local_config(destination: Path, *, project_root: Path, wiki_root: Path, codex_home: Path) -> Path:
    local_config_path = destination / "local_config.json"
    local_config_path.write_text(
        json.dumps(
            {
                "project_root": str(project_root),
                "wiki_root": str(wiki_root),
                "codex_home": str(codex_home),
                "python_executable": sys.executable,
                "python_path_entries": [str(project_root / "src")],
                "hook_event_log_path": str(project_root / "data" / "index" / "codex_hook_events.jsonl"),
                "trigger_strategy": "hook-primary",
                "watcher_fallback": True,
                "hook_timeout_seconds": 110,
                "commands": {
                    "status": "agent-context-substrate codex-status",
                    "watch": "agent-context-substrate codex-watch",
                    "finalize": "agent-context-substrate codex-finalize",
                    "search": "agent-context-substrate search-knowledge",
                    "expand": "agent-context-substrate expand-hit",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return local_config_path


def _install_codex_personal_marketplace(
    *,
    source_plugin_dir: Path,
    marketplace_root: Path,
    codex_home: Path,
) -> dict[str, Path]:
    plugin_name = "agent-context-substrate"
    marketplace_path = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    marketplace_plugin_dir = marketplace_root / "plugins" / plugin_name
    codex_cache_plugin_parent = codex_home / "plugins" / "cache" / "personal" / plugin_name
    manifest = json.loads((source_plugin_dir / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8-sig"))
    version = manifest.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", version):
        raise ValueError("Codex plugin manifest must contain a safe version directory name")
    codex_cache_plugin_dir = codex_cache_plugin_parent / version
    if codex_cache_plugin_dir.resolve().parent != codex_cache_plugin_parent.resolve():
        raise ValueError("Codex plugin cache target must stay inside its cache parent")
    marketplace_plugin_dir.parent.mkdir(parents=True, exist_ok=True)
    if marketplace_plugin_dir.exists():
        shutil.rmtree(marketplace_plugin_dir)
    shutil.copytree(source_plugin_dir, marketplace_plugin_dir)

    if marketplace_path.exists():
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    else:
        marketplace = {"name": "personal", "interface": {"displayName": "Personal"}, "plugins": []}
    plugins = marketplace.setdefault("plugins", [])
    plugins[:] = [item for item in plugins if not (isinstance(item, dict) and item.get("name") == plugin_name)]
    plugins.append(
        {
            "name": plugin_name,
            "source": {"source": "local", "path": f"./plugins/{plugin_name}"},
            "policy": {"installation": "INSTALLED_BY_DEFAULT", "authentication": "ON_INSTALL"},
            "category": "Engineering",
        }
    )
    marketplace_path.parent.mkdir(parents=True, exist_ok=True)
    marketplace_path.write_text(json.dumps(marketplace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    codex_cache_plugin_parent.mkdir(parents=True, exist_ok=True)
    cache_backup_parent = codex_home / "_backups" / "plugins" / "cache" / "personal" / plugin_name
    cache_backup_parent.mkdir(parents=True, exist_ok=True)
    cache_backup_path = None
    with tempfile.TemporaryDirectory(prefix="acs-cache-", dir=cache_backup_parent) as staging_dir:
        staged_plugin = Path(staging_dir) / version
        shutil.copytree(source_plugin_dir, staged_plugin)
        if codex_cache_plugin_dir.exists():
            cache_backup_path = _unique_backup_path(codex_cache_plugin_dir, backup_parent=cache_backup_parent)
            codex_cache_plugin_dir.rename(cache_backup_path)
        try:
            staged_plugin.rename(codex_cache_plugin_dir)
        except OSError:
            if cache_backup_path is not None:
                cache_backup_path.rename(codex_cache_plugin_dir)
            raise

    paths = {
        "personal_marketplace_path": marketplace_path,
        "personal_marketplace_plugin_dir": marketplace_plugin_dir,
        "codex_plugin_cache_dir": codex_cache_plugin_dir,
    }
    if cache_backup_path is not None:
        paths["codex_plugin_cache_backup_path"] = cache_backup_path
    return paths


def _codex_user_stop_hook_group(*, plugin_dir: Path) -> dict[str, object]:
    hook_script = plugin_dir / "hooks" / "codex_stop_finalize.py"
    return {
        "hooks": [
            {
                "type": "command",
                "command": f'python3 "{hook_script.as_posix()}"',
                "commandWindows": f'python "{hook_script}"',
                "timeout": 120,
                "statusMessage": "Finalizing Codex thread into Agent Context Substrate",
            }
        ]
    }


def _is_acs_codex_stop_hook_handler(handler: object) -> bool:
    if not isinstance(handler, dict):
        return False
    command = str(handler.get("command") or "")
    command_windows = str(handler.get("commandWindows") or handler.get("command_windows") or "")
    command_text = f"{command} {command_windows}"
    return "agent-context-substrate" in command_text and "codex_stop_finalize.py" in command_text


_CODEX_HOOK_SCRIPT_PATTERN = re.compile(
    r'''"(?P<double>[^"\n]*codex_stop_finalize\.py)"|'''
    r"'(?P<single>[^'\n]*codex_stop_finalize\.py)'|"
    r'''(?P<bare>[^\s"'()]+codex_stop_finalize\.py)(?=$|[\s"'();])'''
)
_CODEX_COMMAND_FIELDS = ("command", "commandWindows", "command_windows")


def _codex_hook_targets_current_script(handler: dict[str, object], *, hook_script: Path) -> bool:
    expected = hook_script.resolve()
    for command_field in _CODEX_COMMAND_FIELDS:
        command = handler.get(command_field)
        if not command:
            continue
        matches = list(_CODEX_HOOK_SCRIPT_PATTERN.finditer(str(command)))
        if not matches or any(Path(match.group(match.lastgroup)).expanduser().resolve() != expected for match in matches):
            return False
    return True


def _repair_codex_hook_script_paths(handler: dict[str, object], *, hook_script: Path) -> dict[str, object]:
    repaired = dict(handler)
    for command_field in _CODEX_COMMAND_FIELDS:
        command = handler.get(command_field)
        if not command:
            continue
        command = str(command)
        target = hook_script.as_posix() if command_field == "command" else str(hook_script)
        matches = list(_CODEX_HOOK_SCRIPT_PATTERN.finditer(command))
        if not matches:
            raise ValueError("Cannot safely repair ACS user hook script path; review its command manually")
        for match in reversed(matches):
            if match.lastgroup == "bare" and re.search(r'''[\s&;|<>^%$`"'()\[\]{}*?!#,]''', target):
                raise ValueError("Cannot safely repair bare ACS user hook path; quote its script path before reinstall")
            start, end = match.span(match.lastgroup)
            command = command[:start] + target + command[end:]
        repaired[command_field] = command
    return repaired


def _install_codex_user_stop_hook(*, codex_home: Path, plugin_dir: Path, enabled: bool = True) -> Path | None:
    hooks_path = codex_home / "hooks.json"
    if hooks_path.exists():
        payload = json.loads(hooks_path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError(f"{hooks_path} must contain a JSON object")
    else:
        if not enabled:
            return None
        payload = {}

    hooks = payload.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"{hooks_path} field 'hooks' must be an object")
    if not enabled and "Stop" not in hooks:
        return None
    stop_groups = hooks.setdefault("Stop", [])
    if not isinstance(stop_groups, list):
        raise ValueError(f"{hooks_path} field 'hooks.Stop' must be an array")

    retained_acs_handler = False
    changed = False
    expected_group = _codex_user_stop_hook_group(plugin_dir=plugin_dir)
    hook_script = plugin_dir / "hooks" / "codex_stop_finalize.py"
    candidates = [
        (group_index, handler_index, handler)
        for group_index, group in enumerate(stop_groups)
        if isinstance(group, dict) and isinstance(group.get("hooks"), list)
        for handler_index, handler in enumerate(group["hooks"])
        if _is_acs_codex_stop_hook_handler(handler)
    ]
    selected = None
    if enabled:
        selected = next(
            (candidate for candidate in candidates
             if _codex_hook_targets_current_script(candidate[2], hook_script=hook_script)),
            candidates[0] if candidates else None,
        )
    for group_index, group in enumerate(stop_groups):
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            continue
        handlers = []
        for handler_index, handler in enumerate(group["hooks"]):
            if _is_acs_codex_stop_hook_handler(handler):
                if selected is None or (group_index, handler_index) != selected[:2]:
                    changed = True
                    continue
                retained_acs_handler = True
                if not _codex_hook_targets_current_script(handler, hook_script=hook_script):
                    handler = _repair_codex_hook_script_paths(handler, hook_script=hook_script)
                    changed = True
            handlers.append(handler)
        group["hooks"] = handlers
    if enabled and not retained_acs_handler:
        stop_groups.append(expected_group)
        changed = True
    if not changed:
        return hooks_path if enabled else None
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    hooks_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return hooks_path


def install_user_plugin(
    *,
    hermes_home: Path | str,
    project_root: Path | str,
    wiki_root: Path | str,
    overwrite: bool = False,
) -> InstallResult:
    hermes_home = Path(hermes_home).expanduser()
    project_root = Path(project_root).expanduser()
    wiki_root = Path(wiki_root).expanduser()
    plugin_dir = hermes_home / "plugins" / "agent-context-substrate"
    plugins_root = plugin_dir.parent
    if plugin_dir.exists() and not overwrite:
        return InstallResult(
            status="skipped",
            paths={"plugin_dir": plugin_dir},
            messages=["plugin already exists; pass overwrite=True to replace it"],
        )

    _move_legacy_user_plugin_backups(plugins_root)
    backup_path = _backup_existing(plugin_dir, backup_parent=hermes_home / "_backups" / "plugins") if overwrite else None
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)
    _copy_resource_tree(_asset_root() / "user_plugin" / "agent_context_substrate", plugin_dir)
    local_config_path = _write_local_config(plugin_dir, project_root=project_root, wiki_root=wiki_root)

    paths = {"plugin_dir": plugin_dir, "local_config_path": local_config_path}
    if backup_path:
        paths["backup_path"] = backup_path
    return InstallResult(status="installed", paths=paths, messages=["user plugin installed"])


def install_codex_plugin(
    *,
    codex_home: Path | str,
    project_root: Path | str,
    wiki_root: Path | str,
    personal_marketplace_root: Path | str | None = None,
    install_user_hook: bool = False,
    overwrite: bool = False,
) -> InstallResult:
    codex_home = Path(codex_home).expanduser()
    project_root = Path(project_root).expanduser()
    wiki_root = Path(wiki_root).expanduser()
    plugin_dir = codex_home / "plugins" / "agent-context-substrate"
    personal_cache = codex_home / "plugins" / "cache" / "personal" / "agent-context-substrate"
    if personal_marketplace_root is None and personal_cache.exists():
        raise ValueError("Existing ACS personal cache requires an explicit --personal-marketplace-root before reinstall")
    if plugin_dir.exists() and not overwrite:
        return InstallResult(
            status="skipped",
            paths={"plugin_dir": plugin_dir},
            messages=["codex plugin already exists; pass overwrite=True to replace it"],
        )

    backup_path = _backup_existing(plugin_dir, backup_parent=codex_home / "_backups" / "plugins") if overwrite else None
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)
    _copy_resource_tree(_asset_root() / "codex_plugin" / "agent-context-substrate", plugin_dir)
    local_config_path = _write_codex_local_config(
        plugin_dir,
        project_root=project_root,
        wiki_root=wiki_root,
        codex_home=codex_home,
    )
    if install_user_hook:
        (plugin_dir / "hooks" / "hooks.json").write_text('{"hooks": {}}\n', encoding="utf-8")

    paths = {"plugin_dir": plugin_dir, "local_config_path": local_config_path}
    if backup_path:
        paths["backup_path"] = backup_path
    if personal_marketplace_root is not None:
        paths.update(
            _install_codex_personal_marketplace(
                source_plugin_dir=plugin_dir,
                marketplace_root=Path(personal_marketplace_root).expanduser(),
                codex_home=codex_home,
            )
        )
        messages = [
            "codex plugin installed; Stop hook is primary and codex-watch remains fallback",
            "personal marketplace entry and Codex plugin cache installed",
        ]
    else:
        messages = ["codex plugin installed; Stop hook is primary and codex-watch remains fallback"]
    user_hooks_path = _install_codex_user_stop_hook(
        codex_home=codex_home, plugin_dir=plugin_dir, enabled=install_user_hook
    )
    if user_hooks_path is not None:
        paths["codex_user_hooks_path"] = user_hooks_path
    if install_user_hook:
        messages.append("Codex user Stop hook selected; installed bundled hooks are disabled")
    else:
        messages.append("Bundled Codex Stop hook selected; matching ACS user handlers are removed")
    return InstallResult(
        status="installed",
        paths=paths,
        messages=messages,
    )


def install_context_engine(
    *,
    hermes_agent_root: Path | str,
    project_root: Path | str | None = None,
    wiki_root: Path | str | None = None,
    overwrite: bool = False,
) -> InstallResult:
    hermes_agent_root = Path(hermes_agent_root).expanduser()
    project_root_path = Path(project_root).expanduser() if project_root is not None else None
    wiki_root_path = Path(wiki_root).expanduser() if wiki_root is not None else None
    context_engine_root = hermes_agent_root / "plugins" / "context_engine"
    engine_dir = context_engine_root / "agent_context_substrate"
    if engine_dir.exists() and not overwrite:
        return InstallResult(
            status="skipped",
            paths={"engine_dir": engine_dir},
            messages=["context engine already exists; pass overwrite=True to replace it"],
        )

    _move_legacy_context_engine_backups(context_engine_root)
    backup_path = _backup_existing(engine_dir, backup_parent=context_engine_root / "_backups") if overwrite else None
    if engine_dir.exists():
        shutil.rmtree(engine_dir)
    _copy_resource_tree(_asset_root() / "context_engine" / "agent_context_substrate", engine_dir)

    paths = {"engine_dir": engine_dir}
    if project_root_path is not None and wiki_root_path is not None:
        paths["local_config_path"] = _write_local_config(
            engine_dir,
            project_root=project_root_path,
            wiki_root=wiki_root_path,
        )
    if backup_path:
        paths["backup_path"] = backup_path
    return InstallResult(status="installed", paths=paths, messages=["context engine installed"])


@contextmanager
def _temporary_env(**updates: str):
    old_values = {key: os.environ.get(key) for key in updates}
    for key, value in updates.items():
        os.environ[key] = value
    try:
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _ensure_project_import_shim(project_root: Path) -> None:
    package_dir = Path(__file__).resolve().parent
    target = project_root / "src" / "agent_context_substrate"
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(package_dir, target_is_directory=True)
    except OSError:
        shutil.copytree(package_dir, target)


def run_fresh_install_smoke(
    *,
    session_id: str,
    hermes_home: Path | str,
    project_root: Path | str,
    wiki_root: Path | str,
    hermes_agent_root: Path | str | None = None,
) -> FreshInstallSmokeResult:
    from .integration import _lint_issue_count, run_session_finalize_pipeline
    from .lint import lint_wiki
    from .paths import HarnessPaths
    from .retrieval import expand_hit, search_knowledge

    hermes_home = Path(hermes_home).expanduser()
    project_root = Path(project_root).expanduser()
    wiki_root = Path(wiki_root).expanduser()
    hermes_agent_root_path = Path(hermes_agent_root).expanduser() if hermes_agent_root else None

    init_wiki(wiki_root)
    _ensure_project_import_shim(project_root)
    install_user_plugin(hermes_home=hermes_home, project_root=project_root, wiki_root=wiki_root, overwrite=True)
    if hermes_agent_root_path is not None:
        install_context_engine(
            hermes_agent_root=hermes_agent_root_path,
            project_root=project_root,
            wiki_root=wiki_root,
            overwrite=True,
        )

    with _temporary_env(HERMES_HOME=str(hermes_home), WIKI_PATH=str(wiki_root)):
        integration_result = run_session_finalize_pipeline(
            session_id=session_id,
            project_root=project_root,
            wiki_root=wiki_root,
            promotion_mode="packet-only",
        )
        hits = search_knowledge(
            integration_result.packet_id,
            project_root=project_root,
            wiki_root=wiki_root,
            limit=5,
        )
        if not hits:
            hits = search_knowledge(
                session_id,
                project_root=project_root,
                wiki_root=wiki_root,
                limit=5,
                include_raw=True,
            )
        expanded_content_length = 0
        if hits:
            detail = expand_hit(hits[0].hit_id, project_root=project_root, wiki_root=wiki_root)
            expanded_content_length = len(detail.content)
        lint_report = lint_wiki(HarnessPaths(project_root=project_root))
        lint_issue_count = _lint_issue_count(lint_report)

    artifacts = {
        "raw_export_path": integration_result.raw_export_path,
        "packet_json_path": integration_result.packet_json_path,
        "packet_markdown_path": integration_result.packet_markdown_path,
        "lint_json_path": integration_result.lint_json_path,
        "lint_markdown_path": integration_result.lint_markdown_path,
        "recovery_json_path": integration_result.recovery_json_path,
    }
    ok = (
        all(path.exists() for path in artifacts.values())
        and len(hits) > 0
        and expanded_content_length > 0
        and lint_issue_count == 0
    )
    return FreshInstallSmokeResult(
        ok=ok,
        artifacts=artifacts,
        retrieval_hit_count=len(hits),
        expanded_content_length=expanded_content_length,
        lint_issue_count=lint_issue_count,
        messages=["fresh install smoke completed"],
    )


def doctor(
    *,
    hermes_home: Path | str,
    project_root: Path | str,
    wiki_root: Path | str,
    hermes_agent_root: Path | str,
) -> DoctorReport:
    hermes_home = Path(hermes_home).expanduser()
    project_root = Path(project_root).expanduser()
    wiki_root = Path(wiki_root).expanduser()
    hermes_agent_root = Path(hermes_agent_root).expanduser()
    plugin_dir = hermes_home / "plugins" / "agent-context-substrate"
    engine_dir = hermes_agent_root / "plugins" / "context_engine" / "agent_context_substrate"

    checks = {
        "package_importable": True,
        "project_root_exists": project_root.exists(),
        "project_src_exists": (project_root / "src" / "agent_context_substrate").exists(),
        "hermes_home_exists": hermes_home.exists(),
        "state_db_exists": (hermes_home / "state.db").exists(),
        "wiki_root_exists": wiki_root.exists(),
        "wiki_config_exists": (wiki_root / "_system" / "config.yaml").exists(),
        "user_plugin_installed": (plugin_dir / "plugin.yaml").exists() and (plugin_dir / "runtime.py").exists(),
        "context_engine_installed": (engine_dir / "plugin.yaml").exists() and (engine_dir / "engine.py").exists(),
        "installed_templates_are_generic": not _contains_personal_path(plugin_dir) and not _contains_personal_path(engine_dir),
    }
    messages = [f"{name}: {'ok' if ok else 'missing'}" for name, ok in checks.items()]
    return DoctorReport(ok=all(checks.values()), checks=checks, messages=messages)
