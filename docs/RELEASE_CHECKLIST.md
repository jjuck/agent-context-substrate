# Release Checklist

Use this checklist before publishing or updating Agent Context Substrate releases. The repository lives at `https://github.com/jjuck/agent-context-substrate` and is public as of `v0.1.0`; the current local release candidate is `v0.2.0`. Keep generated/private local artifacts out of tracked source and release assets.

## 1. Source hygiene

- [ ] `git status --short --branch` is clean and tracking `origin/main`.
- [ ] `data/exports/`, `data/atoms/`, `data/promotions/`, `data/wiki_patches/`, `data/lint/`, `data/cache/`, and generated `data/index/` artifacts are ignored or intentionally excluded.
- [ ] `.hermes/`, `.venv/`, caches, and `*.egg-info/` are ignored.
- [ ] `LICENSE` exists and matches `pyproject.toml` metadata.
- [ ] GitHub remote `origin` points to `https://github.com/jjuck/agent-context-substrate.git`.
- [ ] `pyproject.toml` has name, version, description, license, keywords, classifiers, and CLI entrypoint.

## 2. Personal path audit

Run:

```bash
python - <<'PY'
from pathlib import Path
markers = ['/' + 'mnt/' + 'c/Users/', 'C:' + '\\\\Users\\\\']
roots = [Path('src'), Path('tests'), Path('README.md'), Path('README.ko.md'), Path('docs'), Path('spec.md'), Path('CHANGELOG.md'), Path('pyproject.toml')]
allowed = {'docs/plans/2026-04-27-distribution-hardening-final-plan.md'}
for root in roots:
    files = [root] if root.is_file() else root.rglob('*')
    for path in files:
        if not path.is_file() or path.as_posix() in allowed:
            continue
        if path.suffix not in {'.py', '.md', '.toml', '.yaml', '.yml', '.txt'}:
            continue
        text = path.read_text(encoding='utf-8', errors='ignore')
        for marker in markers:
            if marker in text:
                raise SystemExit(f'personal path marker in {path}: {marker}')
print('personal path audit ok')
PY
```

## 3. Test suite and lint

```bash
python -m pytest -q
ruff check .
```

Expected current public alpha baseline: `337 passed, 12 skipped` and `All checks passed!` from Ruff.

For a Windows Codex app release, also verify the Windows-facing one-shot install docs and hook-trust instructions in `README.ko.md`, `README.md`, and `docs/WINDOWS_CODEX_APP_SETUP*.md`.

## 4. Fresh-install smoke

Use temp roots so no durable Obsidian vault is mutated:

```bash
TMP_PROJECT=$(mktemp -d)
TMP_WIKI=$(mktemp -d)
TMP_AGENT=$(mktemp -d)
agent-context-substrate fresh-install-smoke \
  --session-id <known-session-id> \
  --hermes-home ~/.hermes \
  --project-root "$TMP_PROJECT" \
  --wiki-root "$TMP_WIKI" \
  --hermes-agent-root "$TMP_AGENT"
```

Expected:

```text
fresh-install-smoke ok=True
retrieval_hit_count>0  # current baseline: 1
lint_issue_count=0
```

## 5. Live install smoke

Back up before overwrite:

```bash
TS=$(date +%Y%m%d-%H%M%S)
cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak-agent-context-substrate-release-$TS
cp -a ~/.hermes/plugins/agent-context-substrate ~/.hermes/plugins/agent-context-substrate.bak-release-$TS 2>/dev/null || true
cp -a ~/.hermes/hermes-agent/plugins/context_engine/agent_context_substrate ~/.hermes/hermes-agent/plugins/context_engine/agent_context_substrate.bak-release-$TS 2>/dev/null || true
```

Install:

```bash
agent-context-substrate install-plugin \
  --hermes-home ~/.hermes \
  --project-root <project-root> \
  --wiki-root <wiki-root> \
  --overwrite

agent-context-substrate install-context-engine \
  --hermes-agent-root ~/.hermes/hermes-agent \
  --project-root <project-root> \
  --wiki-root <wiki-root> \
  --overwrite
```

For Codex live install smoke, verify the user-facing paths before running:

```text
Codex source: ~/.codex/state_5.sqlite and ~/.codex/sessions/**/rollout-*.jsonl
LLM Wiki: <wiki-root>
ACS artifacts: <project-root>/data/
```

Then install and check status:

```bash
agent-context-substrate setup-codex \
  --codex-home ~/.codex \
  --project-root <project-root> \
  --wiki-root <wiki-root> \
  --yes

agent-context-substrate doctor-codex \
  --codex-home ~/.codex \
  --project-root <project-root> \
  --wiki-root <wiki-root> \
  --fail-on-issues

agent-context-substrate config-codex paths \
  --codex-home ~/.codex \
  --project-root <project-root> \
  --wiki-root <wiki-root>
```

Expected: `doctor-codex ok=True`, `hook_primary_installed=ok`, `watcher_fallback_available=ok`, and paths for `state_5.sqlite`, `Documents\LLM Wiki`, and `data\...`. Default Windows setup should not leave an ACS Stop hook in `~/.codex/hooks.json`; use `--user-hook-fallback` only when plugin-bundled hooks are unavailable. Codex still requires `/hooks` or `Hooks need review` review/trust before non-managed command hooks run; do not document or use trust bypass as a normal install path.

For Codex LLM summary smoke, set `summary_mode=auto` in the installed Codex plugin config, run an interactive Stop hook smoke, and verify summary artifacts under `data/exports/summaries/`. The metadata should show either `mode=codex-cli` or heuristic fallback fields such as `fallback_from=auto` / `fallback_reason=codex_cli_unavailable`; ledger artifact paths should include the requested `summary_mode` plus actual summary mode/fallback metadata.

Windows one-shot bootstrap smoke:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -CheckOnly
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
```

If prerequisite install instructions are tested, use these winget package IDs: `Python.Python.3.13`, `Git.Git`, and optional `Obsidian.Obsidian`.

Verify:

```bash
agent-context-substrate doctor \
  --hermes-home ~/.hermes \
  --project-root <project-root> \
  --wiki-root <wiki-root> \
  --hermes-agent-root ~/.hermes/hermes-agent \
  --fail-on-issues
```

## 6. Runtime checks

```bash
cd ~/.hermes/hermes-agent
. venv/bin/activate
hermes plugins list
python - <<'PY'
from plugins.context_engine import load_context_engine
engine = load_context_engine('agent_context_substrate')
print('engine', getattr(engine, 'name', None))
print('tools', [schema['name'] for schema in engine.get_tool_schemas()] if engine else [])
PY
```

Expected:

- `agent-context-substrate` plugin is enabled.
- engine is `agent_context_substrate`.
- tools include `wiki_recovery_context`, `wiki_knowledge_search`, and `wiki_knowledge_expand`.

## 7. Privacy review

- [ ] Do not publish generated/private substrate artifact directories such as `data/exports/`, `data/atoms/`, `data/promotions/`, `data/wiki_patches/`, `data/lint/`, or `data/cache/`.
- [ ] Do not publish raw `state.db` exports.
- [ ] Confirm docs warn that raw session exports may include private conversation content, local paths, commands, and sensitive operational context.

## 8. Gateway restart

After installing plugin/context-engine changes into a live Hermes gateway, restart the gateway so cached modules are refreshed:

```bash
hermes gateway restart
```

Do this only when it is acceptable to interrupt active messaging sessions.


## 9. Current public alpha baseline

Latest verified local baseline for the v0.2.0 release candidate after spec pipeline implementation, real-wiki dry-run validation, semantic atom/lint/patch expansion, and release cleanup:

```text
commit: use `git log -1 --oneline` at audit time
repo: https://github.com/jjuck/agent-context-substrate
visibility: public
project tests: 337 passed, 12 skipped
fresh-install-smoke: ok=True retrieval_hit_count=1 expanded_content_length=14195 lint_issue_count=0
real wiki lint: checked_pages=15 missing_provenance=0 orphan_pages=0 missing_from_index=0 broken_wikilinks=0
live Codex runtime: plugin agent-context-substrate, Stop hook installed, watcher fallback available
live Hermes runtime: plugin agent-context-substrate, context engine agent_context_substrate, gateway restarted
```

Refresh this section whenever a release candidate changes code, docs, installer behavior, or runtime configuration.
