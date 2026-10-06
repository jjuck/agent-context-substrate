# Release Checklist

Record the candidate commit, Python/platform, exact commands, exit codes, skips and limitations for each release. This checklist defines checks to run; it is not evidence that a live installation or test run succeeded. Python 3.11+ is required by `pyproject.toml`.

For docs-only edits, run section 1 checks relevant to the changed files; pytest, builds and install smoke are not required. Sections 2–4 apply to runtime/package releases or changes that affect those behaviors.

## 1. Read-only source and documentation review

- [ ] Review `git status --short --branch`, `git diff --check` and the staged diff; release only intended source files.
- [ ] Match version, license and CLI metadata in `pyproject.toml`, package metadata and changelog.
- [ ] Exclude private/generated `data/`, session DBs, rollout exports, vaults, local configs, credentials, caches and environment directories from commits and release assets.
- [ ] Audit tracked source/docs for personal paths and secrets; generic placeholders must be consistent. Review any intentional historical examples explicitly.
- [ ] Keep [Korean](USER_GUIDE.md) / [English](USER_GUIDE.en.md) guides and [Windows Korean](WINDOWS_CODEX_APP_SETUP.ko.md) / [English](WINDOWS_CODEX_APP_SETUP.md) instructions aligned with local CLI defaults and hook trust behavior.
- [ ] For Pages/diagram changes, confirm publishing from `main` `/docs`, `docs/index.html` redirects to `site/`, and `docs/site/index.html` plus `docs/site/preview.png` resolve. Check deployed URLs after publication; local file checks alone do not prove deployment.
- [ ] Check local links and command options against source or `--help`. Record these as documentation checks, not test execution or live smoke results.

## 2. Execute tests, lint and package build

Use a disposable checkout and virtual environment. These commands install dependencies and create build/test outputs; they are not read-only checks. Bash examples assume the repository root and an activated environment; on Windows activate `.venv/Scripts/Activate.ps1` instead of `.venv/bin/activate`.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]' build
python -m pytest -q
python -m ruff check .
python -m build --outdir '<DIST_ROOT>'
```

- [ ] Run on the minimum supported Python and each release target platform; retain results without hard-coded test counts.
- [ ] Explain skips. Tests marked `integration` require a local Hermes Agent checkout/venv; skips do not establish Hermes runtime compatibility.
- [ ] Review `tests/test_distribution_assets.py`, distribution, Codex setup/hook and fresh-install fixture tests in the full suite.
- [ ] Inspect wheel and sdist contents, including the hidden Codex `.codex-plugin/plugin.json`, hooks, skills, Hermes plugin and context-engine assets. Reject bytecode, caches and private data.

Install the built wheel into another clean environment, then run outside the source checkout so editable imports cannot mask packaging defects:

```bash
python -m venv '<PACKAGE_TEST_ENV>'
. '<PACKAGE_TEST_ENV>/bin/activate'
python -m pip install '<DIST_ROOT>/<WHEEL_FILE>'
cd '<EMPTY_DIRECTORY>'
python -m agent_context_substrate.cli --help
agent-context-substrate --help
python -c "from importlib.resources import files; r=files('agent_context_substrate')/'assets'; print('\n'.join(str(p) for p in r.rglob('*') if p.is_file()))"
```

- [ ] Compare installed resources to `REQUIRED_ASSET_FILES` in `tests/test_distribution_assets.py`; check wheel version and import location. Build dependencies may require network access.

## 3. Isolated install and end-to-end smoke

Use the wheel environment. Prepare disposable project, wiki, Hermes home and Hermes Agent roots. The Hermes home must contain a valid fixture `state.db` with a known session; the fixture test in `tests/test_fresh_install_smoke.py` shows the required input. For real-session validation, use a consistent private DB snapshot in that disposable home and keep outputs private.

**All roots must be disposable:** `fresh-install-smoke` installs/overwrites the plugin in its supplied Hermes home, initializes the wiki, creates a project import shim and optionally installs the context engine. Temporary project/wiki roots alone do not protect a live Hermes home.

```bash
agent-context-substrate fresh-install-smoke --session-id '<KNOWN_SESSION_ID>' --hermes-home '<TEMP_HERMES_HOME>' --project-root '<TEMP_PROJECT_ROOT>' --wiki-root '<TEMP_WIKI_ROOT>' --hermes-agent-root '<TEMP_AGENT_ROOT>'
agent-context-substrate doctor --hermes-home '<TEMP_HERMES_HOME>' --project-root '<TEMP_PROJECT_ROOT>' --wiki-root '<TEMP_WIKI_ROOT>' --hermes-agent-root '<TEMP_AGENT_ROOT>' --fail-on-issues
```

- [ ] Require `ok=True`, existing raw/packet/lint/recovery artifacts, retrieval hits and expanded content greater than zero, and no lint issues. Retain actual results.
- [ ] Verify Codex packaged installation in disposable Codex home, project, wiki **and personal marketplace** roots with explicit `--personal-marketplace-root`; setup otherwise reaches the user's marketplace/cache. Use `setup-codex --dry-run` before the write.
- [ ] Use a fixture Codex DB/rollout for finalize, hook and watcher checks; observe hook event output and artifact creation. `watcher_fallback_available=ok` alone is not evidence of a running watcher.

## 4. Optional live acceptance and release record

Live acceptance is a separate, explicit operation. Back up source DBs, vault/data, runtime configs, plugins, user hooks and marketplace settings first. Follow [operations](OPERATIONS.md); record which live checks were performed and which were omitted.

- [ ] Review actual paths before any installer overwrite, `diagnose-codex --fix`, Windows bootstrap or gateway restart. These actions write files or interrupt runtime sessions.
- [ ] Review/trust Codex hooks through `/hooks`; verify actual execution without a trust bypass. Confirm Hermes plugin enablement, context-engine selection and tool availability when Hermes is in scope.
- [ ] If linting a real vault, set `WIKI_PATH` explicitly and run `lint-wiki --project-root '<PROJECT_ROOT>' --report-id release-check --fail-on-issues`; this reads the vault but writes reports under ACS `data/exports/lint/`.
- [ ] Keep release notes accurate: separate fixture tests, wheel checks, isolated smoke, docs review and live runtime evidence. Include failures/skips and unresolved limitations; never carry forward old numerical baselines as current proof.
