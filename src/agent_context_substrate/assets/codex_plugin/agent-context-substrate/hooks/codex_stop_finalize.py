from __future__ import annotations

from pathlib import Path
import json
import os
import sys


def main() -> int:
    plugin_root = _plugin_root()
    config = _load_config(plugin_root)
    try:
        _prepare_import_path(config)
        from agent_context_substrate.codex_hook import run_codex_stop_finalize_hook

        payload = json.loads(_read_stdin_json_text() or "{}")
        output = run_codex_stop_finalize_hook(
            payload=payload,
            plugin_root=plugin_root,
            python_executable=str(config.get("python_executable") or sys.executable),
        )
    except Exception as exc:
        output = _failure(f"ACS Codex finalize hook failed: {exc}")
    print(json.dumps(output, ensure_ascii=False))
    return 0


def _plugin_root() -> Path:
    configured = os.environ.get("PLUGIN_ROOT")
    return Path(configured).expanduser() if configured else Path(__file__).resolve().parents[1]


def _load_config(plugin_root: Path) -> dict[str, object]:
    try:
        bootstrap_path = plugin_root / "local_config.json"
        config = json.loads(bootstrap_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(config, dict):
        return {}
    canonical_value = str(config.get("canonical_config_path") or "").strip()
    if not canonical_value:
        codex_home = str(config.get("codex_home") or "").strip()
        if codex_home:
            canonical_value = str(
                Path(codex_home) / "plugins" / "agent-context-substrate" / "local_config.json"
            )
    if not canonical_value:
        return config
    canonical_path = Path(canonical_value).expanduser().resolve(strict=False)
    if canonical_path == bootstrap_path.resolve(strict=False) or not canonical_path.exists():
        return config
    try:
        canonical = json.loads(canonical_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return canonical if isinstance(canonical, dict) else {}


def _prepare_import_path(config: dict[str, object]) -> None:
    entries: list[Path] = []
    configured_entries = config.get("python_path_entries")
    if isinstance(configured_entries, list):
        entries.extend(Path(str(entry)).expanduser() for entry in configured_entries if str(entry).strip())
    project_root = config.get("project_root")
    if project_root:
        project_src = Path(str(project_root)).expanduser() / "src"
        if project_src.exists():
            entries.append(project_src)
    for entry in reversed(entries):
        text = str(entry.resolve(strict=False))
        if text not in sys.path:
            sys.path.insert(0, text)


def _read_stdin_json_text() -> str:
    data = sys.stdin.buffer.read()
    if not data:
        return ""
    for encoding in ("utf-8-sig", "utf-8", sys.getdefaultencoding()):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _failure(message: str) -> dict[str, object]:
    return {
        "continue": True,
        "systemMessage": (
            f"{message}. Run codex-status and doctor-codex first; "
            "use codex-watch only for explicit history recovery/backfill."
        ),
    }


if __name__ == "__main__":
    raise SystemExit(main())
