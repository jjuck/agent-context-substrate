<div align="center">

# Agent Context Substrate

**Turn Hermes sessions into reusable context packets, recovery briefs, and request-time retrieval — while keeping Obsidian as a human-facing wiki.**

![Status](https://img.shields.io/badge/status-private%20alpha-orange) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) [![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

[한국어 README](./README.ko.md) · [Quick Start](#quick-start) · [Hermes Install](#install-into-hermes) · [Verified Baseline](#verified-baseline) · [CLI](#cli-commands) · [Privacy](#privacy-and-safety) · [User Guide EN](./docs/USER_GUIDE.en.md) · [User Guide KO](./docs/USER_GUIDE.md)

</div>

## Overview

`agent-context-substrate` is a Python package and CLI for building a durable context and retrieval substrate from AI-agent sessions.
The current packaged adapter supports **Hermes Agent only**: it reads Hermes `state.db`, exports raw sessions, builds context packets, writes recovery briefs, and exposes read-only retrieval tools back to Hermes.

This project was formerly named `hermes-llm-wiki-harness`. The rename reflects the longer-term goal: support more agents through additional adapters while keeping Hermes Agent as the first working reference integration.

The default session-finalize policy is **`packet-only`**: generated session artifacts stay in `data/exports/` and `data/index/session_ledger.json`; Obsidian is reserved for curated, human-written wiki pages.

## Why this helps

Long AI-agent sessions often contain decisions, file paths, test results, and next steps that are hard to recover after a reset or context compression. This harness makes that work reusable:

- **Resume interrupted work** with a compact recovery brief instead of rereading the whole transcript.
- **Search prior project knowledge** while Hermes is handling a new request.
- **Keep Obsidian readable** by separating generated artifacts from human-written wiki pages.
- **Audit release readiness** with lint reports for wiki links, provenance, language metadata, and internal packet consistency.
- **Avoid duplicate processing** through a ledger that records completed, failed, retried, and reused session artifacts.

```text
Hermes state.db
  -> raw session export
  -> context packet JSON / Markdown
  -> lint report JSON / Markdown
  -> recovery brief JSON
  -> session ledger
  -> optional read-only retrieval by Hermes tools
```

## Quick facts

| Item | Value |
| --- | --- |
| Status | Private alpha; GitHub private repo synced; public release checklist still pending |
| Runtime | Python 3.11+ |
| Main interface | CLI: `agent-context-substrate` |
| Current agent support | Hermes Agent only |
| Hermes integration | user plugin `agent-context-substrate` + context engine `agent_context_substrate` |
| Planned adapter direction | Additional agents such as Claude Code, Codex, OpenCode, or Gemini can be added later; they are not packaged yet. |
| Default output | `data/exports/`, `data/index/session_ledger.json` |
| Default promotion mode | `packet-only` |
| Legacy wiki promotion | Explicit `promotion_mode="full"` or `promote-*` CLI only |
| Wiki role | Human-facing semantic Obsidian vault |
| Wiki languages | `ko`, `en` via `lang` frontmatter and `_system/config.yaml` |
| License | MIT |

## Key features

- Export one Hermes session from `HERMES_HOME/state.db` into raw JSON.
- Build heuristic `MicroSummary`, `UnitSummary`, and `ContextPacket` artifacts.
- Generate compact recovery briefs for resume workflows.
- Maintain a ledger for idempotency, stale-artifact rebuilds, retry budgets, and partial-failure diagnostics.
- Keep live Obsidian clean by using `packet-only` as the default finalize mode.
- Initialize a human-facing LLM Wiki skeleton with Korean/English templates.
- Install packaged Hermes user-plugin and context-engine assets into a Hermes Agent environment.
- Run `doctor` and `fresh-install-smoke` checks for distribution validation.
- Expose request-time retrieval through Hermes context-engine tools:
  - `wiki_recovery_context`
  - `wiki_knowledge_search`
  - `wiki_knowledge_expand`

## Quick start

```bash
git clone https://github.com/jjuck/agent-context-substrate.git agent-context-substrate
cd agent-context-substrate
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
python -m pytest -q
.venv/bin/agent-context-substrate --help
```

Expected: tests pass and `--help` shows the distribution commands (`init-wiki`, `install-plugin`, `install-context-engine`, `doctor`, `fresh-install-smoke`) as well as the packet/promotion/lint commands.

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

## Fresh install smoke

`fresh-install-smoke` validates the distribution path against temporary or real roots. It initializes a wiki, installs packaged assets, runs packet-only finalize, exports recovery, searches retrieval, expands a hit, and lints the result.

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

The current private baseline has been verified from the renamed repository and package-managed integration path.

| Check | Current result |
| --- | --- |
| Project tests | `64 passed` |
| Fresh install smoke | `fresh-install-smoke ok=True`, `retrieval_hit_count=1`, `expanded_content_length=5291`, `lint_issue_count=0` |
| Real wiki lint | `checked_pages=15`, `missing_provenance=0`, `orphan_pages=0`, `missing_from_index=0`, `broken_wikilinks=0` |
| Live Hermes attachment | plugin `agent-context-substrate`, context engine `agent_context_substrate`, retrieval tools loaded |
| GitHub sync | `main` pushed to `jjuck/agent-context-substrate` |

Keep this table current when cutting a release or changing installer/runtime behavior.

## CLI commands

| Command | Purpose |
| --- | --- |
| `extract-session` | Export one Hermes session to raw JSON. |
| `build-context-packet` | Build raw export + context packet artifacts. |
| `promote-packet-query` | Legacy explicit promotion into wiki `queries/`. |
| `promote-packet-plan` | Legacy explicit promotion into wiki `plans/`. |
| `promote-unit-concept` | Legacy explicit promotion into wiki `concepts/`. |
| `promote-unit-architecture` | Legacy explicit promotion into wiki `architectures/`. |
| `run-e2e-pipeline` | Legacy full pipeline: packet + four durable pages + lint. Use temp wiki first. |
| `lint-wiki` | Lint human-facing wiki and internal packet graph. |
| `init-wiki` | Initialize human-facing wiki folders/config/templates. |
| `install-plugin` | Install `~/.hermes/plugins/agent-context-substrate` from packaged assets. |
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

By default, `run_session_finalize_pipeline(...)` is `packet-only` and does not create Obsidian pages. If you need the old four-page flow, run it first against a temporary wiki:

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
| `AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT` | installed `local_config.py` or `~/LLM Wiki` | Obsidian LLM Wiki root. |
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
│   ├── integration.py
│   ├── lint.py
│   ├── recovery.py
│   └── retrieval.py
├── tests/
└── data/
    ├── exports/   # generated, ignored by git
    └── index/     # generated ledger/cache, ignored by git
```

## Development and verification

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate
python -m pytest -q
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
- `data/exports/**/*.json` and `data/exports/**/*.md` may contain raw or summarized private session content.
- Obsidian wiki pages may contain personal project notes and provenance links.
- Never commit API keys, tokens, passwords, `.env` files, private connection strings, or raw private session exports.
- `.gitignore` excludes generated exports and local caches by default; review `git status --short` before every release.
- Prefer `packet-only` for live automation; use legacy full promotion only when you intentionally want durable wiki page writes.

## Documentation

- [한국어 README](./README.ko.md) — Korean overview, benefits, install path, and common usage.
- [User Guide EN](./docs/USER_GUIDE.en.md) — English storage layers, Hermes install, plugin/context-engine use, Telegram commands.
- [User Guide KO](./docs/USER_GUIDE.md) — Korean storage layers, Hermes install, plugin/context-engine use, Telegram commands.
- [Operations Guide](./docs/OPERATIONS.md) — runbooks, validation, troubleshooting, privacy and rollback notes.
- [Pipeline Reference](./docs/PIPELINE.md) — data flow, module responsibilities, artifact lifecycle.
- [Release Checklist](./docs/RELEASE_CHECKLIST.md) — source hygiene, install checks, privacy checks, verification gates.

## Current limitations

- The project is still a private alpha; keep the repository private until the release checklist and privacy review are complete.
- Curated promotion into the new human-facing folders (`01 지식`, `04 프로젝트`, etc.) is not yet automated.
- Legacy full promotion still writes old `queries/`, `concepts/`, `plans/`, and `architectures/` paths.
- Long-running Hermes gateway processes need restart after plugin/context-engine deployment.
