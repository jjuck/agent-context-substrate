from __future__ import annotations

from pathlib import Path
import sys

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from runtime import (  # noqa: E402
    handle_harness_command,
    handle_packet_command,
    handle_session_finalize,
    handle_session_reset,
    handle_wiki_language_command,
    handle_wiki_lint_command,
    handle_wiki_resume_command,
)


def register(ctx) -> None:
    ctx.register_hook("on_session_finalize", handle_session_finalize)
    ctx.register_hook("on_session_reset", handle_session_reset)
    ctx.register_command(
        "harness",
        handle_harness_command,
        description="Show wiki-harness plugin status",
    )
    ctx.register_command(
        "packet",
        handle_packet_command,
        description="Generate or reuse a packet for a session id",
    )
    ctx.register_command(
        "wiki-resume",
        handle_wiki_resume_command,
        description="Show a compact recovery brief for a session id",
    )
    ctx.register_command(
        "wiki-lint",
        handle_wiki_lint_command,
        description="Run wiki-harness lint and report output paths",
    )
    ctx.register_command(
        "wiki-language",
        handle_wiki_language_command,
        description="Show or change LLM Wiki language settings",
        args_hint="[ko|en|status]",
    )
    ctx.register_command(
        "wiki-lang",
        handle_wiki_language_command,
        description="Alias for /wiki-language",
        args_hint="[ko|en|status]",
    )
