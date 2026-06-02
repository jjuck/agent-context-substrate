---
name: agent-context-substrate
description: Use when working in Codex and the user wants local Codex sessions finalized, watched, or searched through Agent Context Substrate without MCP.
---

# Agent Context Substrate For Codex

Use the local CLI rather than MCP.

## Status

First check the integration mode:

```bash
agent-context-substrate codex-status
```

Codex Stop hooks are the primary finalize trigger when this plugin is installed and trusted. If hooks have not been reviewed with `/hooks`, or if a Stop event is missed, keep using `codex-watch` as the fallback.

## Hook Primary

After installing the plugin, check that the hook is present:

```bash
agent-context-substrate codex-status
```

Expected mode includes `hook_support=supported`, `hook_primary=installed`, and `watcher_fallback=available`.

## Watcher Fallback

Start the watcher for the active workspace:

```bash
agent-context-substrate codex-watch --project-root . --wiki-root "$WIKI_PATH"
```

The watcher reads `~/.codex/state_5.sqlite` and `~/.codex/sessions/**/rollout-*.jsonl` read-only, waits for idle rollout files, then runs `codex-finalize`.

## Manual Finalize

Finalize a specific thread:

```bash
agent-context-substrate codex-finalize --thread-id THREAD_ID --project-root . --wiki-root "$WIKI_PATH"
```

## Retrieval

Search durable knowledge:

```bash
agent-context-substrate search-knowledge --query "topic" --mode knowledge --project-root . --wiki-root "$WIKI_PATH"
```

Expand a hit:

```bash
agent-context-substrate expand-hit --hit-id HIT_ID --project-root . --wiki-root "$WIKI_PATH"
```
