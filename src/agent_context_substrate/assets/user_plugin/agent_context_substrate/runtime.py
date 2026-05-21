from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import importlib
import logging
import os
import re
import sys

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from config import AgentContextSubstratePluginConfig, load_plugin_config

logger = logging.getLogger(__name__)


def _ensure_harness_on_path(config: AgentContextSubstratePluginConfig) -> None:
    src_path = config.project_root / "src"
    if src_path.exists() and str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


@contextmanager
def _temporary_wiki_root(wiki_root: Path):
    old_value = os.environ.get("WIKI_PATH")
    os.environ["WIKI_PATH"] = str(Path(wiki_root).resolve())
    try:
        yield
    finally:
        if old_value is None:
            os.environ.pop("WIKI_PATH", None)
        else:
            os.environ["WIKI_PATH"] = old_value


def _load_harness_api():
    config = load_plugin_config()
    _ensure_harness_on_path(config)
    integration = importlib.import_module("agent_context_substrate.integration")
    return integration.should_process_session, integration.run_session_finalize_pipeline


def _load_recovery_api():
    config = load_plugin_config()
    _ensure_harness_on_path(config)
    recovery = importlib.import_module("agent_context_substrate.recovery")
    return recovery.build_recovery_brief


def _load_lint_api():
    config = load_plugin_config()
    _ensure_harness_on_path(config)
    lint = importlib.import_module("agent_context_substrate.lint")
    return lint.lint_wiki, lint.export_lint_report


def _load_agent_llm_router_builder():
    config = load_plugin_config()
    _ensure_harness_on_path(config)
    router_module = importlib.import_module("agent_context_substrate.agent_llm_router")
    return router_module.build_agent_llm_router


def _load_llm_safety_options_class():
    config = load_plugin_config()
    _ensure_harness_on_path(config)
    summarizer_backends = importlib.import_module("agent_context_substrate.summarizer_backends")
    return summarizer_backends.LLMInputSafetyOptions


def _host_agent_from_kwargs(kwargs: dict[str, object]) -> object | None:
    for key in ("host", "agent", "context", "ctx", "plugin_context"):
        candidate = kwargs.get(key)
        if candidate is not None:
            return candidate
    return None


def _summary_pipeline_kwargs(config: AgentContextSubstratePluginConfig, hook_kwargs: dict[str, object]) -> dict[str, object]:
    summary_mode = str(getattr(config, "summary_mode", "") or "").strip().lower()
    if not summary_mode or summary_mode in {"off", "none", "disabled"}:
        return {}

    agent_llm_router = None
    if summary_mode in {"agent-llm", "hybrid"}:
        host_agent = _host_agent_from_kwargs(hook_kwargs)
        if host_agent is not None:
            agent_llm_router = _load_agent_llm_router_builder()(host_agent)

    llm_safety_class = _load_llm_safety_options_class()
    return {
        "summary_mode": summary_mode,
        "agent_llm_router": agent_llm_router,
        "summary_model": getattr(config, "summary_model", None),
        "summary_budget": getattr(config, "summary_budget", None),
        "summary_cache": bool(getattr(config, "summary_cache", False)),
        "llm_safety": llm_safety_class(
            redact=bool(getattr(config, "llm_redact", True)),
            max_input_chars=int(getattr(config, "llm_max_input_chars", 12_000)),
            allow_code_snippets=bool(getattr(config, "llm_allow_code_snippets", False)),
        ),
    }


def _diagnose_config(config: AgentContextSubstratePluginConfig) -> dict[str, object]:
    project_exists = config.project_root.exists()
    wiki_exists = config.wiki_root.exists()
    harness_importable = False
    harness_import_error = ""
    src_path = config.project_root / "src"
    try:
        if not src_path.exists():
            raise ModuleNotFoundError(f"configured harness src path does not exist: {src_path}")
        _ensure_harness_on_path(config)
        harness_module = importlib.import_module("agent_context_substrate")
        module_file = getattr(harness_module, "__file__", "")
        if module_file:
            module_path = Path(module_file).resolve()
            expected_src = src_path.resolve()
            if not module_path.is_relative_to(expected_src):
                raise ModuleNotFoundError(
                    f"import resolved outside configured project src: {module_path}"
                )
        harness_importable = True
    except Exception as exc:
        harness_import_error = f"{type(exc).__name__}: {exc}"
    return {
        "project_root_exists": project_exists,
        "wiki_root_exists": wiki_exists,
        "harness_importable": harness_importable,
        "harness_import_error": harness_import_error,
        "health": "ok" if project_exists and wiki_exists and harness_importable else "degraded",
    }


def _status_lines(config: AgentContextSubstratePluginConfig) -> list[str]:
    diagnostics = _diagnose_config(config)
    allowed_sources = list(getattr(config, "allowed_sources", []))
    gateway_policy = getattr(config, "gateway_policy", "trigger-only")
    promotion_mode = getattr(config, "promotion_mode", "packet-only")
    gateway_source_status = "enabled" if "gateway" in set(allowed_sources) else "disabled"
    lines = [
        "Agent Context Substrate plugin status",
        f"- health: {diagnostics['health']}",
        f"- project_root: {config.project_root}",
        f"- project_root exists: {diagnostics['project_root_exists']}",
        f"- wiki_root: {config.wiki_root}",
        f"- wiki_root exists: {diagnostics['wiki_root_exists']}",
        f"- harness_importable: {diagnostics['harness_importable']}",
        f"- auto_finalize_enabled: {config.auto_finalize_enabled}",
        f"- min_message_count: {config.min_message_count}",
        f"- allowed_sources: {', '.join(allowed_sources)}",
        f"- promotion_mode: {promotion_mode}",
        f"- gateway_policy: {gateway_policy}",
        f"- gateway source auto-finalize: {gateway_source_status}",
    ]
    if diagnostics["harness_import_error"]:
        lines.append(f"- harness_import_error: {diagnostics['harness_import_error']}")
    return lines


def handle_harness_command(raw_args: str = "") -> str:
    config = load_plugin_config()
    return "\n".join(_status_lines(config))


def _wiki_config_path(config: AgentContextSubstratePluginConfig) -> Path:
    return Path(config.wiki_root) / "_system" / "config.yaml"


def _parse_inline_list(value: str) -> list[str]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [item.strip().strip("'\"") for item in value.split(",") if item.strip()]


def _extract_wiki_language_settings(text: str) -> dict[str, object]:
    settings: dict[str, object] = {
        "default_language": "",
        "filename_language": "",
        "template_language": "",
        "supported_languages": [],
    }
    in_wiki = False
    collecting_supported = False
    supported: list[str] = []
    for raw_line in text.splitlines():
        if re.match(r"^\S", raw_line):
            in_wiki = raw_line.strip() == "wiki:"
            collecting_supported = False
            continue
        if not in_wiki:
            continue
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if collecting_supported and stripped.startswith("-"):
            supported.append(stripped[1:].strip().strip("'\""))
            continue
        collecting_supported = False
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        value = value.strip().strip("'\"")
        if key in {"default_language", "filename_language", "template_language"}:
            settings[key] = value
        elif key == "supported_languages":
            if value:
                supported = _parse_inline_list(value)
            else:
                collecting_supported = True
    settings["supported_languages"] = supported
    return settings


def _replace_or_insert_wiki_language_key(lines: list[str], key: str, value: str) -> list[str]:
    key_pattern = re.compile(rf"^(\s*){re.escape(key)}\s*:.*$")
    in_wiki = False
    wiki_line_index: int | None = None
    insert_at: int | None = None
    for index, line in enumerate(lines):
        if re.match(r"^\S", line):
            if in_wiki:
                insert_at = index
                break
            in_wiki = line.strip() == "wiki:"
            if in_wiki:
                wiki_line_index = index
            continue
        if in_wiki and key_pattern.match(line):
            indent = key_pattern.match(line).group(1)  # type: ignore[union-attr]
            lines[index] = f"{indent}{key}: {value}"
            return lines
    if wiki_line_index is None:
        return ["wiki:", f"  {key}: {value}", *lines]
    if insert_at is None:
        insert_at = len(lines)
    lines.insert(insert_at, f"  {key}: {value}")
    return lines


def _update_wiki_language_text(text: str, language: str) -> str:
    lines = text.splitlines()
    trailing_newline = text.endswith("\n")
    for key in ("default_language", "filename_language", "template_language"):
        lines = _replace_or_insert_wiki_language_key(lines, key, language)
    updated = "\n".join(lines)
    if trailing_newline or not updated.endswith("\n"):
        updated += "\n"
    return updated


def handle_wiki_language_command(raw_args: str = "") -> str:
    config = load_plugin_config()
    config_path = _wiki_config_path(config)
    if not config_path.exists():
        return "\n".join(
            [
                "Wiki language settings unavailable",
                f"- config_path: {config_path}",
                "- error: _system/config.yaml does not exist",
            ]
        )

    text = config_path.read_text(encoding="utf-8")
    settings = _extract_wiki_language_settings(text)
    supported = list(settings.get("supported_languages") or ["ko", "en"])
    supported_display = ", ".join(supported)
    requested = raw_args.strip().split()[0].lower() if raw_args.strip() else ""

    if not requested or requested in {"status", "show", "current"}:
        return "\n".join(
            [
                "Wiki language settings",
                f"- default_language: {settings.get('default_language') or '(unset)'}",
                f"- filename_language: {settings.get('filename_language') or '(unset)'}",
                f"- template_language: {settings.get('template_language') or '(unset)'}",
                f"- supported_languages: {supported_display}",
                f"- config_path: {config_path}",
                f"Usage: /wiki-language <{'|'.join(supported)}>",
            ]
        )

    if requested not in supported:
        return "\n".join(
            [
                "Unsupported wiki language",
                f"- requested: {requested}",
                f"- supported_languages: {supported_display}",
                f"Usage: /wiki-language <{'|'.join(supported)}>",
            ]
        )

    updated = _update_wiki_language_text(text, requested)
    config_path.write_text(updated, encoding="utf-8")
    return "\n".join(
        [
            "Wiki language updated",
            f"- default_language: {requested}",
            f"- filename_language: {requested}",
            f"- template_language: {requested}",
            f"- supported_languages: {supported_display}",
            f"- config_path: {config_path}",
        ]
    )


def handle_packet_command(raw_args: str = "") -> str:
    session_id = raw_args.strip()
    if not session_id:
        return "Usage: /packet <session_id>"

    config = load_plugin_config()
    try:
        _, run_session_finalize_pipeline = _load_harness_api()
        result = run_session_finalize_pipeline(
            session_id=session_id,
            project_root=config.project_root,
            wiki_root=config.wiki_root,
            promotion_mode=getattr(config, "promotion_mode", "packet-only"),
        )
    except Exception as exc:
        logger.exception("agent-context-substrate packet command failed for session_id=%s", session_id)
        return "\n".join(
            [
                "Agent Context Substrate packet failed",
                f"- session_id: {session_id}",
                f"- error: {type(exc).__name__}: {exc}",
            ]
        )
    status = "reused" if result.skipped else "processed"
    return "\n".join(
        [
            f"Agent Context Substrate packet {status}",
            f"- session_id: {session_id}",
            f"- packet_id: {result.packet_id}",
            f"- recovery_json_path: {getattr(result, 'recovery_json_path', '')}",
        ]
    )


def handle_wiki_resume_command(raw_args: str = "") -> str:
    session_id = raw_args.strip()
    if not session_id:
        return "Usage: /wiki-resume <session_id>"

    config = load_plugin_config()
    try:
        build_recovery_brief = _load_recovery_api()
        brief = build_recovery_brief(
            session_id=session_id,
            project_root=config.project_root,
            wiki_root=config.wiki_root,
            max_items=5,
        )
    except Exception as exc:
        logger.exception("agent-context-substrate resume command failed for session_id=%s", session_id)
        return "\n".join(
            [
                "Wiki resume failed",
                f"- session_id: {session_id}",
                f"- error: {type(exc).__name__}: {exc}",
            ]
        )

    lines = [
        f"Wiki resume: {brief.task_title}",
        f"- session_id: {brief.session_id}",
        f"- packet_id: {brief.packet_id}",
        f"- macro_context: {brief.macro_context}",
    ]
    if brief.critical_files:
        lines.append(f"- critical_files: {', '.join(brief.critical_files)}")
    if brief.open_questions:
        lines.append(f"- open_questions: {', '.join(brief.open_questions)}")
    if brief.related_pages:
        lines.append(f"- related_pages: {', '.join(brief.related_pages)}")
    lines.append(f"- recovery_json_path: {brief.recovery_json_path}")
    return "\n".join(lines)


def _lint_issue_count(report) -> int:
    return sum(
        len(items)
        for items in [
            report.missing_provenance_pages,
            report.orphan_pages,
            report.pages_missing_from_index,
            report.broken_wikilinks,
            report.micro_summaries_missing_parent_unit,
            report.micro_summaries_with_unknown_parent_unit,
            report.unit_summaries_with_missing_micro_references,
            report.packet_micro_summaries_unreferenced,
            report.packets_missing_raw_pointers,
            getattr(report, "numeric_slug_pages", []),
            getattr(report, "session_id_slug_pages", []),
            getattr(report, "generated_summary_only_pages", []),
            getattr(report, "multiline_frontmatter_title_pages", []),
            getattr(report, "transient_command_title_pages", []),
            getattr(report, "smoke_or_test_pages", []),
            getattr(report, "session_derived_plan_pages", []),
            getattr(report, "excessive_critical_files_pages", []),
            getattr(report, "missing_lang_pages", []),
            getattr(report, "unsupported_lang_pages", []),
            getattr(report, "missing_required_sections_pages", []),
            getattr(report, "thin_content_pages", []),
            getattr(report, "unexplained_english_terms_pages", []),
            getattr(report, "insufficient_related_links_pages", []),
        ]
    )


def handle_wiki_lint_command(raw_args: str = "") -> str:
    config = load_plugin_config()
    try:
        _ensure_harness_on_path(config)
        lint_wiki, export_lint_report = _load_lint_api()

        with _temporary_wiki_root(config.wiki_root):
            try:
                from agent_context_substrate.paths import HarnessPaths

                paths = HarnessPaths(project_root=config.project_root)
            except Exception:
                from types import SimpleNamespace

                paths = SimpleNamespace(project_root=config.project_root, wiki_root=config.wiki_root)
            report = lint_wiki(paths)
            json_path, markdown_path = export_lint_report(report, paths, report_id="agent-context-substrate-cli")
    except Exception as exc:
        logger.exception("agent-context-substrate lint command failed")
        return "\n".join(
            [
                "Wiki lint failed",
                f"- error: {type(exc).__name__}: {exc}",
            ]
        )

    return "\n".join(
        [
            "Wiki lint complete",
            f"- checked_pages={len(report.checked_pages)}",
            f"- orphan_pages={len(report.orphan_pages)}",
            f"- broken_wikilinks={len(report.broken_wikilinks)}",
            f"- issue_count={_lint_issue_count(report)}",
            f"- json_path={json_path}",
            f"- markdown_path={markdown_path}",
        ]
    )


def handle_session_finalize(*, session_id: str | None = None, platform: str | None = None, **kwargs):
    try:
        config = load_plugin_config()
        if not session_id:
            return {"status": "ignored", "reason": "missing_session_id"}
        if not config.auto_finalize_enabled:
            return {"status": "disabled", "session_id": session_id}

        should_process_session, run_session_finalize_pipeline = _load_harness_api()
        eligible = should_process_session(
            session_id,
            min_message_count=config.min_message_count,
            allowed_sources=config.allowed_sources,
            skip_title_patterns=config.skip_title_patterns,
        )
        if not eligible:
            return {"status": "skipped", "reason": "policy", "session_id": session_id}

        result = run_session_finalize_pipeline(
            session_id=session_id,
            project_root=config.project_root,
            wiki_root=config.wiki_root,
            promotion_mode=getattr(config, "promotion_mode", "packet-only"),
            **_summary_pipeline_kwargs(config, kwargs),
        )
        return {
            "status": "processed" if not result.skipped else "reused",
            "session_id": session_id,
            "packet_id": result.packet_id,
            "skipped": result.skipped,
            "recovery_json_path": str(getattr(result, "recovery_json_path", "")),
            "platform": platform or "unknown",
        }
    except Exception as exc:
        logger.exception("agent-context-substrate session finalize failed for session_id=%s", session_id)
        return {
            "status": "error",
            "session_id": session_id,
            "platform": platform or "unknown",
            "error": f"{type(exc).__name__}: {exc}",
        }


def handle_session_reset(*, session_id: str | None = None, platform: str | None = None, **kwargs):
    return {
        "status": "observed",
        "session_id": session_id,
        "platform": platform or "unknown",
    }
