<div align="center">

# Agent Context Substrate

**Turn Hermes and Codex sessions into reusable context packets, recovery briefs, request-time retrieval, and a judge-guarded LLM Wiki.**

![Status](https://img.shields.io/badge/status-public%20alpha-orange) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) [![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

[한국어 README](./README.ko.md) · [Quick Start](#quick-start) · [Windows Codex App](#windows-codex-app-quick-install) · [Hermes Install](#install-into-hermes) · [Verified Baseline](#verified-baseline) · [CLI](#cli-commands) · [Privacy](#privacy-and-safety) · [User Guide EN](./docs/USER_GUIDE.en.md) · [Windows Setup](./docs/WINDOWS_CODEX_APP_SETUP.md)

</div>

## Overview

`agent-context-substrate` is a Python package and CLI for building a durable context and retrieval substrate from AI-agent sessions.
The current packaged adapters support **Hermes Agent** and a **non-MCP Codex local session source**. Hermes reads `state.db`; Codex reads `~/.codex/state_5.sqlite` plus `~/.codex/sessions/**/rollout-*.jsonl` read-only. Both paths export raw sessions, build context packets, write recovery briefs, and feed the same local retrieval substrate.

This project was formerly named `hermes-llm-wiki-harness`. The rename reflects the longer-term goal: support more agents through additional adapters while keeping Hermes Agent as the first working reference integration and Codex as the new primary non-MCP path.

The packaged Windows Codex install treats the LLM Wiki as a living knowledge graph maintained by the LLM, not as a manual-only afterthought. By default it finalizes eligible Codex threads with `summary_mode=auto`, plans flexible wiki integration, asks a write-judge LLM whether the evidence is strong enough, and applies approved `apply-flexible` patches to the user's LLM Wiki. If the judge is unavailable, the confidence is too low, or the patch fails safety checks, ACS records a review-required proposal under `data/...` instead of writing the vault.

The default Codex knowledge-growth path is evidence-first and judge-gated:

```text
ContextPacket
  -> EvidenceBundle
  -> MicroSummaryV2 / UnitSummaryV2
  -> claim atoms
  -> promotion candidates
  -> flexible wiki patch proposal
  -> write-judge decision
  -> approved LLM Wiki update or review-required proposal
```

`ContextPacket` files remain raw material, not durable wiki pages by themselves. The Codex Stop hook decides per thread whether that material should become LLM Wiki content, so the wiki can grow without the user explicitly asking for each individual write.

## Why this helps

Long AI-agent sessions often contain decisions, file paths, test results, and next steps that are hard to recover after a reset or context compression. This harness makes that work reusable:

- **Resume interrupted work** with a compact recovery brief instead of rereading the whole transcript.
- **Search prior project knowledge** while Hermes is handling a new request.
- **Grow an LLM Wiki deliberately** by writing only evidence-backed, judge-approved updates and keeping all intermediate artifacts auditable.
- **Audit release readiness** with lint reports for wiki links, provenance, language metadata, and internal packet consistency.
- **Avoid duplicate processing** through a ledger that records completed, failed, retried, and reused session artifacts.

```text
Hermes state.db or Codex rollout JSONL
  -> raw session export
  -> context packet JSON / Markdown
  -> optional v2 evidence + structured summaries
  -> optional claim atoms / promotion candidates / wiki patch proposals
  -> optional write-judge decision and guarded LLM Wiki apply
  -> lint report JSON / Markdown
  -> recovery brief JSON
  -> session ledger
  -> optional read-only retrieval by Hermes tools
```

## Quick facts

| Item | Value |
| --- | --- |
| Status | Public alpha; v0.2.0 local release candidate; Hermes Agent plus non-MCP Codex local integration |
| Runtime | Python 3.11+ |
| Main interface | CLI: `agent-context-substrate` |
| Current agent support | Hermes Agent and Codex local sessions |
| Hermes integration | user plugin `agent-context-substrate` + context engine `agent_context_substrate` |
| Codex integration | `codex-finalize`, `codex-watch`, `codex-status`, and non-MCP packaged Codex plugin skill |
| Planned adapter direction | Additional agents such as Claude Code, OpenCode, or Gemini can be added later; they are not packaged yet. |
| Default output | `data/exports/`, `data/index/session_ledger.json` |
| Default Codex install policy | `summary_mode=auto`, `wiki_auto_mode=apply-flexible`, `wiki_write_judge_mode=auto`, `wiki_auto_min_score=0.85` |
| Standalone/Hermes promotion mode | `packet-only` unless explicitly configured otherwise |
| Optional summary modes | `heuristic`, `agent-llm`, `hybrid`, `custom-command`, `codex-cli`, `auto` via `--summary-mode` |
| Recommended wiki growth | atoms -> promotion candidates -> flexible patch proposal -> write judge -> apply or review |
| Legacy wiki promotion | Explicit `promotion_mode="full"` or `promote-*` CLI only |
| Wiki role | Human-facing semantic Obsidian vault maintained through evidence and judge decisions |
| Wiki languages | `ko`, `en` via `lang` frontmatter and `_system/config.yaml` |
| License | MIT |

## Key features

- Export one Hermes session from `HERMES_HOME/state.db` into raw JSON.
- Export one Codex thread from `~/.codex/state_5.sqlite` and rollout JSONL into raw JSON.
- Build heuristic `MicroSummary`, `UnitSummary`, and `ContextPacket` artifacts.
- Optionally export evidence bundles plus `MicroSummaryV2` / `UnitSummaryV2` artifacts with separated recovery, knowledge, and retrieval summaries.
- Use pluggable summary backends: default heuristic, host Agent LLM, hybrid, custom command, or Codex CLI.
- Extract claim atoms, propose promotion candidates, and plan guarded wiki patches.
- Let the packaged Codex Stop hook apply flexible LLM Wiki updates by default when the write judge approves them.
- Generate compact recovery briefs for resume workflows.
- Maintain a ledger for idempotency, stale-artifact rebuilds, retry budgets, and partial-failure diagnostics.
- Keep live Obsidian clean by requiring evidence, target safety, judge approval, and page-hash guards before automatic writes.
- Initialize a human-facing LLM Wiki skeleton with Korean/English templates.
- Install packaged Hermes user-plugin and context-engine assets into a Hermes Agent environment.
- Install a packaged non-MCP Codex plugin asset whose Stop hook finalizes Codex threads, with watcher fallback still available.
- Run `doctor` and `fresh-install-smoke` checks for distribution validation.
- Build graph-style topic maps from wiki pages and substrate artifacts.
- Expose request-time retrieval through Hermes context-engine tools:
  - `wiki_recovery_context`
  - `wiki_knowledge_search`
  - `wiki_knowledge_expand`

## Quick start

For Windows Codex app users, skip to [Windows Codex app quick install](#windows-codex-app-quick-install). The command block below is the developer smoke path.

```bash
git clone https://github.com/jjuck/agent-context-substrate.git agent-context-substrate
cd agent-context-substrate
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
python -m pytest -q
.venv/bin/agent-context-substrate --help
```

Expected: tests pass and `--help` shows the distribution commands (`init-wiki`, `install-plugin`, `install-codex-plugin`, `setup-codex`, `setup-codex-wizard`, `doctor-codex`, `diagnose-codex`, `config-codex`, `install-context-engine`, `doctor`, `fresh-install-smoke`) as well as the Codex, packet, promotion, and lint commands.

## Windows Codex app quick install

Use this path when the user has the Windows Codex app and wants ACS to finalize local Codex threads automatically. A fresh Codex thread can follow this from the GitHub repo URL alone.

Before installing, make these paths explicit to the user:

| Path | Default on Windows | Used for |
| --- | --- | --- |
| Codex SQLite | `%USERPROFILE%\.codex\state_5.sqlite` | Read-only Codex thread metadata |
| Codex rollouts | `%USERPROFILE%\.codex\sessions\...\rollout-*.jsonl` | Read-only Codex event streams |
| LLM Wiki | `%USERPROFILE%\Documents\LLM Wiki` default template | Human-facing Obsidian wiki updated by judge-approved patches; setup stores this as a portable template unless `--wiki-root` is explicit |
| ACS project data | `<PROJECT_ROOT>\data\...` | Generated raw exports, packets, recovery, ledger, retrieval, wiki proposals, and judge decisions |

Single-command PowerShell install:

```powershell
git clone https://github.com/jjuck/agent-context-substrate.git agent-context-substrate
cd agent-context-substrate
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
```

To let the script install missing prerequisites with winget, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -InstallMissingTools -InstallObsidian
```

The winget package IDs are `Python.Python.3.13`, `Git.Git`, and optional `Obsidian.Obsidian`.

If plain `codex` resolves to an npm shim such as `%APPDATA%\npm\codex.ps1`, use the direct `codex.exe` path reported by `setup-codex` or `doctor-codex`. Setup reports PATH candidates, checks known `%LOCALAPPDATA%\Programs\OpenAI\Codex\bin` and `%LOCALAPPDATA%\OpenAI\Codex\bin` locations, and pins a detected direct CLI into `local_config.json` as `codex_cli_command`.

After install:

```powershell
.\.venv\Scripts\agent-context-substrate.exe doctor-codex --fail-on-issues
.\.venv\Scripts\agent-context-substrate.exe config-codex paths
```

Default `setup-codex` writes `summary_mode=auto`, `wiki_auto_mode=apply-flexible`, `wiki_write_judge_mode=auto`, and `wiki_auto_min_score=0.85` into the installed Codex plugin `local_config.json`. That means the Stop hook asks Codex CLI to produce evidence-backed summaries and then asks a write judge whether a flexible LLM Wiki patch should be applied. No OpenAI Platform API key is required; ACS uses the signed-in Codex runtime and falls back to review-required artifacts if the judge path cannot run cleanly.

Run `doctor-codex --summary-smoke` to opt in to a brief signed-in `codex exec` check. If doctor reports `service_tier="default"` in `%USERPROFILE%\.codex\config.toml`, remove that line or use `fast`/`flex`.

For troubleshooting:

```powershell
.\.venv\Scripts\agent-context-substrate.exe diagnose-codex
.\.venv\Scripts\agent-context-substrate.exe diagnose-codex --fix
```

For an interactive path review:

```powershell
.\.venv\Scripts\agent-context-substrate.exe setup-codex-wizard
```

Codex still requires one human hook review before non-managed command hooks run. Restart the Codex app, open bottom-left Settings > Hooks, or open Codex CLI and enter `/hooks`. Review the ACS command, then choose `Trust all and continue` or the equivalent trust/enable action. This is separate from Full Access or approval-mode settings. A real smoke test should show `Running Stop hook: Finalizing Codex thread into Agent Context Substrate`, append `status=finalized` to `data\index\codex_hook_events.jsonl`, and produce a `search-knowledge --mode recovery` hit. See the full [Windows Codex app setup guide](./docs/WINDOWS_CODEX_APP_SETUP.md), including a prompt that a fresh Codex thread can follow from the GitHub repo alone.

## Install into Hermes

Use these commands when installing the package-managed integration assets into a Hermes Agent setup.
Replace placeholders before running:

- `<PROJECT_ROOT>`: this repository checkout or installed harness project root
- `<WIKI_ROOT>`: your Obsidian LLM Wiki vault root
- `<HERMES_AGENT_ROOT>`: Hermes Agent source/root directory, for example `~/.hermes/hermes-agent`

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate

# 1) Create or refresh the human-facing wiki skeleton.
.venv/bin/agent-context-substrate init-wiki \
  --wiki-root '<WIKI_ROOT>'

# 2) Install the Hermes user plugin from packaged assets.
.venv/bin/agent-context-substrate install-plugin \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

# 3) Install the Hermes context engine from packaged assets.
.venv/bin/agent-context-substrate install-context-engine \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

# 4) Verify installation health.
.venv/bin/agent-context-substrate doctor \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --fail-on-issues
```

Then enable the Hermes plugin and select the context engine in Hermes config:

```bash
cd '<HERMES_AGENT_ROOT>'
. venv/bin/activate
hermes plugins enable agent-context-substrate
```

```yaml
# ~/.hermes/config.yaml
plugins:
  enabled:
    - agent-context-substrate

context:
  engine: agent_context_substrate
```

If a Telegram gateway is already running, restart it after changing plugin or context-engine files so it reloads Python modules and config.

## Install into Codex

Codex integration is **hook-primary, watcher fallback**. The packaged plugin keeps `.codex-plugin/plugin.json` free of MCP servers and manifest `hooks`, and ships the default Codex hook file at `hooks/hooks.json`. When the plugin hook is installed and trusted through Codex `/hooks`, the Stop hook finalizes the current thread, builds Codex CLI summaries, plans a flexible wiki patch, and lets the write judge decide whether to apply it. `codex-watch` remains the fallback for untrusted hooks, older runtimes, or missed Stop events.

Windows Codex app users should prefer the [Windows Codex app quick install](#windows-codex-app-quick-install) or the detailed [Windows setup guide](./docs/WINDOWS_CODEX_APP_SETUP.md). The commands below are the portable developer form.

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate

.venv/bin/agent-context-substrate install-codex-plugin \
  --codex-home ~/.codex \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

.venv/bin/agent-context-substrate codex-status --codex-home ~/.codex

# Expected mode:
# hook_support=supported
# hook_primary=installed
# watcher_fallback=available
```

Codex still requires one hook review before non-managed command hooks run. Open Codex CLI, enter `/hooks`, and trust the `agent-context-substrate` Stop hook. If hook review is not available yet, run watcher fallback explicitly:

Do not install both the plugin hook and `~/.codex/hooks.json` fallback by default. If a specific Codex runtime cannot load plugin-bundled hooks, opt in to the user hook fallback with `setup-codex --user-hook-fallback` or lower-level `install-codex-plugin --install-user-hook`.

```bash
.venv/bin/agent-context-substrate codex-watch \
  --codex-home ~/.codex \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --summary-mode auto \
  --wiki-auto-mode apply-flexible \
  --wiki-write-judge-mode auto \
  --interval-seconds 15 \
  --idle-seconds 90
```

Manual finalize is also available:

```bash
.venv/bin/agent-context-substrate codex-finalize \
  --thread-id '<CODEX_THREAD_ID>' \
  --codex-home ~/.codex \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --summary-mode auto \
  --wiki-auto-mode apply-flexible \
  --wiki-write-judge-mode auto
```

## Fresh install smoke

`fresh-install-smoke` validates the distribution path against temporary or real roots. It initializes a wiki, installs packaged assets, runs a finalize smoke, exports recovery, searches retrieval, expands a hit, and lints the result.

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate
TMP_PROJECT=$(mktemp -d)
TMP_WIKI=$(mktemp -d)
TMP_AGENT=$(mktemp -d)

.venv/bin/agent-context-substrate fresh-install-smoke \
  --session-id '<SESSION_ID>' \
  --hermes-home ~/.hermes \
  --project-root "$TMP_PROJECT" \
  --wiki-root "$TMP_WIKI" \
  --hermes-agent-root "$TMP_AGENT"
```

Successful output includes:

```text
fresh-install-smoke ok=True
retrieval_hit_count=...
expanded_content_length=...
lint_issue_count=0
```

## Verified baseline

The current public alpha baseline has been verified from the published repository and package-managed integration path.

| Check | Current result |
| --- | --- |
| Project tests | `347 passed, 12 skipped` |
| Fresh install smoke | `fresh-install-smoke ok=True`, `retrieval_hit_count=1`, `expanded_content_length=14195`, `lint_issue_count=0` |
| Real wiki lint | `checked_pages=15`, `missing_provenance=0`, `orphan_pages=0`, `missing_from_index=0`, `broken_wikilinks=0` |
| Live Codex attachment | plugin `agent-context-substrate`, Stop hook installed, watcher fallback available |
| Live Hermes attachment | plugin `agent-context-substrate`, context engine `agent_context_substrate`, retrieval tools loaded |
| GitHub sync | `main` pushed to `jjuck/agent-context-substrate` |

Keep this table current when cutting a release or changing installer/runtime behavior.

## CLI commands

| Command | Purpose |
| --- | --- |
| `extract-session` | Export one Hermes session to raw JSON. |
| `build-context-packet` | Build raw export + context packet artifacts; add `--summary-mode` to also write v2 evidence and summary artifacts. |
| `extract-atoms` | Extract claim, decision, entity, concept, and question atoms from v2 summary artifacts into `data/atoms/*.jsonl`. |
| `propose-promotions` | Propose reviewable wiki promotion candidates from claim atoms. Does not write Obsidian. |
| `plan-wiki-patches` | Convert promotion candidates into dry-run wiki patch proposals. |
| `apply-wiki-patch` | Dry-run by default; writes only with `--apply` and guarded managed/flexible operations. |
| `list-promotions` | List promotion queue candidates and statuses. |
| `list-wiki-patches` | List proposed/applied wiki patch records. |
| `lint-promotions` | Run semantic lint checks on promotions and wiki patch records. |
| `build-topic-map` | Build graph-style topic map reports from wiki pages and substrate artifacts. |
| `codex-status` | Inspect local Codex state and confirm hook/watch integration mode. |
| `codex-finalize` | Finalize one Codex thread into raw/context-packet/recovery artifacts. |
| `codex-watch` | Watch Codex rollout JSONL files and finalize idle threads once per file fingerprint. |
| `setup-codex` | Run Windows Codex wiki/plugin/hook/diagnostic setup in one command. |
| `setup-codex-wizard` | Confirm paths interactively before running Codex setup. |
| `doctor-codex` | Check Codex source, plugin, hook, wiki, and artifact health. |
| `diagnose-codex` | Explain Codex setup issues and optionally repair safe local files with `--fix`. |
| `config-codex` | Inspect or update installed Codex plugin `local_config.json` and user-facing paths. |
| `search-knowledge` | Search durable knowledge, recovery, graph, and optional raw sources. |
| `expand-hit` | Expand a retrieval hit id into full local content. |
| `promote-packet-query` | Legacy explicit promotion into wiki `queries/`. |
| `promote-packet-plan` | Legacy explicit promotion into wiki `plans/`. |
| `promote-unit-concept` | Legacy explicit promotion into wiki `concepts/`. |
| `promote-unit-architecture` | Legacy explicit promotion into wiki `architectures/`. |
| `run-e2e-pipeline` | Legacy full pipeline: packet + four durable pages + lint. Use temp wiki first. |
| `lint-wiki` | Lint human-facing wiki and internal packet graph. |
| `init-wiki` | Initialize human-facing wiki folders/config/templates. |
| `install-plugin` | Install `~/.hermes/plugins/agent-context-substrate` from packaged assets. |
| `install-codex-plugin` | Install `~/.codex/plugins/agent-context-substrate` from packaged non-MCP Codex assets. |
| `install-context-engine` | Install `plugins/context_engine/agent_context_substrate` under Hermes Agent. |
| `doctor` | Check installed plugin/context-engine/wiki/project health. |
| `fresh-install-smoke` | End-to-end distribution smoke test. |

## Common usage

### Export one session

```bash
agent-context-substrate extract-session \
  --session-id '<SESSION_ID>' \
  --project-root '<PROJECT_ROOT>'
```

Output:

```text
data/exports/<SESSION_ID>.json
```

### Build a context packet

```bash
agent-context-substrate build-context-packet \
  --session-id '<SESSION_ID>' \
  --packet-id '<PACKET_ID>' \
  --task-title 'Resume context-substrate work' \
  --macro-context 'Recover the main context without replaying the full session.' \
  --unit-title 'Inspect packet-only finalize policy' \
  --goal 'Capture the current implementation state and next actions.' \
  --project-root '<PROJECT_ROOT>'
```

Output:

```text
data/exports/<SESSION_ID>.json
data/exports/context_packets/<PACKET_ID>.json
data/exports/context_packets/<PACKET_ID>.md
```

### Add structured v2 summaries

The default packet build remains backward-compatible. Add `--summary-mode` when you want evidence bundles and v2 summary artifacts.

```bash
agent-context-substrate build-context-packet \
  --session-id '<SESSION_ID>' \
  --packet-id '<PACKET_ID>' \
  --task-title 'Resume context-substrate work' \
  --macro-context 'Recover the main context without replaying the full session.' \
  --unit-title 'Inspect packet-only finalize policy' \
  --goal 'Capture the current implementation state and next actions.' \
  --summary-mode heuristic \
  --summary-cache on \
  --project-root '<PROJECT_ROOT>'
```

Optional modes:

| Mode | Meaning |
| --- | --- |
| `heuristic` | Default offline, deterministic summary backend. |
| `agent-llm` | Uses the host Agent's LLM routing layer when provided by the integration. |
| `hybrid` | Heuristic evidence spine plus Agent LLM semantic interpretation. |
| `custom-command` | Sends JSON to an external command and expects strict JSON back. |
| `codex-cli` | Calls `codex exec` with read-only sandbox, `approval_policy=never`, `service_tier=fast`, low reasoning effort, hooks disabled, inline bounded JSON input, JSONL output, and strict schema validation. |
| `auto` | Uses `codex-cli` when a usable Codex CLI is detected, otherwise writes heuristic summaries with fallback metadata. |

Standalone CLI runs `heuristic`, `custom-command`, `codex-cli`, and `auto` directly. `agent-llm` and `hybrid` require a host integration that injects an Agent LLM router.

Codex users can opt into LLM summaries without ACS reading Codex OAuth tokens or requiring an OpenAI Platform API key:

```bash
agent-context-substrate build-context-packet \
  --session-id '<SESSION_ID>' \
  --packet-id '<PACKET_ID>' \
  --task-title 'Resume context-substrate work' \
  --macro-context 'Recover the main context without replaying the full session.' \
  --unit-title 'Inspect packet-only finalize policy' \
  --goal 'Capture the current implementation state and next actions.' \
  --summary-mode auto \
  --summary-cache on \
  --project-root '<PROJECT_ROOT>'
```

Codex Stop-hook installs enable the same behavior by default. Use `config-codex set` only when you are updating an older install or changing policy:

```powershell
agent-context-substrate config-codex set --key summary_mode --value auto --project-root "<PROJECT_ROOT>"
agent-context-substrate config-codex set --key wiki_auto_mode --value apply-flexible --project-root "<PROJECT_ROOT>"
agent-context-substrate config-codex set --key wiki_write_judge_mode --value auto --project-root "<PROJECT_ROOT>"
```

| Option | When to use | Trade-off |
| --- | --- | --- |
| `codex-cli` / `auto` | Codex users already signed in through the Codex CLI/app. | Subprocess UX, but ACS never stores Codex credentials and falls back to heuristic on CLI/validation failure. |
| `custom-command` | You already have a local summarizer command or API wrapper. | Most flexible, but you own auth, safety, schema output, and cost behavior. |
| OpenAI Platform API key | CI or non-Codex environments that should use explicit API billing. | Simple automation auth, but separate key provisioning and API usage cost. |
| Direct Codex OAuth implementation | Not recommended. | Would make ACS responsible for token storage, refresh, revocation, and private endpoint stability. |
| Codex Python SDK | Promising follow-up for app-server workflows. | Current implementation keeps `codex exec` as the MVP because its sandbox, approval, JSONL, and schema flags are explicit and script-friendly. |

Optional summary evaluation is separate from summary generation:

```bash
agent-context-substrate build-context-packet \
  --summary-mode heuristic \
  --summary-judge-mode hybrid \
  --project-root '<PROJECT_ROOT>'
```

`--summary-judge-mode hybrid` writes `data/exports/evals/<PACKET_ID>-summary-judge.json` when v2 summaries are exported. In host integrations it reuses the Agent LLM router to judge recovery usefulness, hallucination risk, missing next steps, and wiki-candidate noise. It never rewrites summaries or applies wiki patches; without an injected router it degrades to a mechanical-lint verdict artifact.

Additional output:

```text
data/exports/evidence/<SESSION_ID>/<PACKET_ID>-micro-1.json
data/exports/summaries/<PACKET_ID>-micro-v2.json
data/exports/summaries/<PACKET_ID>-unit-v2.json
data/exports/evals/<PACKET_ID>-summary-judge.json   # when --summary-judge-mode hybrid
data/cache/summaries/<cache_key>.json   # when --summary-cache on
```

### Judge-gated wiki growth

The packaged Codex Stop hook runs this path automatically with `wiki_auto_mode=apply-flexible` and `wiki_write_judge_mode=auto`. The LLM Wiki grows when the judge decides the session evidence supports a flexible integration. The same steps are available manually when you want to inspect or replay the pipeline.

```bash
agent-context-substrate extract-atoms \
  --packet-id '<PACKET_ID>' \
  --project-root '<PROJECT_ROOT>'

agent-context-substrate propose-promotions \
  --packet-id '<PACKET_ID>' \
  --project-root '<PROJECT_ROOT>'

agent-context-substrate plan-wiki-patches \
  --promotion-file '<PROJECT_ROOT>/data/promotions/<PACKET_ID>.json' \
  --wiki-root '<WIKI_ROOT>' \
  --project-root '<PROJECT_ROOT>'

# Opt in when a page needs a rubric-guided draft/revision instead of a managed claim block.
agent-context-substrate plan-wiki-patches \
  --promotion-file '<PROJECT_ROOT>/data/promotions/<PACKET_ID>.json' \
  --write-mode flexible \
  --wiki-root '<WIKI_ROOT>' \
  --project-root '<PROJECT_ROOT>'

# Manual CLI apply is still dry-run by default. Add --apply only after reviewing the proposal
# or when the proposal metadata contains an approved write-judge decision.
agent-context-substrate apply-wiki-patch \
  --patch-file '<PROJECT_ROOT>/data/wiki_patches/<PACKET_ID>.json' \
  --wiki-root '<WIKI_ROOT>' \
  --project-root '<PROJECT_ROOT>'
```

Proposal outputs:

```text
data/atoms/claims.jsonl
data/promotions/<PACKET_ID>.json
data/promotions/<PACKET_ID>.md
data/wiki_patches/<PACKET_ID>.json
data/wiki_patches/<PACKET_ID>.md
data/wiki_decisions/<PACKET_ID>.json   # Codex automatic path
```

Flexible proposals remain proposal-only unless their metadata carries an approved semantic judge verdict. `apply-wiki-patch --apply` also checks evidence, target safety, and current page hashes before writing.

### Lint a real wiki

```bash
export WIKI_PATH='<WIKI_ROOT>'

agent-context-substrate lint-wiki \
  --project-root '<PROJECT_ROOT>' \
  --report-id real-wiki-check \
  --fail-on-issues
```

Output:

```text
data/exports/lint/real-wiki-check.json
data/exports/lint/real-wiki-check.md
checked_pages=... missing_provenance=... orphan_pages=... missing_from_index=... broken_wikilinks=...
```

### Legacy full promotion

The legacy Hermes/standalone `run_session_finalize_pipeline(...)` path is `packet-only` unless you explicitly request old full promotion. If you need the old four-page flow, run it first against a temporary wiki:

```bash
TMP_WIKI=$(mktemp -d)
export WIKI_PATH="$TMP_WIKI"

agent-context-substrate run-e2e-pipeline \
  --session-id '<SESSION_ID>' \
  --packet-id '<PACKET_ID>' \
  --task-title '<task title>' \
  --macro-context '<macro context>' \
  --unit-title '<unit title>' \
  --goal '<goal>' \
  --report-id '<REPORT_ID>' \
  --project-root '<PROJECT_ROOT>'
```

## Configuration

### Core paths

| Setting | Required | Default | Description |
| --- | --- | --- | --- |
| `HERMES_HOME` | No | `~/.hermes` | Hermes home; source DB is `HERMES_HOME/state.db`. |
| `WIKI_PATH` | No | `~/wiki` | Obsidian wiki root for lint/promotion/retrieval. |
| `--project-root` | Recommended | Current directory | Harness data root for `data/exports/` and `data/index/`. |
| `--hermes-agent-root` | For context engine install | - | Hermes Agent source/root directory. |

### Hermes plugin variables

| Variable | Default | Description |
| --- | --- | --- |
| `AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT` | installed `local_config.py` or `~/.hermes/agent-context-substrate` | Harness project/data root. |
| `AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT` | runtime override before `WIKI_PATH`, installed `local_config.json`, then `%USERPROFILE%\Documents\LLM Wiki` template | Obsidian LLM Wiki root. |
| `AGENT_CONTEXT_SUBSTRATE_AUTO_FINALIZE` | `true` | Enable session-finalize automation. |
| `AGENT_CONTEXT_SUBSTRATE_MIN_MESSAGE_COUNT` | `3` | Skip short sessions. |
| `AGENT_CONTEXT_SUBSTRATE_ALLOWED_SOURCES` | `telegram,cli` | Raw session sources eligible for auto-finalize. |
| `AGENT_CONTEXT_SUBSTRATE_GATEWAY_POLICY` | `trigger-only` | Treat gateway hooks as non-blocking triggers/backstops. |
| `AGENT_CONTEXT_SUBSTRATE_PROMOTION_MODE` | `packet-only` | `packet-only` or legacy `full`. |
| `AGENT_CONTEXT_SUBSTRATE_SKIP_TITLE_PATTERNS` | empty | Comma-separated title patterns to skip. |

## Obsidian wiki policy

The recommended vault is a human-facing semantic wiki, not a dump of generated session pages:

```text
LLM Wiki/
  Home.md
  index.md
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
```

Active durable pages should include `lang: ko` or `lang: en`, provenance/sources, and type-appropriate sections. The harness linter checks structural graph quality and human-facing quality issues.

Machine-assisted Codex updates default to rubric-guided flexible integration, guarded by a write judge. Managed claim blocks remain available for explicit/manual workflows:

```md
<!-- acs:auto:claims:start -->
- Evidence-backed claim `claim:<id>`
<!-- acs:auto:claims:end -->
```

Canonical pages can be updated automatically only when the patch has evidence, approved judge metadata, target-path safety, and a current-page hash match. Otherwise ACS leaves the proposal and decision artifact for review.

## Project structure

```text
.
├── README.md
├── LICENSE
├── docs/
│   ├── USER_GUIDE.md
│   ├── OPERATIONS.md
│   ├── PIPELINE.md
│   └── RELEASE_CHECKLIST.md
├── pyproject.toml
├── src/agent_context_substrate/
│   ├── assets/
│   ├── cli.py
│   ├── distribution.py
│   ├── agent_llm_router.py
│   ├── atoms.py
│   ├── evidence.py
│   ├── integration.py
│   ├── lint.py
│   ├── promotions.py
│   ├── recovery.py
│   ├── retrieval.py
│   ├── semantic_lint.py
│   ├── summarizer_backends.py
│   ├── summary_lint.py
│   ├── topic_map.py
│   └── wiki_patches.py
├── tests/
└── data/
    ├── atoms/         # generated atom JSONL, ignored by git
    ├── cache/         # generated summary cache, ignored by git
    ├── exports/       # generated raw/packet/evidence/summary/lint artifacts
    ├── index/         # generated ledger/topic-map reports
    ├── promotions/    # generated promotion queue proposals
    └── wiki_patches/  # generated wiki patch proposals and apply log
```

## Development and verification

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate
python -m pytest -q
ruff check .
```

Real wiki smoke:

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate
WIKI_PATH='<WIKI_ROOT>' .venv/bin/agent-context-substrate lint-wiki \
  --project-root '<PROJECT_ROOT>' \
  --report-id real-wiki-smoke \
  --fail-on-issues
```

WSL note: if the project path is under a Windows mount and contains non-ASCII characters, prefer `cd '<path>' && ...` inside the shell command rather than relying on tooling `workdir` support.

## Privacy and safety

This project works with sensitive local data. Treat exports as private unless deliberately scrubbed.

- Hermes `state.db` can contain full user/assistant messages, tool outputs, file paths, and operational details.
- Codex `~/.codex/state_5.sqlite` and rollout JSONL files can contain local thread metadata, messages, tool calls, and paths.
- `data/exports/**/*.json` and `data/exports/**/*.md` may contain raw or summarized private session content.
- Obsidian wiki pages may contain personal project notes and provenance links.
- Never commit API keys, tokens, passwords, `.env` files, private connection strings, or raw private session exports.
- `.gitignore` excludes generated exports and local caches by default; review `git status --short` before every release.
- For Codex live automation, prefer the default judge-gated `apply-flexible` policy. Use legacy full promotion only when you intentionally want the older durable page flow.

## Documentation

- [한국어 README](./README.ko.md) — Korean overview, benefits, install path, and common usage.
- [User Guide EN](./docs/USER_GUIDE.en.md) — English storage layers, Hermes install, plugin/context-engine use, Telegram commands.
- [User Guide KO](./docs/USER_GUIDE.md) — Korean storage layers, Hermes install, plugin/context-engine use, Telegram commands.
- [Operations Guide](./docs/OPERATIONS.md) — runbooks, validation, troubleshooting, privacy and rollback notes.
- [Pipeline Reference](./docs/PIPELINE.md) — data flow, module responsibilities, artifact lifecycle, v2 summaries, promotion queue, wiki patches, and topic map.
- [Release Checklist](./docs/RELEASE_CHECKLIST.md) — source hygiene, install checks, privacy checks, verification gates.

## Current limitations

- The project is a public alpha: APIs, docs, and installer behavior may still change before beta/stable releases.
- Claim atoms are implemented first; decision/entity/concept/question atom stores are planned extensions.
- Recovery brief quality is now surfaced in exported recovery JSON through a `quality_gate` score and issue list.
- Semantic lint currently covers promotion/wiki-patch structural checks, including missing evidence, missing targets, claim sources, patch→candidate integrity, and applied-patch logs; deeper wiki health checks are planned.
- Wiki patch apply is intentionally guarded: Codex defaults to flexible judge-gated writes, and all flexible `replace_page` writes require evidence, approved judge metadata, and a current-page hash match.
- Legacy full promotion still writes old `queries/`, `concepts/`, `plans/`, and `architectures/` paths.
- Long-running Hermes gateway processes need restart after plugin/context-engine deployment.
