# Agent Context Substrate User Guide

This guide explains `agent-context-substrate` from a user point of view: what it does, when it helps, where data is stored, how to install it into Hermes Agent or the Windows Codex app, and how to use the CLI and Telegram commands.

The current release packages **Hermes Agent integration** and a **non-MCP Codex local session source**. The project name reflects the longer-term goal of supporting additional agent adapters; Claude Code/OpenCode/Gemini adapters are not included yet. The former project name was `hermes-llm-wiki-harness`.

[한국어 사용자 가이드](./USER_GUIDE.md) · [Windows Codex App Setup](./WINDOWS_CODEX_APP_SETUP.md) · [English README](../README.md) · [한국어 README](../README.ko.md)

## 1. What this tool does

`Agent Context Substrate` turns Hermes Agent and Codex conversations into reusable local knowledge artifacts and a judge-guarded LLM Wiki.

Instead of relying only on the live chat context, it can export a Hermes session, summarize it into a context packet, generate a recovery brief, and make the result searchable by Hermes later.

For packaged Codex installs, the default policy is **`apply-flexible` with a write judge**:

```text
Hermes state.db or Codex rollout JSONL
  -> raw session export
  -> evidence-backed Codex CLI summary
  -> context packet
  -> claim atoms / promotion candidates
  -> flexible wiki patch proposal
  -> write-judge decision
  -> approved LLM Wiki update or review-required proposal
  -> lint report
  -> recovery brief
  -> ledger
```

This means LLM Wiki content is not accumulated only when the user explicitly requests a write. Each eligible Codex thread can be evaluated by the Stop hook; the judge decides whether the evidence supports a wiki update. If the judge path is unavailable, confidence is too low, or patch safety checks fail, ACS keeps review-required artifacts under `data/...` and does not write the vault.

Standalone/Hermes packet building remains `packet-only` unless explicitly configured otherwise.

## 2. When it helps

This project is useful when:

- a long Hermes or Codex session was reset, stopped, or compressed and you need to recover the work context;
- you want a durable summary of what happened in a session;
- you want Hermes to search prior project knowledge while solving a new request;
- you use Obsidian for human-readable notes but do not want generated session pages to flood the vault;
- you want release checks that confirm wiki links, provenance, language metadata, and artifact consistency.

## 3. Storage layers

| Layer | Location | Format | Purpose |
| --- | --- | --- | --- |
| Hermes raw session DB | `HERMES_HOME/state.db` or `~/.hermes/state.db` | SQLite | Original sessions and messages |
| Codex local session source | `~/.codex/state_5.sqlite` and `~/.codex/sessions/**/rollout-*.jsonl` | SQLite / JSONL | Local Codex thread metadata and rollout events, read-only |
| Harness exports | `data/exports/` | JSON / Markdown | Raw exports, packets, evidence, v2 summaries, lint reports, recovery briefs |
| Harness atoms | `data/atoms/` | JSONL | Claim atoms extracted from packet evidence |
| Harness promotions | `data/promotions/` | JSON / Markdown | Review queue for possible wiki updates |
| Harness wiki patches | `data/wiki_patches/` | JSON / Markdown / JSONL | Reviewable patch proposals and applied patch log |
| Harness wiki decisions | `data/wiki_decisions/` | JSON | Write-judge decisions for automatic Codex wiki growth |
| Harness ledger/index | `data/index/` | JSON / Markdown | Processing status, topic maps, artifact paths, retry/idempotency records |
| Obsidian LLM Wiki | `WIKI_PATH` | Markdown | Human-facing semantic wiki updated by judge-approved patches |

For Windows Codex app users, call out these concrete paths before installing:

```text
Codex source SQLite:
%USERPROFILE%\.codex\state_5.sqlite

Codex rollout JSONL:
%USERPROFILE%\.codex\sessions\...\rollout-*.jsonl

Recommended LLM Wiki default template:
%USERPROFILE%\Documents\LLM Wiki

ACS artifacts:
<PROJECT_ROOT>\data\...
```

## 4. Default artifacts

A successful packaged Codex finalize normally creates:

```text
data/exports/<session_id>.json
data/exports/context_packets/<session_id>.json
data/exports/context_packets/<session_id>.md
data/exports/lint/<session_id>-lint.json
data/exports/lint/<session_id>-lint.md
data/exports/recovery/<session_id>.json
data/index/session_ledger.json

# Extra files when --summary-mode is used
data/exports/evidence/<session_id>/<micro_id>.json
data/exports/summaries/<packet_id>-micro-v2.json
data/exports/summaries/<packet_id>-unit-v2.json

data/atoms/claims.jsonl
data/promotions/<packet_id>.json
data/promotions/<packet_id>.md
data/wiki_patches/<packet_id>.json
data/wiki_patches/<packet_id>.md
data/wiki_decisions/<packet_id>.json
```

The ledger records the wiki automation mode and the write decision. A previous legacy `full` run is not incorrectly reused for a later `packet-only` request.

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

### 6.3 Rubric and optional templates

The LLM Wiki is a maintained markdown knowledge graph, not a strict form generator. Templates under `_system/templates` are examples for humans and agents, but page bodies may use whatever structure best integrates the new knowledge.

The durable contract is intentionally smaller than the example templates:

- preserve source material as the immutable ground truth;
- keep page paths safe and human-readable;
- include provenance or evidence for durable claims;
- keep useful wikilinks, index/log registration, and review state;
- surface uncertainty, contradictions, and open questions instead of hiding them.

```text
_system/templates/ko/home.md
_system/templates/ko/knowledge.md
_system/templates/ko/project.md
_system/templates/en/home.md
_system/templates/en/knowledge.md
_system/templates/en/project.md
```

When creating a new page manually:

1. choose a page type, such as `knowledge`, `idea`, `source`, `project`, `spec`, `plan`, or `decision`;
2. choose `ko` or `en`;
3. optionally copy a matching template as a starting point;
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

Language and section-shape issues are advisories. Blocking wiki lint remains focused on safety and graph integrity, such as provenance gaps, broken wikilinks, missing index entries, unsafe/generated page shapes, and internal artifact graph errors.

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

## 8. Install and enable Codex integration

Codex integration is hook-primary with watcher fallback. The packaged plugin keeps `.codex-plugin/plugin.json` free of MCP servers and manifest `hooks`, and ships the default Codex hook file at `hooks/hooks.json`. When the plugin hook is installed and trusted through Codex `/hooks`, the Stop hook finalizes the current thread, builds Codex CLI summaries, plans a flexible wiki patch, and lets the write judge decide whether to apply it. `codex-watch` remains the fallback for untrusted hooks, older runtimes, or missed Stop events.

Windows Codex app users should start with the [Windows setup guide](./WINDOWS_CODEX_APP_SETUP.md). The distribution PowerShell path is the one-shot bootstrap script:

```powershell
git clone https://github.com/jjuck/agent-context-substrate.git agent-context-substrate
cd agent-context-substrate
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
```

To opt into installing missing tools, use the winget package IDs `Python.Python.3.13`, `Git.Git`, and optional `Obsidian.Obsidian`.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -InstallMissingTools -InstallObsidian
```

After install, inspect health and paths:

```powershell
.\.venv\Scripts\agent-context-substrate.exe doctor-codex --fail-on-issues
.\.venv\Scripts\agent-context-substrate.exe config-codex paths
.\.venv\Scripts\agent-context-substrate.exe diagnose-codex
```

Use `setup-codex-wizard` for an interactive path review. `diagnose-codex --fix` repairs only safe ACS local files such as the wiki skeleton, Codex plugin Stop hook, and local config. The `~/.codex/hooks.json` user hook fallback is opt-in to avoid duplicate Stop hooks. `doctor-codex` reports PATH `codex` candidates and setup pins a detected direct `codex.exe` as `codex_cli_command`.

Codex still requires hook review/trust before non-managed hooks run. Restart the Codex app, open Settings > Hooks or `/hooks`, then trust/enable the ACS Stop hook.

After hook review, you can run the watcher fallback with the same wiki automation policy:

```powershell
.\.venv\Scripts\agent-context-substrate.exe codex-watch `
  --once `
  --codex-home $CodexHome `
  --project-root $ProjectRoot `
  --wiki-root $WikiRoot `
  --summary-mode auto `
  --wiki-auto-mode apply-flexible `
  --wiki-write-judge-mode auto `
  --idle-seconds 999999
```

Manual finalize:

```powershell
.\.venv\Scripts\agent-context-substrate.exe codex-finalize `
  --thread-id "<CODEX_THREAD_ID>" `
  --codex-home $CodexHome `
  --project-root $ProjectRoot `
  --wiki-root $WikiRoot `
  --summary-mode auto `
  --wiki-auto-mode apply-flexible `
  --wiki-write-judge-mode auto
```

Codex raw exports are written under `data/exports/raw/codex/<thread_id>.json`; packet, lint, recovery, ledger, retrieval, atoms, promotions, wiki patch, and wiki decision artifacts then use the same artifact layout as Hermes sessions.

New Codex installs default to `summary_mode=auto`, `wiki_auto_mode=apply-flexible`, `wiki_write_judge_mode=auto`, and `wiki_auto_min_score=0.85`. The `auto` path detects a usable Codex CLI, runs `codex exec` with read-only sandbox, `approval_policy=never`, `service_tier=fast`, low reasoning effort, `features.hooks=false`, and inline bounded JSON input, then validates the returned strict JSON before trusting it. Timeout, CLI failure, invalid JSON, or lint failure degrades to heuristic summaries and records `fallback_from` / `fallback_reason` in summary metadata and the finalize ledger. Wiki write judge failure or low score degrades to a review-required decision artifact. Run `doctor-codex --summary-smoke` when you want an explicit signed-in `codex exec` smoke. If doctor reports `service_tier="default"` in Codex `config.toml`, remove that value or set a supported tier such as `fast` or `flex`.

Credential choices:

| Option | Use it when | Notes |
| --- | --- | --- |
| `codex-cli` / `auto` | You already use Codex CLI/App locally. | Reuses Codex auth through the CLI; ACS does not read or store Codex OAuth tokens. |
| `custom-command` | You have a trusted local summarizer command. | The command owns auth, API usage, schema correctness, and safety controls. |
| OpenAI Platform API key | You are running CI or non-Codex automation. | Explicit key provisioning and API billing are separate from Codex login. |
| Direct Codex OAuth | Avoid for ACS. | It would make ACS responsible for token lifecycle and private endpoint stability. |
| Codex Python SDK | Consider later for app-server integrations. | The current backend uses `codex exec` first because its automation flags are stable and explicit. |

## 9. Plugin configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT` | installed `local_config.py` or `~/.hermes/agent-context-substrate` | Harness package and `data/` root |
| `AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT` | runtime override before `WIKI_PATH`, installed `local_config.json`, then `%USERPROFILE%\Documents\LLM Wiki` template | Obsidian wiki root |
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

## 10. Telegram commands

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

Manually finalizes a specific Hermes session. With default Hermes plugin settings, it uses `packet-only`.

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

## 11. Request-time retrieval

When `context.engine: agent_context_substrate` is active, Hermes can use read-only retrieval while solving a user request.

Search order:

1. Obsidian durable wiki pages
2. context packet JSON artifacts
3. unit and micro summary fields inside packet JSON
4. raw Hermes `state.db` evidence when explicitly needed
5. raw Codex exports after `codex-finalize`

Default excluded paths:

- `.obsidian/`
- `_system/`
- `90 보관/`

Retrieval is read-only. Searching and expanding hits does not edit Obsidian.

## 12. Direct CLI usage

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

### Finalize Codex sessions

```bash
agent-context-substrate codex-status --codex-home ~/.codex

agent-context-substrate codex-finalize \
  --thread-id <thread_id> \
  --codex-home ~/.codex \
  --project-root . \
  --wiki-root '<WIKI_ROOT>'

agent-context-substrate codex-watch \
  --codex-home ~/.codex \
  --project-root . \
  --wiki-root '<WIKI_ROOT>' \
  --once
```

### Search and expand knowledge

```bash
agent-context-substrate search-knowledge \
  --query "<query>" \
  --mode knowledge \
  --project-root . \
  --wiki-root '<WIKI_ROOT>'

agent-context-substrate expand-hit \
  --hit-id <hit_id> \
  --project-root . \
  --wiki-root '<WIKI_ROOT>'
```

### Run wiki lint

```bash
export WIKI_PATH='<WIKI_ROOT>'

agent-context-substrate lint-wiki \
  --project-root . \
  --report-id wiki-lint
```

### Build v2 summary artifacts

The default `build-context-packet` remains backward-compatible. Add `--summary-mode` when you want evidence bundles and v2 summary artifacts.

```bash
agent-context-substrate build-context-packet \
  --session-id <session_id> \
  --packet-id <packet_id> \
  --task-title "<task title>" \
  --macro-context "<macro context>" \
  --unit-title "<unit title>" \
  --goal "<goal>" \
  --summary-mode heuristic \
  --summary-cache on \
  --project-root .
```

Summary modes:

| Mode | Meaning |
| --- | --- |
| `heuristic` | Offline deterministic backend; no keys, network, or model cost. |
| `agent-llm` | Uses the host Agent's LLM router when the integration provides one. |
| `hybrid` | Heuristic evidence spine plus Agent LLM interpretation. |
| `custom-command` | External command receives stdin JSON and returns stdout JSON. |
| `codex-cli` | Runs `codex exec` with read-only sandbox, `approval_policy=never`, `service_tier=fast`, low reasoning effort, hooks disabled, inline bounded JSON input, JSONL output, and ACS schema/lint validation. |
| `auto` | Prefers `codex-cli` when Codex CLI is available and otherwise records heuristic fallback metadata. |

Note: standalone CLI can run `heuristic`, `custom-command`, `codex-cli`, and `auto` directly. `agent-llm` and `hybrid` require a host integration that injects an Agent LLM router.

Summary judge evaluation is opt-in and artifact-only:

```bash
agent-context-substrate build-context-packet \
  --summary-mode heuristic \
  --summary-judge-mode hybrid \
  --project-root .
```

In host integrations, `hybrid` judge mode reuses the Agent LLM router and writes `data/exports/evals/<packet_id>-summary-judge.json`. It judges recovery usefulness, hallucination risk, missing next steps, and wiki-candidate noise without rewriting summaries or applying wiki patches.

### Judge-gated wiki growth

```bash
agent-context-substrate extract-atoms --packet-id <packet_id> --project-root .
agent-context-substrate propose-promotions --packet-id <packet_id> --project-root .
agent-context-substrate plan-wiki-patches \
  --promotion-file data/promotions/<packet_id>.json \
  --wiki-root '<WIKI_ROOT>' \
  --project-root .
```

The packaged Codex automation uses rubric-guided flexible integration by default. The standalone `plan-wiki-patches` command still preserves the legacy managed-claim-block behavior unless you opt in explicitly:

```bash
agent-context-substrate plan-wiki-patches \
  --promotion-file data/promotions/<packet_id>.json \
  --write-mode flexible \
  --wiki-root '<WIKI_ROOT>' \
  --project-root .
```

These manual commands do not edit Obsidian. After reviewing the generated Markdown/JSON proposal, apply explicitly:

```bash
agent-context-substrate apply-wiki-patch \
  --patch-file data/wiki_patches/<packet_id>.json \
  --wiki-root '<WIKI_ROOT>' \
  --project-root . \
  --apply
```

Flexible proposals are proposal-only unless their metadata includes an approved semantic judge verdict. The mechanical write policy still checks safe target paths, evidence, current page hash, and dry-run/apply intent before writing.

## 13. What is automatic

Packaged Codex installs automatically process eligible stopped threads through summaries, atoms, promotions, flexible wiki proposals, and write-judge decisions. They apply the LLM Wiki patch only when the judge approves and safety checks pass.

Codex automation still skips:

- sessions with `source=gateway`;
- sessions shorter than `min_message_count`;
- sessions matching skip title patterns;
- sessions already completed with existing required artifacts;

Standalone/Hermes packet workflows do not automatically modify Obsidian unless explicitly configured. Obsidian can be modified by:

- packaged Codex `apply-flexible` automation with an approved write-judge decision;
- legacy `promotion_mode="full"`;
- `run-e2e-pipeline`;
- `promote-*` CLI commands;
- `apply-wiki-patch --apply`;
- manual curated page editing.

## 14. Privacy and release notes

Agent Context Substrate works with local private data.

- `HERMES_HOME/state.db` can contain full conversations, tool output, file paths, and operational context.
- Codex `%USERPROFILE%\.codex\state_5.sqlite` and rollout JSONL files can contain thread metadata, messages, tool calls, and local paths.
- `data/exports/**/*.json` and `data/exports/**/*.md` can contain raw transcripts or detailed summaries.
- Obsidian pages and provenance links may contain personal or organizational information.
- Never commit API keys, tokens, passwords, connection strings, `.env` files, or raw private session exports.
- Before public distribution, check `git status --short`, `.gitignore`, `docs/RELEASE_CHECKLIST.md`, `doctor`, and `fresh-install-smoke`.

## 15. Safety mechanisms

- ledger-based idempotency
- completed artifact existence checks
- stale completed record rebuilds
- failed record retry budget
- retry exhaustion stop condition
- partial artifact preservation after late failures
- Codex judge-gated `apply-flexible` default
- standalone/Hermes `packet-only` default
- gateway source excluded by default
- qualitative lint
- summary lint and fallback
- write-judge score threshold and review-required fallback
- promotion/wiki patch semantic lint
- read-only retrieval by default
- dry-run wiki patches by default

## 16. Troubleshooting

| Symptom | Check | Fix direction |
| --- | --- | --- |
| `/harness` shows `degraded` | project/wiki paths, import error | Check paths and Hermes venv/plugin setup |
| `/wiki-lint` reports `Missing language` | page frontmatter | Add `lang: ko` or `lang: en` |
| `/wiki-lint` reports broken links | wikilink targets | Fix link or create target page |
| `/packet` only says `reused` | ledger completed record | Usually normal; different promotion modes reprocess separately |
| New settings do not appear in Telegram | gateway process cache | Restart the gateway |
| Auto-finalize does not run | source, message count, policy | Check `allowed_sources`, `min_message_count`, and session source |

## 17. Generic path example

```text
Hermes DB:
~/.hermes/state.db

Codex source:
%USERPROFILE%\.codex\state_5.sqlite
%USERPROFILE%\.codex\sessions\...\rollout-*.jsonl

Harness project:
<PROJECT_ROOT>

Obsidian LLM Wiki:
%USERPROFILE%\Documents\LLM Wiki default template, or explicit <WIKI_ROOT>

Recommended Codex wiki mode:
apply-flexible with wiki_write_judge_mode=auto

Standalone/Hermes promotion mode:
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
