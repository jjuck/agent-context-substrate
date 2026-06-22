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

Codex Stop hooks are the primary finalize trigger when this plugin is registered, installed, and trusted. `setup-codex` copies the plugin asset/marketplace/cache files and, when a usable Codex CLI is available, registers `agent-context-substrate@personal` with `codex plugin add`. If `doctor-codex` reports `codex_plugin_registered=missing`, run `codex plugin add agent-context-substrate@personal --json`; the plugin may appear under `Personal` or `Created by you`. If hooks have not been reviewed in `Codex app -> Settings -> Hooks`, or if a Stop event is missed, keep using `codex-watch` as the fallback. CLI `/hooks` is the alternate review path for CLI/TUI users. Hook trust is separate from Full Access, approval mode, sandbox settings, auto-review, and plugin installation state.

`project_root` is the ACS artifact root, not the active Codex workspace allowlist. New installs set `allowed_workspace_roots` to `%USERPROFILE%\Documents\Codex` so ordinary Codex workspaces can finalize on Stop while artifacts stay under `<PROJECT_ROOT>/data`. If `doctor-codex` reports `codex_hook_recent_workspace_skips=warn`, inspect `data/index/codex_hook_events.jsonl` and update `allowed_workspace_roots` for the user's actual workspace parent.

New Codex installs default to `summary_mode=auto`, `wiki_auto_mode=apply-flexible`, `wiki_write_judge_mode=auto`, and `wiki_auto_min_score=0.85`. Treat the LLM Wiki as a living knowledge graph: eligible stopped threads can become wiki updates when the write judge approves the evidence-backed flexible patch. If the judge path fails or confidence is too low, ACS leaves review-required artifacts under `data/...` instead of writing the vault.

## Hook Primary

After installing the plugin, check that the hook is present:

```bash
agent-context-substrate codex-status
```

Expected mode includes `hook_support=supported`, `hook_primary=installed`, and `watcher_fallback=available`.

`doctor-codex` should also report `codex_plugin_registered=ok` when Codex CLI registry inspection is available. Plugin files on disk do not by themselves mean Codex has registered `agent-context-substrate@personal`.

## Watcher Fallback

Start the watcher for the active workspace:

```bash
agent-context-substrate codex-watch --project-root . --wiki-root "$WIKI_PATH" --summary-mode auto --wiki-auto-mode apply-flexible --wiki-write-judge-mode auto
```

The watcher reads `~/.codex/state_5.sqlite` and `~/.codex/sessions/**/rollout-*.jsonl` read-only, waits for idle rollout files, then runs `codex-finalize`.

## Manual Finalize

Finalize a specific thread:

```bash
agent-context-substrate codex-finalize --thread-id THREAD_ID --project-root . --wiki-root "$WIKI_PATH" --summary-mode auto --wiki-auto-mode apply-flexible --wiki-write-judge-mode auto
```

To inspect or change installed defaults:

```bash
agent-context-substrate config-codex show
agent-context-substrate config-codex set --key wiki_auto_mode --value apply-flexible
```

`auto` tries `codex exec` with read-only sandbox, `approval_policy=never`, `service_tier=fast`, low reasoning effort, hooks disabled, and inline bounded JSON input, then falls back to heuristic summaries when the CLI is unavailable or output validation fails. The wiki write judge uses the same signed-in Codex runtime when `wiki_write_judge_mode=auto`.

## Retrieval

Search durable knowledge:

```bash
agent-context-substrate search-knowledge --query "topic" --mode knowledge --project-root . --wiki-root "$WIKI_PATH"
```

Expand a hit:

```bash
agent-context-substrate expand-hit --hit-id HIT_ID --project-root . --wiki-root "$WIKI_PATH"
```
