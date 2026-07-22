# Agent Context Substrate

**Turn Hermes and Codex sessions into recoverable context, searchable artifacts, and an evidence-backed living Markdown wiki.**

[한국어 README](./README.ko.md) | [Documentation map](./docs/README.md) | [User guide](./docs/USER_GUIDE.en.md) | [Windows Codex setup](./docs/WINDOWS_CODEX_APP_SETUP.md)

## What ACS Does

Agent Context Substrate reads local agent session stores without modifying them and creates a durable context layer:

- raw session exports with provenance;
- compact context packets and recovery briefs;
- evidence-backed V2 summaries with deterministic fallback;
- claim atoms and promotion candidates;
- guarded LLM Wiki patch proposals and write decisions;
- read-only knowledge, recovery, and graph retrieval;
- lint, ledger, and hook event artifacts for auditability.

Packaged adapters currently support Hermes Agent and the Windows Codex app. The core pipeline is source-neutral after each adapter produces a typed `SessionBundle`.

## Default Codex Behavior

New Codex installs use:

```text
summary_mode=auto
wiki_auto_mode=apply-flexible
wiki_write_judge_mode=auto
wiki_auto_min_score=0.85
workspace_scope=all
```

When an eligible Codex thread stops, ACS:

```text
Codex rollout
  -> typed SessionBundle
  -> context packet + evidence-backed summary
  -> atoms + promotion candidates
  -> flexible wiki patch proposal
  -> write-judge decision and candidate selection
  -> guarded transaction or review artifact
  -> lint + recovery + ledger
```

The judge decides whether the evidence is durable enough to write and selects exact candidate IDs. Mechanical policy still checks evidence, safe paths, operation type, and current-page hashes. A failed or low-confidence judge run does not write the vault.

## Living Wiki Model

The default wiki policy is `emergent-root`.

- New automatic flexible writes target `<Title>.md` at the vault root.
- Folder paths are storage hints, not the semantic taxonomy.
- `type`, optional `category`, `sources`, wikilinks, and index/MOC sections carry meaning.
- New categories are allowed and do not block writes.
- Category and type values are open vocabulary, not enums.
- Generic subjects such as `context packet` do not force artificial canonical pages.
- Existing registry-folder vaults remain supported as an explicit compatibility mode.

`init-wiki` creates only the system guidance, templates, `index.md`, and `log.md` needed to let the wiki grow:

```text
LLM Wiki/
  index.md
  log.md
  _system/
    config.yaml
    guides/
      wiki-principles.md
      ontology-seeds.md
    templates/
    styles/
```

## Quick Start

Requirements: Python 3.11+ and Git. Runtime dependencies are standard-library only.

```bash
git clone https://github.com/jjuck/agent-context-substrate.git
cd agent-context-substrate
python -m venv .venv
```

Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

Linux, macOS, or WSL:

```bash
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

## Windows Codex Install

The recommended one-command setup is:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
```

The script creates or refreshes the environment, initializes the default wiki, installs the plugin and personal marketplace/cache entry, registers `agent-context-substrate@personal` when a usable Codex CLI is available, and runs diagnostics.

The default wiki config stores the portable template `%USERPROFILE%\Documents\LLM Wiki`, not a username-bound absolute path. Effective root precedence is:

1. `AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT`
2. `WIKI_PATH`
3. installed `local_config.json["wiki_root"]`
4. `%USERPROFILE%\Documents\LLM Wiki`

After setup, restart Codex and trust the `agent-context-substrate` Stop hook in **Codex app -> Settings -> Hooks**. CLI/TUI users can use `/hooks`. Hook trust is separate from Full Access, approval mode, and sandbox settings.

Verify:

```powershell
.\.venv\Scripts\agent-context-substrate.exe codex-status
.\.venv\Scripts\agent-context-substrate.exe doctor-codex --fail-on-issues
.\.venv\Scripts\agent-context-substrate.exe config-codex paths
```

Expected integration mode:

```text
hook_support=supported
hook_primary=installed
watcher_fallback=available
```

`project_root` is the ACS artifact root, not a workspace boundary. New installs use `workspace_scope="all"`. Use `workspace_scope="restricted"` with explicit `allowed_workspace_roots` only when an allowlist is required.

See [Windows Codex App Setup](./docs/WINDOWS_CODEX_APP_SETUP.md) for trust, smoke-test, diagnosis, and fallback details.

## Hermes Install

```bash
agent-context-substrate init-wiki --wiki-root '<WIKI_ROOT>'

agent-context-substrate install-plugin \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

agent-context-substrate install-context-engine \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

agent-context-substrate doctor \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --fail-on-issues
```

Hermes/standalone finalize remains `packet-only` unless legacy full promotion is explicitly requested.

## Common Commands

```bash
# Inspect the command surface
agent-context-substrate --help

# Finalize one Codex thread
agent-context-substrate codex-finalize \
  --thread-id '<THREAD_ID>' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --summary-mode auto \
  --wiki-auto-mode apply-flexible \
  --wiki-write-judge-mode auto

# Read-only retrieval
agent-context-substrate search-knowledge \
  --query '<QUERY>' \
  --mode knowledge \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>'

# Expand a hit
agent-context-substrate expand-hit \
  --hit-id '<HIT_ID>' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>'

# Validate the wiki
WIKI_PATH='<WIKI_ROOT>' agent-context-substrate lint-wiki \
  --project-root '<PROJECT_ROOT>' \
  --report-id manual-check \
  --fail-on-issues
```

Manual `apply-wiki-patch` is dry-run by default. Use `--apply` only after reviewing the proposal; the command still enforces judge metadata and mechanical safety gates.

## Artifacts

Machine-facing artifacts stay under `<PROJECT_ROOT>/data`:

```text
data/
  exports/raw/
  exports/context_packets/
  exports/evidence/
  exports/summaries/
  exports/recovery/
  atoms/
  promotions/
  wiki_decisions/
  wiki_patches/
  index/
```

Wiki writes update the separate resolved vault root. Non-dry-run page, index, log, promotion status, and applied-log changes run inside a recoverable transaction. An interrupted `prepared` transaction is restored before the next apply.

## Lint Policy

Blocking issues protect provenance and graph integrity, including missing provenance, missing index registration, undiscoverable pages, broken links, and malformed internal references.

Language, recommended prose sections, thin content, related-link quality, and registry-only category findings are advisory. Emergent-root mode does not report a new category as a problem.

## Privacy And Safety

- Hermes `state.db`, Codex SQLite/rollouts, and `data/exports` can contain private messages, tool output, and local paths.
- ACS reads source session stores read-only.
- Codex workers run with a read-only sandbox, `approval_policy=never`, fast service tier, low reasoning effort, and hooks disabled.
- LLM-bound payloads are bounded and can redact secrets, email addresses, paths, and code blocks.
- Never commit credentials, private exports, or generated local artifacts.
- Review `git status --short` before release.

## Documentation

- [Documentation map](./docs/README.md)
- [English user guide](./docs/USER_GUIDE.en.md)
- [Korean user guide](./docs/USER_GUIDE.md)
- [Windows Codex setup](./docs/WINDOWS_CODEX_APP_SETUP.md)
- [Operations guide](./docs/OPERATIONS.md)
- [Pipeline and architecture](./docs/PIPELINE.md)
- [Release checklist](./docs/RELEASE_CHECKLIST.md)
- [Changelog](./CHANGELOG.md)

## Status

ACS is alpha software. The current release line is `0.2.0`. Legacy explicit promotion commands and existing folder-based vaults remain compatible, but the recommended path is typed finalize artifacts plus judge-gated emergent wiki growth.
