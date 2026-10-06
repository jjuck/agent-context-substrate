# Agent Context Substrate

**Keep decisions, progress, and source evidence from Hermes and Codex conversations so the next task can resume with useful context.**

![Status](https://img.shields.io/badge/status-alpha-orange) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) [![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[한국어](README.ko.md) · [Quick start](#quick-start) · [User guide](docs/USER_GUIDE.en.md) · [Interactive architecture](https://jjuck.github.io/agent-context-substrate/site/)

ACS is a local Python package and CLI. It reads Hermes `state.db` or Codex thread metadata and rollout JSONL, then writes reusable context packets and recovery briefs. Codex source files are read-only inputs; generated artifacts stay under the configured project's `data/` directory.

## Architecture

[![ACS architecture: session capture, local artifacts, search and recovery](docs/site/preview.png)](https://jjuck.github.io/agent-context-substrate/site/)

**Click the image to explore the diagram.** Nodes link to source evidence; the viewer supports zoom, themes, and export. The diagram reflects source revision [`ea83152`](https://github.com/jjuck/agent-context-substrate/commit/ea83152d01dccecf359164971de8e592cad577f3). It is a static architecture snapshot, not a live runtime monitor.

## What it does

- Exports sessions with provenance and builds rule-based summaries, `ContextPacket` JSON/Markdown, and recovery briefs.
- Provides read-only lexical retrieval over wiki pages, packets, recovery artifacts, and topic maps. Raw-message retrieval is optional.
- Integrates with Codex through a non-MCP plugin and a project-scoped Stop hook, with an explicit watcher fallback.
- Integrates with Hermes through session-finalize hooks and a context engine for recovery loading and request-time search tools.
- Offers optional V2 summaries, structured atoms, promotion review, and wiki patch proposals.

The default is **`packet-only`**: generated artifacts remain outside the human-facing Obsidian wiki. Wiki writes require explicit promotion or patch application. V2/LLM summarization is opt-in; the standalone CLI rejects `agent-llm`/`hybrid`; these modes require an injected router through a host integration or core API.

## Quick start

Requires **Python 3.11+** and Git. This is alpha software; consult the guides before using a live session store or wiki.

### Windows + Codex

```powershell
git clone https://github.com/jjuck/agent-context-substrate.git
cd agent-context-substrate
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
.\.venv\Scripts\agent-context-substrate.exe doctor-codex --fail-on-issues
.\.venv\Scripts\agent-context-substrate.exe config-codex paths
```

The script prints the selected paths before setup. By default, generated artifacts use the checkout as `project_root`; the Stop hook skips working directories outside that root. The bootstrap installs ACS from `-ProjectRoot`, so that path must be an ACS checkout. To capture a selected thread from another repository, use manual finalize; the watcher scans more broadly as described in the guide.

Installed hooks must still be reviewed and trusted in Codex. `doctor-codex` confirms files and configuration, not runtime hook trust. See the [Windows setup guide](docs/WINDOWS_CODEX_APP_SETUP.md) for path selection, trust review, prerequisite installation, and watcher fallback.

### Portable package setup

```bash
git clone https://github.com/jjuck/agent-context-substrate.git
cd agent-context-substrate
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
agent-context-substrate --help
```

On Windows, use `.venv\Scripts\python.exe -m pip install -e .` and `.venv\Scripts\agent-context-substrate.exe --help` after creating the venv.

Then follow the [user guide](docs/USER_GUIDE.en.md) for Hermes asset installation and activation, portable Codex setup, or manual capture. Installing the package alone does not activate an agent integration.

## Everyday commands

Replace placeholder paths and IDs before running; `project_root` is the generated-artifact root and the Codex hook's working-directory boundary.

```bash
# Inspect Codex source and installation status.
agent-context-substrate codex-status --codex-home '<CODEX_HOME>'

# Capture one Codex thread without MCP.
agent-context-substrate codex-finalize \
  --thread-id '<THREAD_ID>' --codex-home '<CODEX_HOME>' \
  --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>'

# Find where prior work stopped; results include hit IDs for expand-hit.
agent-context-substrate search-knowledge \
  --query 'next steps' --mode recovery \
  --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>'
```

Use `<command> --help` for the current flags. The [user guide](docs/USER_GUIDE.en.md) covers Hermes capture, search expansion, V2 summaries, and review-first wiki changes.

## Documentation

| Need | Document |
| --- | --- |
| Install, capture, retrieve, and review wiki updates | [English user guide](docs/USER_GUIDE.en.md) / [한국어](docs/USER_GUIDE.md) |
| Windows Codex setup and hook trust | [English setup](docs/WINDOWS_CODEX_APP_SETUP.md) / [한국어](docs/WINDOWS_CODEX_APP_SETUP.ko.md) |
| Runtime flow, artifacts, and adapter limits | [Pipeline](docs/PIPELINE.md) |
| Diagnostics, backups, and recovery | [Operations](docs/OPERATIONS.md) |
| Reproducible release checks | [Release checklist](docs/RELEASE_CHECKLIST.md) |
| Version history | [Changelog](CHANGELOG.md) |

## Development

In an activated environment:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check .
git diff --check
```

Report results with the revision and platform tested. Historical test counts or a previous live installation do not verify a new checkout. Live integration smoke checks require explicit session and installation roots; see the release checklist.

## Privacy and limitations

- Session databases, rollouts, exports, and summaries can contain private conversations, tool output, credentials, and local paths. Do not commit them.
- `.gitignore` excludes the standard generated-artifact locations, not every possible report name or custom output path; review staged files before publishing.
- Search is local and lexical, not a hosted vector database. LLM summary safety options reduce input exposure but do not guarantee removal of every secret.
- Hermes and local Codex are the packaged integrations. Other agents require adapters. Hermes must reload updated plugin/context-engine modules.
- Hook installation, hook trust, successful execution, and artifact quality are separate checks. Review wiki proposals before applying them.

Licensed under [MIT](LICENSE).
