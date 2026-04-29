"""Configuration constants for the Agent Context Substrate context engine."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from .local_config import PROJECT_ROOT as LOCAL_PROJECT_ROOT
    from .local_config import WIKI_ROOT as LOCAL_WIKI_ROOT
except Exception:  # local_config.py is installer-generated and optional.
    LOCAL_PROJECT_ROOT = None
    LOCAL_WIKI_ROOT = None

DEFAULT_PROJECT_ROOT = Path(
    os.environ.get("AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT", "")
    or LOCAL_PROJECT_ROOT
    or "~/.hermes/agent-context-substrate"
).expanduser()
DEFAULT_WIKI_ROOT = Path(
    os.environ.get("AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT", "")
    or os.environ.get("WIKI_PATH", "")
    or LOCAL_WIKI_ROOT
    or "~/LLM Wiki"
).expanduser()
LEDGER_PIPELINE = "session_finalize"
