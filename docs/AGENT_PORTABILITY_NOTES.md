# Agent Portability Notes

This note records portability findings that matter when Agent Context Substrate grows across local agent integrations.

## Current scope

The current packaged integrations target **Hermes Agent** and a **non-MCP Codex local session source**.

The issues below were first written during a Hermes/WSL-focused phase. Some have since been addressed for the Windows Codex app path, but they remain useful checks before claiming broad support for additional agents or every native Windows workflow.

## Current known baseline

Current local Windows baseline:

```text
python -m pytest -q  # 408 passed, 12 skipped
ruff check .         # All checks passed
```

This proves the current test suite on the local Windows environment. It does not prove every third-party Windows configuration, shell, symlink policy, or future agent adapter.

## Portability status by area

### 1. Home directory resolution: addressed for current adapters

`HarnessPaths` now honors an explicit `home_dir`, then `HOME`, then platform home expansion. Explicit `hermes_home` and `wiki_root` values take precedence over environment values. Tests cover a Windows-style `USERPROFILE` alongside a test-provided `HOME`.

Codex wiki roots use a separate portable resolver. Its precedence is `AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT`, `WIKI_PATH`, installed config, then the `%USERPROFILE%\Documents\LLM Wiki` template. The configured template and effective path are reported separately.

Remaining boundary:

- Future adapters must inject their own state/session roots instead of assuming Hermes or Codex home layouts.
- `config.py` still contains legacy generic defaults; new adapter code should use typed adapter setup or explicit `HarnessPaths` inputs.

### 2. Custom-command parsing: addressed on Windows and POSIX

`CustomCommandSummarizerBackend` keeps `shell=False`. POSIX uses `shlex.split(...)`; Windows uses `CommandLineToArgvW` semantics through the platform API. Regression tests cover quoted executable and script paths with spaces.

Configuration should still quote any path containing spaces. External command failure remains observable through summary fallback metadata rather than becoming a silent success.

### 3. Symlink tests are privilege-sensitive on Windows

Several security tests intentionally create symlinks to verify path-escape hardening. On Windows, symlink creation may require Developer Mode or elevated privileges. If tests directly call `Path.symlink_to(...)` without handling `OSError`, the test can fail even though the production containment logic is correct.

Potential symptoms:

- `WinError 1314` or similar permission failures in symlink tests.
- Native Windows CI fails while WSL/Linux passes.

Future action before cross-platform CI:

- Add a shared test helper for symlink creation.
- Call `pytest.skip(...)` on symlink privilege errors.
- Keep the production checks: resolved paths must remain under the allowed project/wiki root.

### 4. Local config representation: monitored compatibility boundary

The legacy Hermes installer writes local Python config such as:

```python
from pathlib import Path

PROJECT_ROOT = Path('...')
WIKI_ROOT = Path('...')
```

For Windows paths, the generated Python source may contain escaped backslashes. The config can still execute correctly, but tests that assert raw `str(path)` appears as a substring can fail because Python source escaping and runtime `Path` values are different representations.

Current rule:

- Load or execute generated `local_config.py` in tests and compare path values, not source escaping.
- Codex `local_config.json` stores the portable wiki template unless the user explicitly supplied a root.
- Keep the existing audit that packaged templates do not embed personal/local paths.

### 5. Adapter/core coupling: substantially reduced

Hermes and Codex now converge after producing a typed `SessionBundle`. Shared artifact construction lives in `finalize_artifacts.py`; summary/judge Codex execution lives in `codex_exec.py` and `llm_runtime.py`; wiki placement crosses the `WikiPageIntent` boundary; apply consistency is owned by `wiki_apply_transaction.py`.

Current architecture checks:

- the package import graph has no strongly connected component;
- adapter modules own extraction and trigger details;
- artifact, promotion, wiki policy, transaction, lint, and retrieval remain adapter-neutral;
- the installed Stop-hook file is a thin bootstrap into core `codex_hook.py`.

Remaining maintenance signals are module size rather than domain-cycle defects. `cli.py` and retrieval composition can be split further when a third adapter or additional transport creates concrete pressure.

Future action before multi-agent expansion:

- Move command-specific parsing/printing into `commands/` handlers if `cli.py` starts changing for every adapter.
- Keep trigger orchestration out of shared artifact services.
- Keep adapter-specific code at the edges; keep artifact, retrieval, lint, and promotion logic adapter-neutral.

## Expansion checklist for additional agents

Before adding or advertising support for another agent runtime, verify these items:

- [ ] The adapter can inject explicit project, wiki, home, and state/session roots without relying on platform-specific home expansion.
- [ ] External command execution uses `shell=False` and parses Windows/Unix command paths correctly.
- [ ] Native Windows tests pass or platform-sensitive tests skip for documented capability reasons.
- [ ] Installer/local config tests compare runtime values rather than source string formatting.
- [ ] Generated artifacts remain outside the human-facing wiki by default.
- [ ] LLM/provider configuration remains owned by the host agent or adapter, not hard-coded in the substrate core.
- [ ] Retrieval tools can operate without Hermes- or Codex-specific assumptions except in adapter layers.
- [ ] Release notes clearly distinguish supported integrations from experimental adapter behavior.

## Current decision

Do **not** block the current Hermes/Codex release on historical portability notes that are already covered by tests or documented Windows setup steps. Keep the checklist visible for future agent expansion and broader Windows packaging work.
