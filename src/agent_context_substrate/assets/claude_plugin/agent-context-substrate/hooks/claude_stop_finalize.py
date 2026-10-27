from __future__ import annotations

from pathlib import Path
import json
import os
import sys


def main() -> int:
    _force_utf8_stdio()
    payload = _read_payload()
    # Stop re-entered after a blocking hook: do nothing at all.
    if payload.get("stop_hook_active") is True:
        return 0
    config_path = _config_path()
    config = _load_config(config_path)
    try:
        _prepare_import_path(config)
        from agent_context_substrate.claude_hook import run_claude_stop_finalize_hook

        output = run_claude_stop_finalize_hook(
            payload=payload,
            config_path=config_path,
            python_executable=str(config.get("python_executable") or sys.executable),
        )
    except Exception as exc:
        output = _failure(f"ACS Claude finalize hook failed: {exc}")
    if output:
        # ASCII-escaped JSON survives any console code page.
        print(json.dumps(output, ensure_ascii=True))
    return 0


def _plugin_root() -> Path:
    configured = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(configured).expanduser() if configured else Path(__file__).resolve().parents[1]


def _claude_home() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    if configured:
        return Path(configured).expanduser()
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or str(Path.home())
    return Path(home).expanduser() / ".claude"


def _config_path() -> Path:
    explicit = os.environ.get("ACS_CLAUDE_CONFIG", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    bundled = _plugin_root() / "local_config.json"
    if bundled.is_file():
        return bundled
    return _claude_home() / "agent-context-substrate" / "local_config.json"


def _load_config(path: Path) -> dict[str, object]:
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return config if isinstance(config, dict) else {}


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


def _read_payload() -> dict[str, object]:
    data = sys.stdin.buffer.read()
    if not data:
        return {}
    text = ""
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _failure(message: str) -> dict[str, object]:
    return {
        "continue": True,
        "suppressOutput": True,
        "systemMessage": f"{message}. Run `agent-context-substrate claude-status` to inspect the queue.",
    }


if __name__ == "__main__":
    raise SystemExit(main())
