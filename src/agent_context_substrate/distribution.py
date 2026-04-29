from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from contextlib import contextmanager
import os
import re
import shutil

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


def _backup_existing(path: Path, *, backup_parent: Path | None = None) -> Path | None:
    if not path.exists():
        return None
    if backup_parent is None:
        backup_path = path.with_name(f"{path.name}.bak-{_timestamp()}")
    else:
        backup_parent.mkdir(parents=True, exist_ok=True)
        backup_path = backup_parent / f"{path.name}.bak-{_timestamp()}"
    shutil.copytree(path, backup_path)
    return backup_path


def _move_legacy_context_engine_backups(context_engine_root: Path, engine_name: str = "agent_context_substrate") -> None:
    backup_parent = context_engine_root / "_backups"
    for child in context_engine_root.glob(f"{engine_name}.bak-*"):
        if not child.is_dir():
            continue
        backup_parent.mkdir(parents=True, exist_ok=True)
        destination = backup_parent / child.name
        if destination.exists():
            destination = backup_parent / f"{child.name}-migrated-{_timestamp()}"
        shutil.move(str(child), str(destination))


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
    if plugin_dir.exists() and not overwrite:
        return InstallResult(
            status="skipped",
            paths={"plugin_dir": plugin_dir},
            messages=["plugin already exists; pass overwrite=True to replace it"],
        )

    backup_path = _backup_existing(plugin_dir) if overwrite else None
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)
    _copy_resource_tree(_asset_root() / "user_plugin" / "agent_context_substrate", plugin_dir)
    local_config_path = _write_local_config(plugin_dir, project_root=project_root, wiki_root=wiki_root)

    paths = {"plugin_dir": plugin_dir, "local_config_path": local_config_path}
    if backup_path:
        paths["backup_path"] = backup_path
    return InstallResult(status="installed", paths=paths, messages=["user plugin installed"])


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
