# Claude Code Setup

[한국어](./CLAUDE_CODE_SETUP.ko.md) · [README](../README.md) · [Windows Codex setup](./WINDOWS_CODEX_APP_SETUP.md)

The Claude Code adapter runs the same flow as Codex: **Stop hook → durable queue → singleton worker → wiki and retrieval artifacts**. It works in the `claude` CLI and in the Claude desktop app's Code tab, since both load plugins and hooks from `~/.claude`.

## How it works

1. Claude Code runs the plugin's Stop hook after each turn with `session_id`, `transcript_path`, `cwd`, `hook_event_name`, and `stop_hook_active` on stdin.
2. `hooks/claude_stop_finalize.py` does nothing when `stop_hook_active` is true. Otherwise it records the transcript fingerprint (path, mtime, size) in `<PROJECT_ROOT>/data/index/claude_jobs.sqlite3`, launches a hidden `claude-worker`, and prints `{"continue": true, "suppressOutput": true}`. It never blocks the turn; errors become a `systemMessage` warning.
3. The worker runs `claude-finalize`, which parses `~/.claude/projects/<encoded cwd>/<session_id>.jsonl` into a `SessionBundle` (user and assistant text, tool calls, tool results; thinking, meta, and sidechain entries are dropped) and runs the shared finalize pipeline: raw export, context packet, v2 summaries, judge-guarded wiki writes, lint, and the recovery brief.
4. A newer stop supersedes older queued jobs for the same session. The worker re-checks the fingerprint and config digest before and after finalizing, retries transient failures, and dead-letters exhausted jobs. Claude and Codex workers share `codex_finalize.lock`, so only one adapter writes the wiki at a time.

Summaries use the configured LLM backend. With `summary_mode=auto` that is the Codex CLI named by `codex_cli_command`, with a heuristic fallback.

## 1. Write the adapter config

The config lives outside the plugin, because marketplace installs copy the plugin into `~/.claude/plugins/cache` and replace it on update:

```text
~/.claude/agent-context-substrate/local_config.json
```

From the ACS checkout, preview it, then write it:

```bash
agent-context-substrate setup-claude --project-root .
agent-context-substrate setup-claude --project-root . --yes
```

When a Codex ACS config exists, `setup-claude` copies its summary, wiki, worker, and workspace policy so both agents behave the same. Use `--from-codex off` to start from defaults and `--wiki-root PATH` to point at another vault. `ACS_CLAUDE_CONFIG` overrides the config path. `setup-claude` never edits `~/.claude/settings.json`.

## 2. Install the plugin from the local marketplace

The packaged assets directory is a local marketplace named `acs-local`:

```text
<ACS_CHECKOUT>/src/agent_context_substrate/assets/claude_plugin/
  .claude-plugin/marketplace.json
  agent-context-substrate/
    .claude-plugin/plugin.json
    hooks/hooks.json
    hooks/claude_stop_finalize.py
    skills/agent-context-substrate/SKILL.md
```

In an interactive `claude` session:

```text
/plugin marketplace add <ACS_CHECKOUT>/src/agent_context_substrate/assets/claude_plugin
/plugin install agent-context-substrate@acs-local
```

Without the CLI (for example, desktop app only), add the same entries to `~/.claude/settings.json` yourself, then restart the app:

```json
{
  "extraKnownMarketplaces": {
    "acs-local": {
      "source": {
        "source": "directory",
        "path": "C:/Users/<you>/path/to/agent-context-substrate/src/agent_context_substrate/assets/claude_plugin"
      }
    }
  },
  "enabledPlugins": {
    "agent-context-substrate@acs-local": true
  }
}
```

Merge these keys into the existing file; don't replace it.

The hook command is `python "${CLAUDE_PLUGIN_ROOT}/hooks/claude_stop_finalize.py"`, so `python` must be on `PATH` for the shell Claude Code uses for hooks. The script only bootstraps: it adds `python_path_entries` from the config to `sys.path` and imports the editable ACS package, so core Python changes apply without reinstalling. Changes to the bundled hook or skill files need `/plugin marketplace update acs-local`.

## 3. Check it

```bash
agent-context-substrate claude-status
agent-context-substrate claude-jobs list
```

After a stop, `claude_hook_events.jsonl` should show `enqueued` and later `finalized`, and `claude-status` should report `worker_status=idle` with `queue_pending_count=0`.

To fix a dead-lettered job:

```bash
agent-context-substrate claude-jobs list --status dead_letter
agent-context-substrate claude-jobs retry --job-id ID
agent-context-substrate claude-worker
```

Finalize one session by hand:

```bash
agent-context-substrate claude-finalize --session-id SESSION_ID --project-root . --wiki-root "$WIKI_PATH" --summary-mode auto
```

## Files

| Path | Purpose |
| --- | --- |
| `data/index/claude_jobs.sqlite3` | Durable Claude job queue |
| `data/index/claude_hook_events.jsonl` | Hook and worker decisions |
| `data/index/claude_worker_status.json` | Worker heartbeat |
| `data/exports/raw/claude/<session_id>.json` | Redacted raw session export |
| `data/exports/context_packets/<session_id>.json` | Context packet (provenance `claude-session:<id>#messages=…`) |

## Config keys

These are the Claude-specific keys. The rest (`summary_*`, `wiki_*`, `worker_*`, `llm_*`, `workspace_scope`, `allowed_workspace_roots`, `python_path_entries`) mean the same as in the Codex config.

| Key | Meaning |
| --- | --- |
| `project_root` | ACS artifact root (`data/` lives here) |
| `claude_home` | Claude config directory, used to find transcripts by session id |
| `python_executable` | Python that runs the worker and `claude-finalize` |
| `trigger_strategy` | `hook-enqueue` (default) or `hook-primary` (finalize inline) |
| `claude_hook_event_log_path` | Optional override for the event log |
