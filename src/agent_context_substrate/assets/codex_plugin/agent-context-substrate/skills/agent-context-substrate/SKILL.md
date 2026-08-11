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

Codex Stop hooks are the primary trigger when this plugin is registered, installed, and trusted. Review or trust the hook in `Codex app -> Settings -> Hooks`; CLI `/hooks` is the alternate path for CLI/TUI users. New installs use `trigger_strategy=hook-enqueue`: the one-shot hook durably records the current rollout fingerprint in `data/index/codex_jobs.sqlite3`, launches a hidden singleton worker, and returns quickly. The worker performs finalization, retries transient failures, and dead-letters exhausted jobs. `setup-codex` copies the plugin asset/marketplace/cache files and, when a usable Codex CLI is available, registers `agent-context-substrate@personal` with `codex plugin add`. If `doctor-codex` reports `codex_plugin_registered=missing`, run `codex plugin add agent-context-substrate@personal --json`; the plugin may appear under `Personal` or `Created by you`. Hook trust is separate from Full Access, approval mode, sandbox settings, auto-review, and plugin installation state.

`project_root` is the ACS artifact root, not the active Codex workspace allowlist. New installs use `workspace_scope="all"`, so any active Codex workspace can finalize on Stop while artifacts stay under `<PROJECT_ROOT>/data`. Use `workspace_scope="restricted"` with explicit `allowed_workspace_roots` only when a user requests an allowlist boundary.

New Codex installs default to `summary_mode=auto`, `wiki_auto_mode=apply-flexible`, `wiki_write_judge_mode=auto`, and `wiki_auto_min_score=0.85`. Treat the LLM Wiki as a living knowledge graph: eligible stopped threads can become wiki updates when the write judge approves the evidence-backed flexible patch. If the judge path fails or confidence is too low, ACS leaves review-required artifacts under `data/...` instead of writing the vault.

The default wiki policy is `emergent-root`: new flexible pages use `<Title>.md` at the vault root, while optional category/type metadata, sources, wikilinks, and the generated MOC carry meaning. Category values are open vocabulary and do not grant or deny write permission. Approved writes update the page, index, log, promotion state, and applied record through a recoverable transaction.

Resolve the effective wiki root with `config-codex paths`. The installed default is the portable `%USERPROFILE%\Documents\LLM Wiki` template; environment overrides and explicit or legacy config may point elsewhere.

## Durable Hook And Worker

After installing the plugin, check that the hook is present:

```bash
agent-context-substrate codex-status
```

Expected mode includes `hook_support=supported`, `hook_primary=installed`, `trigger_strategy=hook-enqueue`, and `watcher_fallback=available`. Also inspect `queue_pending_count`, `queue_dead_letter_count`, `worker_status`, and `worker_last_error`. An idle worker with an empty queue is normal. Inspect failures with `agent-context-substrate codex-jobs list --status dead_letter`; after fixing the cause, use `agent-context-substrate codex-jobs retry --job-id ID` and run the printed worker command.

`doctor-codex` should also report `codex_plugin_registered=ok` when Codex CLI registry inspection is available. Plugin files on disk do not by themselves mean Codex has registered `agent-context-substrate@personal`.

The installed hook script is a thin bootstrap into the editable ACS Python package. Core Python changes apply through the editable install; changes to bundled hook/skill/plugin assets require `setup-codex --yes` again and may trigger another hook trust review.

## Watcher Fallback

`codex-watch` scans all eligible rollout history; it is an explicit recovery/backfill tool, not the durable queue worker. Never start it blindly against real data. Inspect the configured roots and use a conservative idle window first:

```bash
agent-context-substrate codex-watch --project-root . --wiki-root "$WIKI_PATH" --summary-mode auto --wiki-auto-mode apply-flexible --wiki-write-judge-mode auto
```

The watcher reads `~/.codex/state_5.sqlite` and `~/.codex/sessions/**/rollout-*.jsonl` read-only, waits for idle rollout files, then runs `codex-finalize`. To drain already queued Stop jobs manually, use `agent-context-substrate codex-worker --plugin-root <installed-plugin-root>` instead.

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
