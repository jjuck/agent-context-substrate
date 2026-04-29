# Release Checklist

Use this checklist before distributing Agent Context Substrate to other Hermes Agent users.

## 1. Source hygiene

- [ ] `git status --short` contains no accidental private/generated artifacts.
- [ ] `data/exports/` and `data/index/session_ledger.json` are ignored or intentionally excluded.
- [ ] `.hermes/`, `.venv/`, caches, and `*.egg-info/` are ignored.
- [ ] `LICENSE` exists and matches `pyproject.toml` metadata.
- [ ] `pyproject.toml` has name, version, description, license, keywords, classifiers, and CLI entrypoint.

## 2. Personal path audit

Run:

```bash
python - <<'PY'
from pathlib import Path
markers = ['/mnt/c/Users/', 'C:\\Users\\']
roots = [Path('src'), Path('tests'), Path('README.md'), Path('docs')]
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

## 3. Test suite

```bash
python -m pytest -q
```

Expected: all tests pass.

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
retrieval_hit_count=>0
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

- [ ] Do not publish `data/exports/` from a real Hermes home.
- [ ] Do not publish raw `state.db` exports.
- [ ] Confirm docs warn that raw session exports may include private conversation content, local paths, commands, and sensitive operational context.

## 8. Gateway restart

After installing plugin/context-engine changes into a live Hermes gateway, restart the gateway so cached modules are refreshed:

```bash
hermes gateway restart
```

Do this only when it is acceptable to interrupt active messaging sessions.
