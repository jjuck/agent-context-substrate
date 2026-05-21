"""Request-time retrieval tool schemas and handlers for agent_context_substrate."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from .config import DEFAULT_PROJECT_ROOT


def retrieval_tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "name": "wiki_knowledge_search",
            "description": (
                "Search the Agent Context Substrate knowledge layer while solving the "
                "current request. Use this when prior project decisions, wiki pages, "
                "context packets, summaries, topic maps, promotion candidates, "
                "wiki patch proposals, applied patch logs, or raw evidence may be relevant."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "limit": {"type": "integer", "description": "Maximum hits to return."},
                    "include_raw": {
                        "type": "boolean",
                        "description": "Include raw state.db message hits when summaries/wiki are insufficient.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["knowledge", "graph", "recovery"],
                        "description": (
                            "Retrieval mode. Use graph to search topic-map nodes, edges, and readable paths only. "
                            "Use recovery to find where prior work stopped from recovery briefs and packet fields."
                        ),
                    },
                    "graph_depth": {
                        "type": "integer",
                        "description": "When mode=graph, include neighboring topic-map nodes/edges up to this depth.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "wiki_knowledge_expand",
            "description": "Expand a retrieval hit returned by wiki_knowledge_search into full content and metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hit_id": {"type": "string", "description": "Retrieval hit id to expand."},
                },
                "required": ["hit_id"],
                "additionalProperties": False,
            },
        },
    ]


def handle_knowledge_search(args: Dict[str, Any], *, project_root: Path, wiki_root: Path) -> str:
    query = str(args.get("query") or "").strip()
    if not query:
        return json.dumps({"ok": False, "error": "query is required"}, ensure_ascii=False)
    try:
        limit = int(args.get("limit") or 5)
    except (TypeError, ValueError):
        limit = 5
    include_raw = bool(args.get("include_raw") or False)
    mode = str(args.get("mode") or "knowledge").strip() or "knowledge"
    try:
        graph_depth = int(args.get("graph_depth") or 0)
    except (TypeError, ValueError):
        graph_depth = 0
    try:
        search_knowledge, _ = load_retrieval_api(project_root)
        hits = search_knowledge(
            query,
            project_root=project_root,
            wiki_root=wiki_root,
            limit=limit,
            include_raw=include_raw,
            mode=mode,
            graph_depth=graph_depth,
        )
        return json.dumps(
            {
                "ok": True,
                "query": query,
                "mode": mode,
                "graph_depth": graph_depth,
                "hits": [hit.to_dict() for hit in hits],
                "project_root": str(project_root),
                "wiki_root": str(wiki_root),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def handle_knowledge_expand(args: Dict[str, Any], *, project_root: Path, wiki_root: Path) -> str:
    hit_id = str(args.get("hit_id") or "").strip()
    if not hit_id:
        return json.dumps({"ok": False, "error": "hit_id is required"}, ensure_ascii=False)
    try:
        _, expand_hit = load_retrieval_api(project_root)
        detail = expand_hit(hit_id, project_root=project_root, wiki_root=wiki_root)
        return json.dumps({"ok": True, "detail": detail.to_dict()}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def load_retrieval_api(project_root: Path):
    for src_path in (project_root / "src", DEFAULT_PROJECT_ROOT / "src"):
        if src_path.exists() and str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))
    from agent_context_substrate.retrieval import expand_hit, search_knowledge

    return search_knowledge, expand_hit
