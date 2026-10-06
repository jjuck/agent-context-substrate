# Agent Context Substrate User Guide

[한국어](./USER_GUIDE.md) · [README](../README.md) · [Windows setup](./WINDOWS_CODEX_APP_SETUP.md)

ACS turns Hermes and Codex sessions into local context packets, recovery briefs, and searchable evidence. This guide covers daily use; [Operations](./OPERATIONS.md) covers maintenance and [Pipeline](./PIPELINE.md) describes artifact processing.

## 1. Choose a task

| Task | Start here |
| --- | --- |
| Install for Windows Codex | [Canonical setup, trust, and diagnosis guide](./WINDOWS_CODEX_APP_SETUP.md) |
| Install for Hermes | Section 3 |
| Finalize a Codex thread or run a watcher | Section 4 |
| Find and recover past context | Section 5 |
| Propose a reviewed wiki update | Section 6 |
| Diagnose missing artifacts | Section 8 |

The default is `packet-only`: raw export → summaries → context packet → lint → recovery → ledger. It stores machine artifacts under ACS `data/` without automatically promoting session pages into Obsidian. V2 summaries and wiki promotion are optional additional steps.

## 2. Know your paths

| Path | Purpose |
| --- | --- |
| `<PROJECT_ROOT>` | ACS artifact scope containing `data/`; often the ACS checkout |
| `<WIKI_ROOT>` | Human-facing LLM Wiki / Obsidian vault |
| `<HERMES_AGENT_ROOT>` | Existing Hermes Agent checkout and runtime |
| `HERMES_HOME/state.db` (normally `~/.hermes/state.db`) | Original Hermes sessions |
| `<CODEX_HOME>/state_5.sqlite` and `sessions/**/rollout-*.jsonl` | Local Codex metadata/events, read-only for ACS |

Use the same project and wiki roots when finalizing, searching, and expanding hits. `--project-root .` means the current directory's ACS data, not every project on the machine. The Codex Stop hook also filters by the configured project root: a payload `cwd` outside it is skipped. The watcher has different scope; see section 4.

| Artifact | Location under `<PROJECT_ROOT>` |
| --- | --- |
| Hermes raw export | `data/exports/<session_id>.json` |
| Codex raw export | `data/exports/raw/codex/<thread_id>.json` |
| Packets | `data/exports/context_packets/<id>.{json,md}` |
| Recovery | `data/exports/recovery/<id>.json` |
| Lint reports | `data/exports/lint/` |
| Ledger / watcher state | `data/index/` |
| Optional evidence / V2 summaries | `data/exports/evidence/`, `data/exports/summaries/` |
| Optional claims / promotions / patches | `data/atoms/`, `data/promotions/`, `data/wiki_patches/` |

Obsidian is optional for execution. Open `<WIKI_ROOT>` as a vault when you want to read and curate pages. Initialization creates a wiki skeleton; it does not register or open an Obsidian vault.

## 3. Install and enable Hermes

Use Python 3.11+ in the ACS checkout. Replace all angle-bracket placeholders. These examples use a POSIX shell; Windows Codex setup has dedicated PowerShell instructions.

```bash
cd '<PROJECT_ROOT>'
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
agent-context-substrate init-wiki --wiki-root '<WIKI_ROOT>'
agent-context-substrate install-plugin \
  --hermes-home ~/.hermes --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>'
agent-context-substrate install-context-engine \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>'
```

For an existing installation, add `--overwrite` to the two install commands to back up and replace installed assets. They write machine-specific `local_config.py` alongside the plugin/context engine.

Enable the plugin using the existing Hermes runtime:

```bash
cd '<HERMES_AGENT_ROOT>'
. venv/bin/activate
hermes plugins enable agent-context-substrate
```

In Hermes configuration, retain other settings and select:

```yaml
plugins:
  enabled:
    - agent-context-substrate
context:
  engine: agent_context_substrate
```

The plugin provides finalize hooks and Telegram commands. The context engine provides `wiki_recovery_context`, `wiki_knowledge_search`, and `wiki_knowledge_expand`. Installing assets alone does not enable either component.

Restart a running gateway with Telegram `/restart` or `hermes gateway restart`. Then check with the ACS environment:

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate
agent-context-substrate doctor \
  --hermes-home ~/.hermes --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --fail-on-issues
```

### Hermes defaults and controls

Environment variables override installed local configuration. The prefix for these suffixes is `AGENT_CONTEXT_SUBSTRATE_`.

| Suffix | Default | Effect |
| --- | --- | --- |
| `PROJECT_ROOT` | Installed local value, else `~/.hermes/agent-context-substrate` | ACS data scope |
| `WIKI_ROOT` | Installed local value, else `~/LLM Wiki` | Wiki location |
| `AUTO_FINALIZE` | `true` | Set `false` to stop automatic finalize |
| `MIN_MESSAGE_COUNT` | `3` | Skip shorter sessions |
| `ALLOWED_SOURCES` | `telegram,cli` | Eligible session sources |
| `GATEWAY_POLICY` | `trigger-only` | Gateway hooks act as triggers/backstops |
| `PROMOTION_MODE` | `packet-only` | Keep automatic results in ACS artifacts |
| `SKIP_TITLE_PATTERNS` | Empty | Comma-separated title patterns to skip |
| `SUMMARY_MODE` | Empty | V2 summary generation is opt-in |
| `SUMMARY_JUDGE_MODE` | `off` | Optional artifact-only evaluation |

Gateway-source sessions are excluded by default. Changed environment settings require the relevant Hermes process to restart. Legacy `PROMOTION_MODE=full` writes wiki pages; use it only when that behavior is intended.

| Telegram command | Task |
| --- | --- |
| `/harness` | Inspect health, paths, and policy |
| `/packet <session_id>` | Finalize a selected session under configured policy |
| `/wiki-resume <session_id>` | Show its recovery brief |
| `/wiki-lint` | Check wiki and artifact consistency |

## 4. Finalize Codex without MCP

Install and review hook trust using the [Windows setup guide](./WINDOWS_CODEX_APP_SETUP.md). The packaged integration uses a Stop hook with watcher fallback; it has no MCP server.

From the ACS checkout in PowerShell, define explicit paths:

```powershell
$AcsCli = '.\.venv\Scripts\agent-context-substrate.exe'
$AcsRoot = (Resolve-Path -LiteralPath '.').Path
$AcsWiki = "$env:USERPROFILE\Documents\LLM Wiki"
$AcsCodex = "$env:USERPROFILE\.codex"
& $AcsCli codex-status --codex-home $AcsCodex
& $AcsCli codex-finalize --thread-id '<THREAD_ID>' `
  --codex-home $AcsCodex --project-root $AcsRoot --wiki-root $AcsWiki
```

Choose the thread ID from `codex-status`. Manual finalize writes packets, recovery, lint, and ledger artifacts; it does not require hook trust. Source files remain read-only.

To process currently idle threads once:

```powershell
& $AcsCli codex-watch --once --idle-seconds 300 `
  --codex-home $AcsCodex --project-root $AcsRoot --wiki-root $AcsWiki
```

This is a processing command, not a dry-run. It discovers sessions across the selected Codex home, without the Stop hook's `cwd` filter. Older eligible threads can be exported into the selected ACS root. A larger idle threshold postpones recently modified threads but does not exclude older ones.

Omit `--once` for continuous polling; use `--interval-seconds` to set the polling interval and Ctrl+C to stop. The watcher records processed rollout fingerprints in `data/index/codex_watcher_state.json`.

Codex finalize currently uses its packet-only summary path and has no `--summary-mode` flag. Do not assume its output already includes the V2 artifacts needed for claim extraction.

## 5. Search and recover context

Use the installed CLI in either shell (these examples use POSIX continuation):

```bash
agent-context-substrate search-knowledge \
  --query 'deployment decision' --mode knowledge \
  --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>'
agent-context-substrate expand-hit \
  --hit-id '<HIT_ID>' --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>'
```

Copy `hit_id` from search output. Choose `--mode recovery` for recovery briefs or `--mode graph` for relationships; `--limit` and `--json` control results. `--include-raw` opts into raw Hermes messages, not arbitrary Codex-home scanning. Raw-message hits support snippets/provenance; full expansion is disabled.

Retrieval reads wiki pages, exported packets, recovery, and other supported artifacts. Codex evidence becomes available through exports. Search and expansion do not edit Obsidian. Default excluded wiki folders include `.obsidian/`, `_system/`, and `90 보관/`.

## 6. Optional V2 summaries → claims → reviewed wiki patches

The following V2 build command takes a **Hermes session ID**. Run it only when evidence-backed summaries are needed:

```bash
agent-context-substrate build-context-packet \
  --session-id '<SESSION_ID>' --packet-id '<PACKET_ID>' \
  --task-title '<TASK>' --macro-context '<CONTEXT>' \
  --unit-title '<UNIT>' --goal '<GOAL>' \
  --summary-mode heuristic --summary-cache on --project-root '<PROJECT_ROOT>'
```

`heuristic` is local and deterministic. `custom-command` needs `--summarizer-command` with JSON stdin/stdout. `agent-llm` and `hybrid` require a host integration that supplies an LLM router; the standalone CLI does not supply one. `--summary-judge-mode hybrid` requires a summary mode but does not require a router to run: without a router, or if it fails, the judge returns a degraded mechanical verdict with `judge_unavailable`. Semantic judging requires a working host router. The judge exports evaluation artifacts rather than applying patches.

With V2 summaries present, work from the same ACS root:

```bash
cd '<PROJECT_ROOT>'
agent-context-substrate extract-atoms --packet-id '<PACKET_ID>' --project-root .
agent-context-substrate propose-promotions --packet-id '<PACKET_ID>' --project-root .
agent-context-substrate plan-wiki-patches \
  --promotion-file 'data/promotions/<PACKET_ID>.json' \
  --wiki-root '<WIKI_ROOT>' --project-root .
agent-context-substrate apply-wiki-patch \
  --patch-file 'data/wiki_patches/<PACKET_ID>.json' \
  --wiki-root '<WIKI_ROOT>' --project-root .
```

Planning uses `pending` candidates; review the generated JSON/Markdown evidence, target, and diff. `review-promotion --candidate-id '<ID>' --preview-evidence --project-root .` previews without changing status. Planning and default patch application do not write wiki pages.

After reviewing the proposal and dry-run result, repeat the apply command with `--apply`. Human review is a workflow requirement, not a CLI-enforced approval gate. Current alpha operations cover page creation, managed claim blocks, and section appends; unsupported or conflicting changes are skipped. Review new seed pages and their language metadata before treating them as curated knowledge. See [Pipeline](./PIPELINE.md) for details.

## 7. Maintain wiki language and lint

The initialized vault includes `Home.md`, `index.md`, `SCHEMA.md`, `log.md`, numbered content folders, and `_system/`. Language configuration lives in `_system/config.yaml`; templates live in `_system/templates/ko/` and `en/`.

Human-facing pages should carry `lang: ko` or `lang: en` along with title, type, category, status, and tags. Folder names can remain Korean in either language. Use the corresponding language template when adding a page.

```bash
export WIKI_PATH='<WIKI_ROOT>'
agent-context-substrate lint-wiki --project-root '<PROJECT_ROOT>' --report-id wiki-lint
```

In PowerShell, set `$env:WIKI_PATH = $AcsWiki` instead of `export`. Lint writes reports; it does not repair pages. Add `--semantic` to include semantic artifact checks, or `--fail-on-issues` for a nonzero exit on issues.

## 8. Diagnose and protect private data

| Symptom | Check / next action |
| --- | --- |
| Hermes `/harness` is degraded | Inspect paths/import errors; run `doctor` in the ACS environment |
| Hermes settings are stale | Restart the gateway/process after changes |
| Automatic Hermes finalize is skipped | Check source, message count, skip patterns, and policy |
| Codex Stop hook produces nothing | Check installation, trust, runtime, and `cwd` scope in the Windows guide |
| Packet is reused | Inspect ledger and required artifacts; reuse can be normal |
| No search hits | Confirm matching project/wiki roots and that finalize exported the source |
| Claim extraction lacks input | Build V2 summaries first; a legacy packet alone is insufficient |
| Lint reports language or broken links | Correct frontmatter or link targets, then rerun lint |

Raw databases, rollout files, exports, summaries, provenance, and installed local config can expose messages, secrets, code, personal data, and machine paths. Keep them private and inspect changes before sharing. Opt-in LLM/custom summaries may send filtered evidence to the configured provider or process; redaction is not a guarantee that all sensitive data is removed.

For maintenance and public release checks, use [Operations](./OPERATIONS.md) and [Release checklist](./RELEASE_CHECKLIST.md). Setup health, CLI help, and artifact checks each provide different evidence; none alone proves that a GUI hook ran successfully.
