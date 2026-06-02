from __future__ import annotations

from pathlib import Path
from typing import Any

from ..distribution import doctor, init_wiki, install_context_engine, install_user_plugin, run_fresh_install_smoke
from ..distribution import install_codex_plugin


def handle_init_wiki_command(*, args: Any) -> int:
    result = init_wiki(Path(args.wiki_root).resolve())
    print(result.status)
    for name, path in result.paths.items():
        print(f"{name}={path}")
    for message in result.messages:
        print(message)
    return 0


def handle_install_plugin_command(*, args: Any) -> int:
    result = install_user_plugin(
        hermes_home=Path(args.hermes_home).expanduser(),
        project_root=Path(args.project_root).expanduser(),
        wiki_root=Path(args.wiki_root).expanduser(),
        overwrite=args.overwrite,
    )
    print(result.status)
    for name, path in result.paths.items():
        print(f"{name}={path}")
    for message in result.messages:
        print(message)
    return 0


def handle_install_codex_plugin_command(*, args: Any) -> int:
    result = install_codex_plugin(
        codex_home=Path(args.codex_home).expanduser(),
        project_root=Path(args.project_root).expanduser(),
        wiki_root=Path(args.wiki_root).expanduser(),
        personal_marketplace_root=(
            Path(args.personal_marketplace_root).expanduser()
            if getattr(args, "personal_marketplace_root", None)
            else None
        ),
        install_user_hook=args.install_user_hook,
        overwrite=args.overwrite,
    )
    print(result.status)
    for name, path in result.paths.items():
        print(f"{name}={path}")
    for message in result.messages:
        print(message)
    return 0


def handle_install_context_engine_command(*, args: Any) -> int:
    result = install_context_engine(
        hermes_agent_root=Path(args.hermes_agent_root).expanduser(),
        project_root=Path(args.project_root).expanduser() if args.project_root else None,
        wiki_root=Path(args.wiki_root).expanduser() if args.wiki_root else None,
        overwrite=args.overwrite,
    )
    print(result.status)
    for name, path in result.paths.items():
        print(f"{name}={path}")
    for message in result.messages:
        print(message)
    return 0


def handle_doctor_command(*, args: Any) -> int:
    report = doctor(
        hermes_home=Path(args.hermes_home).expanduser(),
        project_root=Path(args.project_root).expanduser(),
        wiki_root=Path(args.wiki_root).expanduser(),
        hermes_agent_root=Path(args.hermes_agent_root).expanduser(),
    )
    print(f"doctor ok={report.ok}")
    for name, ok in report.checks.items():
        print(f"{name}={'ok' if ok else 'missing'}")
    for message in report.messages:
        print(message)
    if args.fail_on_issues and not report.ok:
        return 1
    return 0


def handle_fresh_install_smoke_command(*, args: Any) -> int:
    result = run_fresh_install_smoke(
        session_id=args.session_id,
        hermes_home=Path(args.hermes_home).expanduser(),
        project_root=Path(args.project_root).expanduser(),
        wiki_root=Path(args.wiki_root).expanduser(),
        hermes_agent_root=Path(args.hermes_agent_root).expanduser() if args.hermes_agent_root else None,
    )
    print(f"fresh-install-smoke ok={result.ok}")
    print(f"retrieval_hit_count={result.retrieval_hit_count}")
    print(f"expanded_content_length={result.expanded_content_length}")
    print(f"lint_issue_count={result.lint_issue_count}")
    for name, path in result.artifacts.items():
        print(f"{name}={path}")
    for message in result.messages:
        print(message)
    return 0 if result.ok else 1
