# Agent Context Substrate User Guide

This guide explains `agent-context-substrate` from a user point of view: what it does, when it helps, where data is stored, how to install it into Hermes Agent, and how to use the CLI and Telegram commands.

The current release packages **Hermes Agent integration only**. The project name reflects the longer-term goal of supporting additional agent adapters, but Claude Code/Codex/OpenCode/Gemini adapters are not included yet. The former project name was `hermes-llm-wiki-harness`.

[한국어 사용자 가이드](./USER_GUIDE.md) · [English README](../README.md) · [한국어 README](../README.ko.md)

## 1. What this tool does

`Agent Context Substrate` turns Hermes Agent conversations into reusable local knowledge artifacts.

Instead of relying only on the live chat context, it can export a Hermes session, summarize it into a context packet, generate a recovery brief, and make the result searchable by Hermes later.

The default session-finalize policy is **`packet-only`**.

```text
Hermes state.db
  -> raw session export
  -> micro/unit summary
  -> context packet
  -> lint report
  -> recovery brief
  -> ledger
```

This means the default automation does **not** write generated query/concept/plan/architecture pages into Obsidian. Obsidian stays a human-facing semantic wiki. Machine-oriented artifacts stay in the harness project under `data/exports/` and `data/index/`.

## 2. When it helps

This project is useful when:

- a long Hermes session was reset or compressed and you need to recover the work context;
- you want a durable summary of what happened in a session;
- you want Hermes to search prior project knowledge while solving a new request;
- you use Obsidian for human-readable notes but do not want generated session pages to flood the vault;
- you want release checks that confirm wiki links, provenance, language metadata, and artifact consistency.

## 3. Storage layers

| Layer | Location | Format | Purpose |
| --- | --- | --- | --- |
| Hermes raw session DB | `HERMES_HOME/state.db` or `~/.hermes/state.db` | SQLite | Original sessions and messages |
| Harness exports | `data/exports/` | JSON / Markdown | Raw exports, packets, lint reports, recovery briefs |
| Harness ledger | `data/index/session_ledger.json` | JSON | Processing status, artifact paths, retry/idempotency records |
| Obsidian LLM Wiki | `WIKI_PATH` | Markdown | Human-facing curated wiki |

## 4. Default artifacts

A successful `packet-only` finalize normally creates:

```text
data/exports/<session_id>.json
data/exports/context_packets/<session_id>.json
data/exports/context_packets/<session_id>.md
data/exports/lint/<session_id>-lint.json
data/exports/lint/<session_id>-lint.md
data/exports/recovery/<session_id>.json
data/index/session_ledger.json
```

The ledger also records `promotion_mode`. A previous `full` run is not incorrectly reused for a later `packet-only` request.

## 5. Obsidian wiki structure

Recommended vault layout:

```text
LLM Wiki/
  Home.md
  index.md              # compatibility catalog for harness lint
  SCHEMA.md
  log.md
  01 지식/
  02 내 아이디어/
  03 인물과 조직/
  04 프로젝트/
  05 계획/
  06 원천 자료/
  90 보관/
  _system/
    config.yaml
    templates/
      ko/
      en/
    styles/
      llm-wiki.css
```

The folder names can stay Korean because they are part of the human-facing wiki convention. Machine-readable classification is handled by Markdown frontmatter.

## 6. Language settings

The human-facing wiki supports `ko` and `en`.

### 6.1 Vault language config

```yaml
# <WIKI_PATH>/_system/config.yaml
wiki:
  default_language: ko
  supported_languages: [ko, en]
  filename_language: ko
  template_language: ko
  source_language_preserve: true
```

| Field | Meaning |
| --- | --- |
| `default_language` | Default language for new human-facing pages |
| `supported_languages` | Language codes accepted by lint |
| `filename_language` | Naming convention for generated or template-based page filenames |
| `template_language` | Default template language |
| `source_language_preserve` | Whether source material should preserve its original language |

### 6.2 Page frontmatter

Every active human-facing page should include `lang`.

```yaml
---
title: Context Packet
lang: en
type: knowledge
category: knowledge
status: active
tags: [context, hermes, recovery]
---
```

Korean pages use `lang: ko`; English pages use `lang: en`.

### 6.3 Language-specific templates

```text
_system/templates/ko/home.md
_system/templates/ko/knowledge.md
_system/templates/ko/project.md
_system/templates/en/home.md
_system/templates/en/knowledge.md
_system/templates/en/project.md
```

When creating a new page:

1. choose a page type, such as `knowledge`, `idea`, `source`, `project`, `spec`, `plan`, or `decision`;
2. choose `ko` or `en`;
3. copy the matching template;
4. fill in `title`, `lang`, `type`, `category`, `status`, and `tags`.

### 6.4 Language lint

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate
.venv/bin/agent-context-substrate lint-wiki \
  --project-root '<PROJECT_ROOT>' \
  --report-id language-check
```

Language issues appear in the `Human-Facing Quality` section as:

- `Missing language`
- `Unsupported language`

## 7. Install and enable Hermes integration

Hermes integration has two parts:

1. `agent-context-substrate` user plugin: session-finalize hooks and Telegram commands such as `/harness`, `/packet`, `/wiki-resume`, and `/wiki-lint`.
2. `agent_context_substrate` context engine: retrieval tools such as `wiki_recovery_context`, `wiki_knowledge_search`, and `wiki_knowledge_expand`.

Replace these placeholders before running commands.

| Placeholder | Meaning |
| --- | --- |
| `<PROJECT_ROOT>` | Harness project/data root |
| `<WIKI_ROOT>` | Obsidian LLM Wiki vault root |
| `<HERMES_AGENT_ROOT>` | Hermes Agent root, for example `~/.hermes/hermes-agent` |

### 7.1 Run the packaged installer

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate

.venv/bin/agent-context-substrate init-wiki \
  --wiki-root '<WIKI_ROOT>'

.venv/bin/agent-context-substrate install-plugin \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

.venv/bin/agent-context-substrate install-context-engine \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

.venv/bin/agent-context-substrate doctor \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --fail-on-issues
```

`install-plugin` writes `<PROJECT_ROOT>` and `<WIKI_ROOT>` into `~/.hermes/plugins/agent-context-substrate/local_config.py`. `install-context-engine` also writes a local config beside the installed context engine. These files are local machine configuration, not public templates.

### 7.2 Enable the plugin

```bash
cd '<HERMES_AGENT_ROOT>'
. venv/bin/activate
hermes plugins enable agent-context-substrate
```

Expected config shape:

```yaml
plugins:
  enabled:
    - agent-context-substrate
```

### 7.3 Select the context engine

Set Hermes config to use the Agent Context Substrate context engine.

```yaml
context:
  engine: agent_context_substrate
```

This enables these tools inside Hermes:

```text
wiki_recovery_context
wiki_knowledge_search
wiki_knowledge_expand
```

### 7.4 Restart the gateway

If the Telegram gateway is already running, restart it after plugin or context-engine changes.

```text
/restart
```

or from a shell:

```bash
cd '<HERMES_AGENT_ROOT>'
. venv/bin/activate
hermes gateway restart
```

## 8. Plugin configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT` | installed `local_config.py` or `~/.hermes/agent-context-substrate` | Harness package and `data/` root |
| `AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT` | installed `local_config.py` or `~/LLM Wiki` | Obsidian wiki root |
| `AGENT_CONTEXT_SUBSTRATE_AUTO_FINALIZE` | `true` | Enable automatic session finalize |
| `AGENT_CONTEXT_SUBSTRATE_MIN_MESSAGE_COUNT` | `3` | Skip sessions that are too short |
| `AGENT_CONTEXT_SUBSTRATE_ALLOWED_SOURCES` | `telegram,cli` | Raw session sources eligible for automation |
| `AGENT_CONTEXT_SUBSTRATE_GATEWAY_POLICY` | `trigger-only` | Treat gateway hooks as non-blocking triggers/backstops |
| `AGENT_CONTEXT_SUBSTRATE_PROMOTION_MODE` | `packet-only` | `packet-only` or legacy `full` |
| `AGENT_CONTEXT_SUBSTRATE_SKIP_TITLE_PATTERNS` | empty | Comma-separated title patterns to skip |

Recommended defaults:

```text
AGENT_CONTEXT_SUBSTRATE_PROMOTION_MODE=packet-only
AGENT_CONTEXT_SUBSTRATE_ALLOWED_SOURCES=telegram,cli
AGENT_CONTEXT_SUBSTRATE_GATEWAY_POLICY=trigger-only
```

## 9. Telegram commands

### `/harness`

Shows plugin health and configuration.

```text
/harness
```

Healthy output includes:

```text
Agent Context Substrate plugin status
- health: ok
- project_root exists: True
- wiki_root exists: True
- harness_importable: True
- auto_finalize_enabled: True
- min_message_count: 3
- allowed_sources: telegram, cli
- promotion_mode: packet-only
- gateway_policy: trigger-only
- gateway source auto-finalize: disabled
```

### `/packet <session_id>`

Manually finalizes a specific session. With default settings, it uses `packet-only`.

```text
/packet 20260424_122938_c308ad
```

### `/wiki-resume <session_id>`

Shows the recovery brief for a specific session.

```text
/wiki-resume 20260424_122938_c308ad
```

### `/wiki-lint`

Checks the Obsidian human-facing wiki and packet artifact graph.

```text
/wiki-lint
```

## 10. Request-time retrieval

When `context.engine: agent_context_substrate` is active, Hermes can use read-only retrieval while solving a user request.

Search order:

1. Obsidian durable wiki pages
2. context packet JSON artifacts
3. unit and micro summary fields inside packet JSON
4. raw Hermes `state.db` evidence when explicitly needed

Default excluded paths:

- `.obsidian/`
- `_system/`
- `90 보관/`

Retrieval is read-only. Searching and expanding hits does not edit Obsidian.

## 11. Direct CLI usage

### Export a raw session

```bash
agent-context-substrate extract-session \
  --session-id <session_id> \
  --project-root .
```

### Build a context packet

```bash
agent-context-substrate build-context-packet \
  --session-id <session_id> \
  --packet-id <packet_id> \
  --task-title "<task title>" \
  --macro-context "<macro context>" \
  --unit-title "<unit title>" \
  --goal "<goal>" \
  --project-root .
```

### Run wiki lint

```bash
export WIKI_PATH='<WIKI_ROOT>'

agent-context-substrate lint-wiki \
  --project-root . \
  --report-id wiki-lint
```

## 12. What is not automatic

The default policy does not automatically process:

- sessions with `source=gateway`;
- sessions shorter than `min_message_count`;
- sessions matching skip title patterns;
- sessions already completed with existing required artifacts;
- Obsidian durable page promotion when `promotion_mode=packet-only`.

Obsidian is modified only by:

- legacy `promotion_mode="full"`;
- `run-e2e-pipeline`;
- `promote-*` CLI commands;
- manual curated page editing.

## 13. Privacy and release notes

Agent Context Substrate works with local private data.

- `HERMES_HOME/state.db` can contain full conversations, tool output, file paths, and operational context.
- `data/exports/**/*.json` and `data/exports/**/*.md` can contain raw transcripts or detailed summaries.
- Obsidian pages and provenance links may contain personal or organizational information.
- Never commit API keys, tokens, passwords, connection strings, `.env` files, or raw private session exports.
- Before public distribution, check `git status --short`, `.gitignore`, `docs/RELEASE_CHECKLIST.md`, `doctor`, and `fresh-install-smoke`.

## 14. Safety mechanisms

- ledger-based idempotency
- completed artifact existence checks
- stale completed record rebuilds
- failed record retry budget
- retry exhaustion stop condition
- partial artifact preservation after late failures
- `packet-only` default
- gateway source excluded by default
- qualitative lint
- read-only retrieval by default

## 15. Troubleshooting

| Symptom | Check | Fix direction |
| --- | --- | --- |
| `/harness` shows `degraded` | project/wiki paths, import error | Check paths and Hermes venv/plugin setup |
| `/wiki-lint` reports `Missing language` | page frontmatter | Add `lang: ko` or `lang: en` |
| `/wiki-lint` reports broken links | wikilink targets | Fix link or create target page |
| `/packet` only says `reused` | ledger completed record | Usually normal; different promotion modes reprocess separately |
| New settings do not appear in Telegram | gateway process cache | Restart the gateway |
| Auto-finalize does not run | source, message count, policy | Check `allowed_sources`, `min_message_count`, and session source |

## 16. Generic path example

```text
Hermes DB:
~/.hermes/state.db

Harness project:
<PROJECT_ROOT>

Obsidian LLM Wiki:
<WIKI_ROOT>

Recommended promotion mode:
packet-only

Automatic sources:
telegram, cli

Gateway policy:
trigger-only
```

If the project is under a Windows-mounted WSL path, prefer changing directory inside the shell command instead of relying on tool `workdir` behavior.

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest -q
```
