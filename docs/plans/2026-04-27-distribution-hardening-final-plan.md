# Agent Context Substrate Distribution Hardening Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn the current user-local alpha into a distributable Hermes Agent extension that a fresh user can install, initialize, attach to Hermes, and verify without Korean/Windows path assumptions.

**Architecture:** Keep `agent-context-substrate` as the standalone Python package and move installable Hermes integration assets into that package. The package owns fresh-user bootstrap, plugin/context-engine installation, health checks, and smoke validation; Hermes user plugin and context engine remain thin adapters.

**Tech Stack:** Python 3.11+, setuptools editable/installable package, argparse CLI, Hermes user plugin API, Hermes context-engine plugin API, pytest, temporary `HERMES_HOME`/`WIKI_PATH` smoke environments.

---

## Current state verified on 2026-04-27

- Harness package exists and is editable-installed in the project venv.
- Harness full test suite passes: `50 passed`.
- Hermes user plugin is enabled in the live Hermes config.
- `context.engine: agent_context_substrate` is active in `~/.hermes/config.yaml`.
- Context engine exposes `wiki_recovery_context`, `wiki_knowledge_search`, `wiki_knowledge_expand`.
- Recent compression bug has been fixed: `WikiHarnessContextEngine.compress(...)` accepts `focus_topic` and delegates large-context compaction to built-in `ContextCompressor`.
- Remaining distribution blockers:
  - user-specific defaults still exist in live plugin/context-engine files:
    - `~/.hermes/plugins/agent-context-substrate/config.py`
    - `<HERMES_AGENT_ROOT>/plugins/context_engine/agent_context_substrate/config.py`
  - project itself is not currently a git repository.
  - integration assets are installed manually, not from package-managed templates.
  - no fresh-user `init`, `install-plugin`, `install-context-engine`, or `doctor` command exists yet.
  - docs still contain local path examples that must be generalized before public distribution.

## Release definition of done

A release candidate is ready when all are true:

1. No source/plugin/context-engine default requires a user-specific Windows mount path.
2. A new user can run a package CLI flow:
   ```bash
   pip install -e .
   agent-context-substrate init-wiki --wiki-root <wiki>
   agent-context-substrate install-plugin --hermes-home <home> --project-root <project> --wiki-root <wiki>
   agent-context-substrate install-context-engine --hermes-agent-root <hermes-agent> --project-root <project> --wiki-root <wiki>
   agent-context-substrate doctor --hermes-home <home> --project-root <project> --wiki-root <wiki>
   ```
3. A fresh temp install smoke proves: init → plugin install → context-engine install → finalize packet-only → recovery → retrieval/expand → lint.
4. Live user environment is verified after install with the user's real Hermes home and Obsidian vault.
5. README/docs describe generic installation and privacy implications without relying on local paths.
6. Project has repository basics: git repo, `.gitignore`, LICENSE decision, pyproject metadata, release notes/checklist.

---

## Task 1: Add package-managed integration asset templates

**Objective:** Put the user plugin and context-engine files under the harness package so installers can copy from package resources instead of the current live `~/.hermes/...` locations.

**Files:**
- Create: `src/agent_context_substrate/assets/user_plugin/agent_context_substrate/plugin.yaml`
- Create: `src/agent_context_substrate/assets/user_plugin/agent_context_substrate/__init__.py`
- Create: `src/agent_context_substrate/assets/user_plugin/agent_context_substrate/config.py`
- Create: `src/agent_context_substrate/assets/user_plugin/agent_context_substrate/runtime.py`
- Create: `src/agent_context_substrate/assets/context_engine/agent_context_substrate/plugin.yaml`
- Create: `src/agent_context_substrate/assets/context_engine/agent_context_substrate/__init__.py`
- Create: `src/agent_context_substrate/assets/context_engine/agent_context_substrate/config.py`
- Create: `src/agent_context_substrate/assets/context_engine/agent_context_substrate/engine.py`
- Create: `src/agent_context_substrate/assets/context_engine/agent_context_substrate/formatting.py`
- Create: `src/agent_context_substrate/assets/context_engine/agent_context_substrate/recovery_loader.py`
- Create: `src/agent_context_substrate/assets/context_engine/agent_context_substrate/retrieval_tools.py`
- Modify: `pyproject.toml`
- Test: `tests/test_distribution_assets.py`

**Step 1: Write failing tests**

Test that the package includes every expected asset and that template text does not contain the local Korean/Windows path.

```python
from importlib.resources import files


def test_distribution_assets_are_packaged_without_user_paths():
    root = files("agent_context_substrate") / "assets"
    required = [
        "user_plugin/agent_context_substrate/plugin.yaml",
        "user_plugin/agent_context_substrate/__init__.py",
        "user_plugin/agent_context_substrate/config.py",
        "user_plugin/agent_context_substrate/runtime.py",
        "context_engine/agent_context_substrate/plugin.yaml",
        "context_engine/agent_context_substrate/__init__.py",
        "context_engine/agent_context_substrate/config.py",
        "context_engine/agent_context_substrate/engine.py",
        "context_engine/agent_context_substrate/formatting.py",
        "context_engine/agent_context_substrate/recovery_loader.py",
        "context_engine/agent_context_substrate/retrieval_tools.py",
    ]
    for rel in required:
        text = (root / rel).read_text(encoding="utf-8")
        windows_mount_user_prefix = "/mnt/" "c/Users/"
        windows_drive_user_prefix = "C:" + "\\\\Users\\\\"
        assert windows_mount_user_prefix not in text
        assert windows_drive_user_prefix not in text
```

**Step 2: Verify RED**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest tests/test_distribution_assets.py -q
```

Expected: FAIL because `assets/` does not exist.

**Step 3: Implement minimum code**

- Copy current live plugin/context-engine files into `src/agent_context_substrate/assets/...`.
- Replace local path defaults with generic env/config defaults:
  - project root: `AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT` or `~/.hermes/agent-context-substrate`
  - wiki root: `AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT`, `WIKI_PATH`, or `~/LLM Wiki`
- Update `pyproject.toml`:

```toml
[tool.setuptools.package-data]
agent_context_substrate = ["assets/**/*"]
```

**Step 4: Verify GREEN**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest tests/test_distribution_assets.py -q
```

Expected: PASS.

---

## Task 2: Add installer service module

**Objective:** Provide Python functions that initialize a wiki, copy plugin/context-engine assets, write `.env`-style integration defaults, and run diagnostics.

**Files:**
- Create: `src/agent_context_substrate/distribution.py`
- Modify: `src/agent_context_substrate/__init__.py`
- Test: `tests/test_distribution.py`

**Step 1: Write failing tests**

Create tests for:

- `init_wiki(wiki_root)` creates human-facing folders and `_system/config.yaml`.
- `install_user_plugin(hermes_home, project_root, wiki_root)` copies `agent-context-substrate` into `<hermes_home>/plugins/agent-context-substrate` and writes generic defaults.
- `install_context_engine(hermes_agent_root)` copies engine files into `<hermes_agent_root>/plugins/context_engine/agent_context_substrate`.
- `doctor(...)` reports structured checks.

Expected API skeleton:

```python
from agent_context_substrate.distribution import (
    init_wiki,
    install_user_plugin,
    install_context_engine,
    doctor,
)
```

**Step 2: Verify RED**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest tests/test_distribution.py -q
```

Expected: FAIL because module/functions do not exist.

**Step 3: Implement minimum code**

Recommended result dataclasses:

```python
@dataclass(frozen=True)
class InstallResult:
    status: str
    paths: dict[str, Path]
    messages: list[str]

@dataclass(frozen=True)
class DoctorReport:
    ok: bool
    checks: dict[str, bool]
    messages: list[str]
```

Implementation rules:

- Use `importlib.resources.files("agent_context_substrate") / "assets"` to locate templates.
- Never mutate live Hermes config in this module except when an explicit `enable` flag is later added.
- Copy files idempotently.
- Do not overwrite user-modified plugin files unless `overwrite=True`.
- Create backups before overwrite:
  - `agent-context-substrate.bak-<timestamp>`
  - `agent_context_substrate.bak-<timestamp>`
- `doctor` should check:
  - package importable
  - `project_root/src/agent_context_substrate` exists or package is installed
  - `hermes_home/state.db` exists
  - `wiki_root` exists and has `_system/config.yaml`
  - user plugin files exist
  - context-engine files exist
  - no local Korean path appears in installed templates

**Step 4: Verify GREEN**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest tests/test_distribution.py -q
```

Expected: PASS.

---

## Task 3: Add CLI commands for fresh install and diagnostics

**Objective:** Expose the distribution module through the existing `agent-context-substrate` CLI.

**Files:**
- Modify: `src/agent_context_substrate/cli.py`
- Test: `tests/test_cli.py`

**New commands:**

```text
init-wiki
install-plugin
install-context-engine
doctor
fresh-install-smoke
```

**Command contracts:**

```bash
agent-context-substrate init-wiki --wiki-root <path>
agent-context-substrate install-plugin --hermes-home <path> --project-root <path> --wiki-root <path> [--overwrite]
agent-context-substrate install-context-engine --hermes-agent-root <path> --project-root <path> --wiki-root <path> [--overwrite]
agent-context-substrate doctor --hermes-home <path> --project-root <path> --wiki-root <path> --hermes-agent-root <path>
agent-context-substrate fresh-install-smoke --session-id <id> --hermes-home <path> --project-root <path> --wiki-root <path> --hermes-agent-root <path>
```

**Step 1: Write failing tests**

- Test `build_parser()` includes all commands.
- Test each command invokes the distribution function and prints output paths/status.
- Test `doctor` exits `1` if `--fail-on-issues` is set and report is not ok.

**Step 2: Verify RED**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest tests/test_cli.py -q
```

Expected: FAIL for missing commands.

**Step 3: Implement minimum code**

Keep `main(argv: list[str] | None = None)` intact. Print exact paths and concise status lines, not prose-only output.

**Step 4: Verify GREEN**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest tests/test_cli.py -q
```

Expected: PASS.

---

## Task 4: Add fresh-install smoke pipeline

**Objective:** Prove distribution works from empty/temp roots without using the real Obsidian vault or existing project ledger.

**Files:**
- Modify: `src/agent_context_substrate/distribution.py`
- Test: `tests/test_fresh_install_smoke.py`

**Smoke flow:**

1. Create temp `HERMES_HOME`.
2. Use a copied or fixture `state.db` with at least one session.
3. Create temp `project_root` with symlink or installed package access.
4. Create temp `wiki_root`.
5. Run `init_wiki`.
6. Run `install_user_plugin`.
7. Run `install_context_engine`.
8. Run `run_session_finalize_pipeline(..., promotion_mode="packet-only")`.
9. Build recovery brief.
10. Search retrieval with `search_knowledge(...)`.
11. Expand first hit with `expand_hit(...)`.
12. Run lint and assert issue count is zero for the fresh temp wiki/artifact graph.

**Step 1: Write failing test**

Expected high-level assertion:

```python
def test_fresh_install_smoke_runs_packet_recovery_retrieval_and_lint(tmp_path):
    result = run_fresh_install_smoke(...)
    assert result.ok is True
    assert result.artifacts["packet_json_path"].exists()
    assert result.artifacts["recovery_json_path"].exists()
    assert result.retrieval_hit_count > 0
    assert result.lint_issue_count == 0
```

**Step 2: Verify RED**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest tests/test_fresh_install_smoke.py -q
```

Expected: FAIL until `run_fresh_install_smoke` exists.

**Step 3: Implement minimum code**

Add one orchestration function:

```python
def run_fresh_install_smoke(
    *,
    session_id: str,
    hermes_home: Path,
    project_root: Path,
    wiki_root: Path,
    hermes_agent_root: Path | None = None,
) -> FreshInstallSmokeResult:
    ...
```

**Step 4: Verify GREEN**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest tests/test_fresh_install_smoke.py -q
```

Expected: PASS.

---

## Task 5: Generalize path defaults in live integration templates

**Objective:** Remove user-specific defaults from distributable code and installed live adapter files.

**Files:**
- Modify: `src/agent_context_substrate/assets/user_plugin/agent_context_substrate/config.py`
- Modify: `src/agent_context_substrate/assets/context_engine/agent_context_substrate/config.py`
- Later installed copy targets:
  - `~/.hermes/plugins/agent-context-substrate/config.py`
  - `<hermes-agent-root>/plugins/context_engine/agent_context_substrate/config.py`
- Test: `tests/test_distribution_assets.py`

**Policy:**

- For public templates:
  - project root default: `~/.hermes/agent-context-substrate`
  - wiki root default: `~/LLM Wiki`
- For this user's live installation, explicit env/config can still point to:
  - `<PROJECT_ROOT>`
  - `<WIKI_ROOT>`
- Public source must not hardcode those values.

**Verification command:**

```bash
cd '<PROJECT_ROOT>' && python - <<'PY'
from pathlib import Path
for base in [Path('src'), Path('docs'), Path('README.md')]:
    files = [base] if base.is_file() else base.rglob('*')
    for path in files:
        if path.is_file() and path.suffix in {'.py', '.md', '.toml', '.yaml', '.yml'}:
            text = path.read_text(encoding='utf-8', errors='ignore')
            windows_mount_user_prefix = '/mnt/' 'c/Users/'
            assert windows_mount_user_prefix not in text, path
PY
```

For generated historical artifacts under `data/exports/`, do not block release solely on old local paths; exclude them from the public package/repo or document them as generated/private artifacts.

---

## Task 6: Add repository/release hygiene

**Objective:** Make the project a real distributable repository instead of a loose working directory.

**Files:**
- Create/modify: `.gitignore`
- Create: `LICENSE` after user chooses license, likely MIT if no objection.
- Modify: `pyproject.toml`
- Create: `docs/RELEASE_CHECKLIST.md`

**Required `.gitignore` policy:**

```gitignore
.venv/
__pycache__/
.pytest_cache/
*.pyc

# private/generated harness artifacts
data/exports/
data/index/session_ledger.json

# local Hermes/Obsidian paths and scratch plans
.hermes/
```

**pyproject metadata to fill before public release:**

```toml
license = { text = "MIT" }
keywords = ["hermes-agent", "obsidian", "context", "rag", "wiki"]
classifiers = [
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "License :: OSI Approved :: MIT License",
]
```

**Verification:**

```bash
cd '<PROJECT_ROOT>' && git init && git status --short
```

Do not commit private generated artifacts.

---

## Task 7: Update repository-facing docs after implementation

**Objective:** Make README and docs match the actual install/doctor/smoke flow.

**Files:**
- Modify: `README.md`
- Modify: `docs/USER_GUIDE.md`
- Modify: `docs/OPERATIONS.md`
- Modify: `docs/PIPELINE.md`
- Create/modify: `docs/RELEASE_CHECKLIST.md`

**Content requirements:**

- Replace local path quick start with generic paths.
- Add install options:
  - standalone package only
  - package + Hermes user plugin
  - package + context engine
- Add privacy warning:
  - raw `state.db` exports may include private conversation content, paths, and sensitive operational context.
  - never publish `data/exports/` from a personal Hermes home.
- Add `packet-only` default explanation.
- Add `full` promotion as explicit legacy/advanced mode only.
- Add troubleshooting section for:
  - plugin enabled but not loaded
  - `context.engine` not selected
  - missing `state.db`
  - wrong `WIKI_PATH`
  - gateway restart required after integration changes

**Verification:**

- Markdown code fences balanced.
- Relative docs links exist.
- No local Korean path appears in public docs except in an explicitly labeled local-development appendix.

---

## Task 8: Run full local verification before touching live install

**Objective:** Prove the package changes are safe before installing into the user's live Hermes environment.

**Commands:**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest -q

cd '<PROJECT_ROOT>' && . .venv/bin/activate && .venv/bin/agent-context-substrate fresh-install-smoke \
  --session-id 20260420_100039_36789dfa \
  --hermes-home "$(mktemp -d)" \
  --project-root "$(mktemp -d)" \
  --wiki-root "$(mktemp -d)" \
  --hermes-agent-root '<HERMES_AGENT_ROOT>'

cd '<HERMES_AGENT_ROOT>' && . venv/bin/activate && python -m pytest \
  tests/plugins/test_agent_context_substrate_plugin.py \
  tests/agent/test_agent_context_substrate_context_engine.py \
  tests/run_agent/test_agent_context_substrate_context_engine_active.py \
  tests/run_agent/test_plugin_context_engine_init.py \
  tests/agent/test_context_engine.py \
  tests/gateway/test_session_boundary_hooks.py \
  tests/cli/test_session_boundary_hooks.py -q
```

Expected:

- Harness suite passes.
- Fresh-install smoke returns `ok=True`.
- Hermes targeted suite passes.

---

## Task 9: Install and verify directly in this user's environment

**Objective:** Perform the final requested live install/test/verification on the user's actual WSL + Hermes + Obsidian setup.

**Pre-flight backup:**

```bash
cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak-agent-context-substrate-release-$(date +%Y%m%d-%H%M%S)
cp -a ~/.hermes/plugins/agent-context-substrate ~/.hermes/plugins/agent-context-substrate.bak-release-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
cp -a ~/.hermes/hermes-agent/plugins/context_engine/agent_context_substrate ~/.hermes/hermes-agent/plugins/context_engine/agent_context_substrate.bak-release-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
```

**Install package into both envs:**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && pip install -e '.[dev]'
cd '<HERMES_AGENT_ROOT>' && . venv/bin/activate && pip install -e '<PROJECT_ROOT>'
```

**Install adapters from packaged assets:**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && \
agent-context-substrate install-plugin \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

cd '<PROJECT_ROOT>' && . .venv/bin/activate && \
agent-context-substrate install-context-engine \
  --hermes-agent-root ~/.hermes/hermes-agent \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite
```

**Live diagnostics:**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && \
agent-context-substrate doctor \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --hermes-agent-root ~/.hermes/hermes-agent \
  --fail-on-issues
```

**Live smoke without mutating durable wiki pages:**

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && \
AGENT_CONTEXT_SUBSTRATE_PROMOTION_MODE=packet-only \
agent-context-substrate lint-wiki \
  --project-root '<PROJECT_ROOT>' \
  --report-id release-live-wiki-check \
  --fail-on-issues
```

**Hermes runtime verification:**

```bash
cd '<HERMES_AGENT_ROOT>' && . venv/bin/activate && hermes plugins list
cd '<HERMES_AGENT_ROOT>' && . venv/bin/activate && python - <<'PY'
from plugins.context_engine import load_context_engine
engine = load_context_engine('agent_context_substrate')
print('engine', getattr(engine, 'name', None))
print('tools', [schema['name'] for schema in engine.get_tool_schemas()] if engine else [])
PY
```

Expected:

- plugin status: `agent-context-substrate enabled`
- context engine: `agent_context_substrate`
- tools include:
  - `wiki_recovery_context`
  - `wiki_knowledge_search`
  - `wiki_knowledge_expand`

**Gateway restart:**

Because long-running gateway processes cache plugin/context-engine modules, restart after install:

```bash
cd '<HERMES_AGENT_ROOT>' && . venv/bin/activate && hermes gateway restart
```

Only run this after confirming the user is okay with the Telegram gateway restart.

---

## Task 10: Release candidate decision

**Objective:** Decide whether the harness is ready for other Hermes Agent users.

**Ready if:**

- all tests pass;
- fresh install smoke passes;
- live install smoke passes;
- no public source/template default contains personal paths;
- README/docs describe install and privacy accurately;
- repo initialized and private artifacts excluded;
- rollback instructions are documented.

**Not ready if:**

- install requires manual copying from `~/.hermes/...`;
- fresh user needs to know the user's local path layout;
- gateway restart is required but undocumented;
- raw exports are accidentally included in the public repo;
- `doctor` cannot clearly explain degraded health.

## Rollback commands

```bash
cp ~/.hermes/config.yaml.bak-agent-context-substrate-release-<timestamp> ~/.hermes/config.yaml
rm -rf ~/.hermes/plugins/agent-context-substrate
cp -a ~/.hermes/plugins/agent-context-substrate.bak-release-<timestamp> ~/.hermes/plugins/agent-context-substrate
rm -rf ~/.hermes/hermes-agent/plugins/context_engine/agent_context_substrate
cp -a ~/.hermes/hermes-agent/plugins/context_engine/agent_context_substrate.bak-release-<timestamp> ~/.hermes/hermes-agent/plugins/context_engine/agent_context_substrate
cd '<HERMES_AGENT_ROOT>' && . venv/bin/activate && hermes gateway restart
```
