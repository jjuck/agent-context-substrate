# Agent Portability Notes

This note records portability findings that matter when Agent Context Substrate grows beyond its current Hermes Agent integration.

## Current scope

The current packaged integration targets **Hermes Agent**. For that scope, the project is intentionally optimized around Hermes session storage, Hermes plugin/context-engine installation, and the existing WSL-first development environment.

The issues below are **not blockers for the current Hermes-only workflow**, but they should be treated as required cleanup before claiming broader support for other agents, native Windows execution, or cross-platform CI.

## Current known baseline

At the time this note was written, the local WSL/Hermes-focused baseline was green:

```text
python -m pytest -q  # 211 passed
ruff check .         # All checks passed
```

This does **not** prove native Windows compatibility. The findings below explain why a Windows-native test run can fail even when the WSL run passes.

## Deferred portability findings

### 1. Home directory resolution depends on platform behavior

`HarnessPaths` currently derives the default home directory from `os.path.expanduser("~")` when `home_dir` is not passed explicitly.

On Unix-like environments this generally follows `HOME`. On native Windows, `expanduser("~")` can prefer `USERPROFILE` or `HOMEDRIVE`/`HOMEPATH` over a test-provided `HOME` value. That can send the default Hermes state lookup to the real user profile instead of the intended test or agent sandbox.

Potential symptoms:

- `extract-session` cannot open the expected `state.db`.
- `build-context-packet` fails before artifact generation.
- integration tests fail with `sqlite3.OperationalError: unable to open database file`.

Future action before cross-agent/native-Windows support:

- Define explicit precedence for `home_dir`, `HERMES_HOME`, `WIKI_PATH`, `HOME`, and Windows profile variables.
- Prefer explicit `home_dir`/`hermes_home` in non-Hermes adapters.
- Add a regression test that simulates Windows `expanduser` behavior.

### 2. Custom-command summarizer parsing is POSIX-oriented

`CustomCommandSummarizerBackend` parses command strings with `shlex.split(...)` and then calls `subprocess.run(argv, shell=False)`.

Using `shell=False` is the right security default, but plain POSIX-style `shlex.split(...)` can mangle unquoted native Windows paths containing backslashes. For example, a command like `python C:\tmp\summarizer.py` can be tokenized incorrectly before `subprocess.run(...)` is called.

Potential symptoms:

- Custom-command mode falls back to heuristic summaries because the command executable or script cannot be found.
- Tests expecting a successful custom-command summary receive fallback metadata instead.

Future action before cross-agent/native-Windows support:

- Use platform-aware parsing or accept an explicit argv/list form in adapter configuration.
- Preserve `shell=False`.
- Add tests for quoted and unquoted Windows-style paths.
- Keep fallback metadata so failed external summarizers remain observable.

### 3. Symlink tests are privilege-sensitive on Windows

Several security tests intentionally create symlinks to verify path-escape hardening. On Windows, symlink creation may require Developer Mode or elevated privileges. If tests directly call `Path.symlink_to(...)` without handling `OSError`, the test can fail even though the production containment logic is correct.

Potential symptoms:

- `WinError 1314` or similar permission failures in symlink tests.
- Native Windows CI fails while WSL/Linux passes.

Future action before cross-platform CI:

- Add a shared test helper for symlink creation.
- Call `pytest.skip(...)` on symlink privilege errors.
- Keep the production checks: resolved paths must remain under the allowed project/wiki root.

### 4. Local config tests should compare values, not string escaping

Installer code writes local Python config such as:

```python
from pathlib import Path

PROJECT_ROOT = Path('...')
WIKI_ROOT = Path('...')
```

For Windows paths, the generated Python source may contain escaped backslashes. The config can still execute correctly, but tests that assert raw `str(path)` appears as a substring can fail because Python source escaping and runtime `Path` values are different representations.

Future action before native-Windows support:

- Load or execute generated `local_config.py` in tests.
- Compare `PROJECT_ROOT` and `WIKI_ROOT` as path values, not raw source substrings.
- Keep the existing audit that packaged templates do not embed personal/local paths.

### 5. CLI and integration logic still contain adapter-host coupling

The current command extraction work is a good direction, but some host-oriented logic remains concentrated in large modules.

Current maintenance signals:

- `cli.py` remains large.
- `retrieval.py` remains large.
- helper logic for index/log registration exists in both CLI and integration layers.

This is acceptable for the Hermes-first implementation, but it increases friction when adding other agent adapters.

Future action before multi-agent expansion:

- Continue moving command-specific logic into `commands/` handlers.
- Move shared artifact registration helpers into a small service module.
- Keep adapter-specific code at the edges; keep artifact, retrieval, lint, and promotion logic adapter-neutral.

## Expansion checklist for non-Hermes agents

Before adding or advertising support for another agent runtime, verify these items:

- [ ] The adapter can inject explicit project, wiki, home, and state/session roots without relying on platform-specific home expansion.
- [ ] External command execution uses `shell=False` and parses Windows/Unix command paths correctly.
- [ ] Native Windows tests pass or platform-sensitive tests skip for documented capability reasons.
- [ ] Installer/local config tests compare runtime values rather than source string formatting.
- [ ] Generated artifacts remain outside the human-facing wiki by default.
- [ ] LLM/provider configuration remains owned by the host agent or adapter, not hard-coded in the substrate core.
- [ ] Retrieval tools can operate without Hermes-specific assumptions except in the Hermes adapter layer.
- [ ] Release notes clearly distinguish Hermes-supported behavior from experimental adapter behavior.

## Current decision

Do **not** block the current Hermes-focused work on these portability fixes. Keep them visible as preconditions for future agent expansion.
