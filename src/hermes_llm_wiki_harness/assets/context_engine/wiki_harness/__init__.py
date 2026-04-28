"""Hermes LLM Wiki Harness context-engine plugin."""

from __future__ import annotations

from .config import DEFAULT_PROJECT_ROOT, DEFAULT_WIKI_ROOT, LEDGER_PIPELINE
from .engine import WikiHarnessContextEngine
from .formatting import RECOVERY_MARKER, already_injected, format_recovery_context
from .recovery_loader import (
    ledger_path,
    ledger_record_for,
    ledger_records,
    load_first_json,
    load_json_object,
    load_latest_recovery_from_ledger,
    load_recovery_brief,
    recovery_dir,
    resolve_artifact_path,
)
from .retrieval_tools import (
    handle_knowledge_expand,
    handle_knowledge_search,
    load_retrieval_api,
    retrieval_tool_schemas,
)

# Backward-compatible aliases for previous private helper names used in ad-hoc debugging.
_already_injected = already_injected
_format_recovery_context = format_recovery_context
_load_first_json = load_first_json
_load_json_object = load_json_object
_resolve_artifact_path = resolve_artifact_path


def register(ctx) -> None:
    """Plugin-style entrypoint used by context-engine discovery."""
    ctx.register_context_engine(WikiHarnessContextEngine())


__all__ = [
    "DEFAULT_PROJECT_ROOT",
    "DEFAULT_WIKI_ROOT",
    "LEDGER_PIPELINE",
    "RECOVERY_MARKER",
    "WikiHarnessContextEngine",
    "already_injected",
    "format_recovery_context",
    "handle_knowledge_expand",
    "handle_knowledge_search",
    "ledger_path",
    "ledger_record_for",
    "ledger_records",
    "load_first_json",
    "load_json_object",
    "load_latest_recovery_from_ledger",
    "load_recovery_brief",
    "load_retrieval_api",
    "recovery_dir",
    "register",
    "resolve_artifact_path",
    "retrieval_tool_schemas",
]
