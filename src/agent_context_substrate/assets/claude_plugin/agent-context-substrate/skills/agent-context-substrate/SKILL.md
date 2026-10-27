---
name: agent-context-substrate
description: Use when working in Claude Code and the user wants Claude Code sessions finalized into Agent Context Substrate, wants to check the ACS queue/worker, or wants to search ACS knowledge (wiki, packets, recovery briefs) without MCP.
---

# Agent Context Substrate For Claude Code

Use the local CLI rather than MCP.

## Status

First check the integration state:

```bash
agent-context-substrate claude-status
```

The plugin's Stop hook is the primary trigger. On each stop it reads the hook input (`session_id`, `transcript_path`, `cwd`), records the transcript fingerprint in `<PROJECT_ROOT>/data/index/claude_jobs.sqlite3`, launches a hidden singleton `claude-worker`, and returns at once. The hook never blocks the turn: failures surface only as a `systemMessage` warning, and it does nothing when `stop_hook_active` is true.

The worker runs `claude-finalize`, retries transient failures, and dead-letters exhausted jobs. It shares the finalize lock with the Codex adapter, so only one agent writes the wiki at a time.

Config lives outside the plugin at `~/.claude/agent-context-substrate/local_config.json` (override with `ACS_CLAUDE_CONFIG`). `setup-claude --yes` writes it and copies summary, wiki, and worker policy from the Codex ACS config when one exists. `project_root` is the ACS artifact root, not a workspace allowlist.

Summaries use the configured LLM backend (`summary_mode=auto` uses the Codex CLI given by `codex_cli_command`, then falls back to heuristics). Wiki writes follow `wiki_auto_mode` and the write judge exactly as for Codex sessions.

## Queue And Worker

```bash
agent-context-substrate claude-jobs list --status dead_letter
agent-context-substrate claude-jobs retry --job-id ID
agent-context-substrate claude-worker
```

Hook decisions are logged to `<PROJECT_ROOT>/data/index/claude_hook_events.jsonl`; worker heartbeat is in `claude_worker_status.json` next to it.

## Manual Finalize

```bash
agent-context-substrate claude-finalize --session-id SESSION_ID --project-root . --wiki-root "$WIKI_PATH" --summary-mode auto --wiki-auto-mode apply-flexible --wiki-write-judge-mode auto
```

`--transcript-path` is optional; without it ACS looks under `~/.claude/projects/*/<SESSION_ID>.jsonl`.

## Retrieval

Search durable knowledge:

```bash
agent-context-substrate search-knowledge --query "topic" --mode knowledge --project-root . --wiki-root "$WIKI_PATH"
```

Expand a hit:

```bash
agent-context-substrate expand-hit --hit-id HIT_ID --project-root . --wiki-root "$WIKI_PATH"
```
