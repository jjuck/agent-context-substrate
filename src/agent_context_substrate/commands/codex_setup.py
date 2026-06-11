from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from ..codex_setup import (
    codex_config_paths,
    codex_plugin_dir,
    default_codex_local_config,
    diagnose_codex,
    doctor_codex,
    read_codex_local_config,
    setup_codex,
    setup_codex_wizard,
    update_codex_local_config,
    write_codex_local_config,
)
from ..codex_wiki_root import resolve_codex_wiki_root


def handle_setup_codex_command(*, args: Any) -> int:
    result = setup_codex(
        codex_home=args.codex_home,
        project_root=args.project_root,
        wiki_root=args.wiki_root,
        personal_marketplace_root=args.personal_marketplace_root,
        install_user_hook=bool(args.user_hook_fallback and not args.no_user_hook),
        install_marketplace=not args.no_marketplace,
        overwrite=not args.no_overwrite,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_setup_result("setup-codex", result.to_dict())
    return 0 if result.ok else 1


def handle_setup_codex_wizard_command(*, args: Any) -> int:
    result = setup_codex_wizard(
        codex_home=args.codex_home,
        project_root=args.project_root,
        wiki_root=args.wiki_root,
        personal_marketplace_root=args.personal_marketplace_root,
        assume_yes=args.yes,
    )
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_setup_result("setup-codex-wizard", result.to_dict())
    return 0 if result.ok else 1


def handle_doctor_codex_command(*, args: Any) -> int:
    report = doctor_codex(
        codex_home=args.codex_home,
        project_root=args.project_root,
        wiki_root=args.wiki_root,
        summary_smoke=args.summary_smoke,
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"doctor-codex ok={report.ok}")
        for name, status in report.checks.items():
            print(f"{name}={status}")
        for message in report.messages:
            print(message)
    if args.fail_on_issues and not report.ok:
        return 1
    return 0


def handle_diagnose_codex_command(*, args: Any) -> int:
    report = diagnose_codex(
        codex_home=args.codex_home,
        project_root=args.project_root,
        wiki_root=args.wiki_root,
        personal_marketplace_root=args.personal_marketplace_root,
        fix=args.fix,
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"diagnose-codex ok={report.ok}")
        for issue in report.issues:
            print(f"issue={issue}")
        for action in report.actions:
            print(f"action={action}")
    return 0 if report.ok else 1


def handle_config_codex_command(*, args: Any) -> int:
    plugin_dir = codex_plugin_dir(args.codex_home)
    if args.config_action == "paths":
        paths = codex_config_paths(
            codex_home=args.codex_home,
            project_root=args.project_root,
            wiki_root=args.wiki_root,
            config=_read_config_for_paths(plugin_dir, explicit_wiki_root=args.wiki_root),
        )
        _print_mapping(paths, as_json=args.json)
        return 0

    if args.config_action == "show":
        config = read_codex_local_config(plugin_dir)
        _print_mapping(_with_effective_wiki_root(config), as_json=args.json)
        return 0

    if args.config_action == "write":
        config = default_codex_local_config(
            codex_home=args.codex_home,
            project_root=args.project_root,
            wiki_root=args.wiki_root,
        )
        written = write_codex_local_config(plugin_dir, config)
        _print_mapping(written, as_json=args.json)
        return 0

    if args.config_action == "set":
        value = _parse_config_value(args.value)
        updated = update_codex_local_config(plugin_dir, {args.key: value})
        _print_mapping(updated, as_json=args.json)
        return 0

    if args.config_action == "export-env":
        paths = codex_config_paths(
            codex_home=args.codex_home,
            project_root=args.project_root,
            wiki_root=args.wiki_root,
            config=_read_config_for_paths(plugin_dir, explicit_wiki_root=args.wiki_root),
        )
        print(f"$env:CODEX_HOME='{paths['codex_home']}'")
        print(f"$env:AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT='{paths['acs_project_root']}'")
        print(f"$env:AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT='{paths['llm_wiki_root']}'")
        return 0

    raise ValueError(f"unknown config-codex action: {args.config_action}")


def _print_setup_result(label: str, payload: dict[str, Any]) -> None:
    print(f"{label} ok={payload['ok']}")
    print(f"status={payload['status']}")
    for name, path in payload["paths"].items():
        print(f"{name}={path}")
    for action in payload["actions"]:
        print(f"action={action}")
    for message in payload["messages"]:
        print(message)


def _print_mapping(mapping: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({name: str(value) if isinstance(value, Path) else value for name, value in mapping.items()}, ensure_ascii=False, indent=2))
        return
    for name, value in mapping.items():
        print(f"{name}={value}")


def _with_effective_wiki_root(config: dict[str, Any]) -> dict[str, Any]:
    resolution = resolve_codex_wiki_root(config)
    view = dict(config)
    view.setdefault("wiki_root_source", resolution.source)
    if resolution.path is not None:
        view["wiki_root_effective"] = resolution.path
    return view


def _read_config_for_paths(plugin_dir: Path, *, explicit_wiki_root: str | None) -> dict[str, Any] | None:
    if explicit_wiki_root is not None:
        return None
    config_path = plugin_dir / "local_config.json"
    if not config_path.exists():
        return None
    return read_codex_local_config(plugin_dir)


def _parse_config_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
