"""ContextEngine implementation for Agent Context Substrate."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from agent.context_engine import ContextEngine
from agent.context_compressor import ContextCompressor

from .config import DEFAULT_PROJECT_ROOT, DEFAULT_WIKI_ROOT
from .formatting import already_injected, format_recovery_context
from .recovery_loader import (
    ledger_path,
    ledger_record_for,
    ledger_records,
    load_latest_recovery_from_ledger,
    load_recovery_brief,
    recovery_dir,
)
from .retrieval_tools import handle_knowledge_expand, handle_knowledge_search, retrieval_tool_schemas


class AgentContextSubstrateContextEngine(ContextEngine):
    """Prototype engine that surfaces durable wiki recovery briefs."""

    threshold_percent = 0.75
    protect_first_n = 3
    protect_last_n = 6

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = Path(
            project_root
            or os.environ.get("AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT", "")
            or DEFAULT_PROJECT_ROOT
        )
        self.wiki_root = Path(
            os.environ.get("AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT", "")
            or os.environ.get("WIKI_PATH", "")
            or DEFAULT_WIKI_ROOT
        )
        self.current_session_id = ""
        self.recovery_brief: dict[str, Any] | None = None
        self.recovery_source_path: Path | None = None
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_total_tokens = 0
        self.threshold_tokens = 0
        self.context_length = 0
        self.compression_count = 0
        self._delegate_compressor: ContextCompressor | None = None
        self._model = ""
        self._base_url = ""
        self._api_key = ""
        self._provider = ""
        self._api_mode = ""

    @property
    def name(self) -> str:
        return "agent_context_substrate"

    def update_from_response(self, usage: Dict[str, Any]) -> None:
        self.last_prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        self.last_completion_tokens = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        self.last_total_tokens = int(
            usage.get("total_tokens")
            or self.last_prompt_tokens + self.last_completion_tokens
            or 0
        )
        if self._delegate_compressor is not None:
            self._delegate_compressor.update_from_response(usage)
            self._sync_from_delegate_compressor()

    def _sync_from_delegate_compressor(self) -> None:
        if self._delegate_compressor is None:
            return
        self.last_prompt_tokens = int(getattr(self._delegate_compressor, "last_prompt_tokens", 0) or 0)
        self.last_completion_tokens = int(
            getattr(self._delegate_compressor, "last_completion_tokens", 0) or 0
        )
        self.last_total_tokens = self.last_prompt_tokens + self.last_completion_tokens
        self.threshold_tokens = int(getattr(self._delegate_compressor, "threshold_tokens", 0) or 0)
        self.context_length = int(getattr(self._delegate_compressor, "context_length", 0) or 0)
        self.compression_count = int(getattr(self._delegate_compressor, "compression_count", 0) or 0)

    def update_model(
        self,
        model: str,
        context_length: int,
        base_url: str = "",
        api_key: str = "",
        provider: str = "",
        api_mode: str = "",
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._provider = provider
        self._api_mode = api_mode
        self._delegate_compressor = ContextCompressor(
            model=model,
            threshold_percent=self.threshold_percent,
            protect_first_n=self.protect_first_n,
            protect_last_n=self.protect_last_n,
            quiet_mode=True,
            base_url=base_url,
            api_key=api_key,
            config_context_length=context_length,
            provider=provider,
            api_mode=api_mode,
        )
        self._delegate_compressor.update_model(
            model=model,
            context_length=context_length,
            base_url=base_url,
            api_key=api_key,
            provider=provider,
            api_mode=api_mode,
        )
        self._sync_from_delegate_compressor()

    def should_compress(self, prompt_tokens: int = None) -> bool:
        tokens = int(prompt_tokens if prompt_tokens is not None else self.last_prompt_tokens)
        if self._delegate_compressor is not None:
            return bool(self._delegate_compressor.should_compress(tokens))
        return bool(self.threshold_tokens and tokens >= self.threshold_tokens)

    def _with_recovery_context(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not self.recovery_brief or already_injected(messages):
            return messages

        recovery_message = {
            "role": "system",
            "content": format_recovery_context(self.recovery_brief),
        }
        if messages and messages[0].get("role") == "system":
            return [messages[0], recovery_message, *messages[1:]]
        return [recovery_message, *messages]

    def compress(
        self,
        messages: List[Dict[str, Any]],
        current_tokens: int = None,
        focus_topic: str = None,
    ) -> List[Dict[str, Any]]:
        messages_with_recovery = self._with_recovery_context(messages)
        if self._delegate_compressor is not None:
            compressed = self._delegate_compressor.compress(
                messages_with_recovery,
                current_tokens=current_tokens,
                focus_topic=focus_topic,
            )
            self._sync_from_delegate_compressor()
            return compressed

        self.compression_count += 1
        return messages_with_recovery

    def on_session_start(self, session_id: str, **kwargs) -> None:
        self.current_session_id = session_id or ""
        override_session_id = os.environ.get("AGENT_CONTEXT_SUBSTRATE_RECOVERY_SESSION_ID")
        brief, source_path = self._load_recovery_brief(
            requested_session_id=override_session_id or self.current_session_id
        )
        if brief is None and not override_session_id:
            brief, source_path = self._load_latest_recovery_from_ledger()
        self.recovery_brief = brief
        self.recovery_source_path = source_path

    def on_session_reset(self) -> None:
        super().on_session_reset()
        if self._delegate_compressor is not None:
            self._delegate_compressor.on_session_reset()
            self._sync_from_delegate_compressor()
        self.current_session_id = ""
        self.recovery_brief = None
        self.recovery_source_path = None

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "wiki_recovery_context",
                "description": (
                    "Return the durable recovery brief loaded from "
                    "agent-context-substrate packet/wiki artifacts."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Optional prior Hermes session id to load explicitly.",
                        }
                    },
                    "additionalProperties": False,
                },
            },
            *retrieval_tool_schemas(),
        ]

    def handle_tool_call(self, name: str, args: Dict[str, Any], **kwargs) -> str:
        args = args or {}
        if name == "wiki_knowledge_search":
            return handle_knowledge_search(args, project_root=self.project_root, wiki_root=self.wiki_root)
        if name == "wiki_knowledge_expand":
            return handle_knowledge_expand(args, project_root=self.project_root, wiki_root=self.wiki_root)
        if name != "wiki_recovery_context":
            return json.dumps({"error": f"Unknown context engine tool: {name}"})

        session_id = str(args.get("session_id") or "").strip()
        brief = self.recovery_brief
        source_path = self.recovery_source_path
        if session_id:
            loaded_brief, loaded_path = self._load_recovery_brief(requested_session_id=session_id)
            brief = loaded_brief
            source_path = loaded_path

        if not brief:
            return json.dumps(
                {
                    "ok": False,
                    "error": "No agent-context-substrate recovery brief found.",
                    "project_root": str(self.project_root),
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "ok": True,
                "brief": brief,
                "source_path": str(source_path) if source_path else "",
            },
            ensure_ascii=False,
        )

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        brief = self.recovery_brief or {}
        status.update(
            {
                "engine": self.name,
                "project_root": str(self.project_root),
                "wiki_root": str(self.wiki_root),
                "recovery_loaded": self.recovery_brief is not None,
                "recovery_session_id": str(brief.get("session_id", "")),
                "recovery_title": str(brief.get("task_title", "")),
                "recovery_source_path": str(self.recovery_source_path or ""),
            }
        )
        return status

    # Backward-compatible wrappers kept for focused tests and ad-hoc diagnostics.
    def _recovery_dir(self) -> Path:
        return recovery_dir(self.project_root)

    def _ledger_path(self) -> Path:
        return ledger_path(self.project_root)

    def _load_recovery_brief(
        self,
        requested_session_id: str | None = None,
    ) -> tuple[dict[str, Any] | None, Path | None]:
        return load_recovery_brief(self.project_root, requested_session_id)

    def _load_latest_recovery_from_ledger(self) -> tuple[dict[str, Any] | None, Path | None]:
        return load_latest_recovery_from_ledger(self.project_root)

    def _ledger_record_for(self, session_id: str) -> dict[str, Any] | None:
        return ledger_record_for(self.project_root, session_id)

    def _ledger_records(self) -> list[dict[str, Any]]:
        return ledger_records(self.project_root)
