# Windows Codex App Setup

[한국어](./WINDOWS_CODEX_APP_SETUP.ko.md) · [README](../README.md) · [User guide](./USER_GUIDE.en.md) · [Operations](./OPERATIONS.md)

Use this guide to install ACS, review hook trust, and diagnose local setup. ACS reads Codex session sources read-only and writes derived artifacts under its configured project root. Daily search, manual finalize, and optional wiki updates are in the [User guide](./USER_GUIDE.en.md); artifact behavior is in [Pipeline](./PIPELINE.md).

## 1. Choose paths and scope

| Item | Default / example |
| --- | --- |
| Codex home | `%USERPROFILE%\.codex` |
| Codex metadata | `<CODEX_HOME>\state_5.sqlite` |
| Codex rollouts | `<CODEX_HOME>\sessions\...\rollout-*.jsonl` |
| ACS project root | Cloned `agent-context-substrate` checkout |
| ACS artifacts | `<PROJECT_ROOT>\data\...` |
| LLM Wiki | `%USERPROFILE%\Documents\LLM Wiki` |
| Installed plugin | `<CODEX_HOME>\plugins\agent-context-substrate` |
| User hook (explicit opt-in) | `<CODEX_HOME>\hooks.json` |

`project_root` is the ACS artifact scope and the Stop hook's `cwd` filter. The default checkout root does **not** automatically capture work in unrelated repositories. A Stop payload whose `cwd` is outside the configured root is skipped. Select the intended scope deliberately; manual finalize and watcher processing have different selection behavior.

Keep the ACS checkout and its `.venv` available: this is an editable install, and the installed hook references the configured Python/project paths. Moving or deleting them requires updating the configuration/install.

## 2. Check prerequisites

Use Python 3.11+, Git, PowerShell, and a Codex runtime with local session files. Obsidian is optional. The bootstrap checks command availability; finding `py` or `python` alone does not establish the selected interpreter version or a working Codex GUI hook.

| Tool | Bootstrap opt-in |
| --- | --- |
| Python | `-InstallMissingTools`, winget `Python.Python.3.13` |
| Git | `-InstallMissingTools`, winget `Git.Git` |
| Obsidian | `-InstallObsidian`, winget `Obsidian.Obsidian` |
| Codex app/CLI | Install separately; bootstrap does not install it |

After installing tools, a new terminal may be needed to refresh PATH. The script prefers `py -3` when creating `.venv`; check the resulting interpreter if multiple Python versions are present.

## 3. Install from PowerShell

Use the repository's [setup script](../scripts/setup-codex-windows.ps1):

```powershell
git clone https://github.com/jjuck/agent-context-substrate.git agent-context-substrate
cd agent-context-substrate
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -CheckOnly
```

`-CheckOnly` exits before ACS setup. Run it **without** install switches for prerequisite inspection only: tool handling occurs before that exit, so combining it with install switches can install missing system tools.

Install ACS with the displayed default paths:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
```

For another wiki or Codex home, supply `-WikiRoot` and `-CodexHome`; `-ProjectRoot` selects the ACS checkout used for editable installation and artifacts; it must contain the ACS package, so this bootstrap option cannot simply point to an unrelated repository to capture its sessions. To opt into installing missing tools:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -InstallMissingTools -InstallObsidian
```

The script creates `.venv`, upgrades pip, installs ACS with `pip install -e .`, and runs `setup-codex --yes` with explicit paths. Setup initializes the wiki, installs plugin/config with its bundled hook, registers a personal marketplace/cache entry, and runs local diagnostics. `--yes` accepts setup choices; it does not grant hook trust.

In 0.2.2, installation selects one Stop trigger. `setup-codex`, the wizard, and diagnostic repair default to the bundled plugin hook, avoiding a global ACS user-hook entry. Both `setup-codex` and direct `install-codex-plugin` accept `--install-user-hook` to explicitly select the user hook and disable the bundled hook in installed copies. `setup-codex --no-user-hook` remains a compatibility option for the bundled default and cannot be combined with `--install-user-hook`. Switching back removes only ACS handlers from user hooks. Other handlers are preserved. Doctor does not warn about an absent user hook when the bundled hook is installed. The watcher remains a separately started fallback.

The Windows bundled command reads `PLUGIN_ROOT` inside Python instead of using shell-specific `%PLUGIN_ROOT%` expansion. Marketplace caches use the manifest version; older cached versions remain available to running hosts. After reinstalling, refresh/reinstall the personal plugin in Codex and inspect the loaded version and hooks before removing any old cache.

For direct reinstallation of an existing personal-marketplace setup, always repeat `--personal-marketplace-root '<MARKETPLACE_ROOT>'`. The installer rejects an omitted root before changing files, so a mode switch cannot disable the user hook while leaving the registered plugin copy stale. `setup-codex` supplies its selected marketplace root automatically.

For interactive path review after the CLI is available:

```powershell
.\.venv\Scripts\agent-context-substrate.exe setup-codex-wizard
```

To preview ACS setup actions without writing setup files:

```powershell
.\.venv\Scripts\agent-context-substrate.exe setup-codex --dry-run
```

## 4. Inspect installation separately from runtime

Run from the ACS checkout:

```powershell
$AcsCli = '.\.venv\Scripts\agent-context-substrate.exe'
$AcsRoot = (Resolve-Path -LiteralPath '.').Path
$AcsWiki = "$env:USERPROFILE\Documents\LLM Wiki"
$AcsCodex = "$env:USERPROFILE\.codex"
& $AcsCli config-codex paths --codex-home $AcsCodex --project-root $AcsRoot --wiki-root $AcsWiki
& $AcsCli config-codex show --codex-home $AcsCodex
& $AcsCli doctor-codex --codex-home $AcsCodex --project-root $AcsRoot --wiki-root $AcsWiki --fail-on-issues
& $AcsCli diagnose-codex --codex-home $AcsCodex --project-root $AcsRoot --wiki-root $AcsWiki
```

Change these variables if you chose custom paths. `config-codex paths` displays paths calculated from arguments/defaults; `config-codex show` reads the installed `local_config.json`. Compare both rather than assuming displayed paths came from installed configuration.

`doctor-codex` checks local files, configuration consistency, interpreter version, and data-directory writability. Required failures produce a nonzero exit with `--fail-on-issues`; warnings can coexist with `ok=True`. Its `hook_support` result reflects an ACS capability assumption, and `hook_primary_installed` checks hook files. Neither proves that Codex loaded, enabled, trusted, or executed the hook. Source metadata availability and runtime behavior need separate inspection.

## 5. Enable and trust the hook

ACS ships the default `hooks/hooks.json` under the plugin directory. Official [plugin packaging documentation](https://developers.openai.com/plugins/build/plugins) describes default hook discovery. Discovery and plugin installation/enabling do not grant trust to non-managed command hooks.

Confirm the ACS plugin is enabled in your Codex runtime. For hook review, open Codex CLI and enter `/hooks` as described in the official [hooks documentation](https://developers.openai.com/docs/hooks):

```powershell
codex
```

```text
/hooks
```

Review the command/path associated with `agent-context-substrate`, `codex_stop_finalize.py`, and `Finalizing Codex thread into Agent Context Substrate`, then grant trust through the available review surface. Use your runtime's controls; this guide does not assert a tested GUI state or particular button label.

Full Access, sandbox settings, and approval mode are separate from hook trust. Review may be required again when hook definitions or commands change, including after reinstall/repair. ACS setup does not bypass this step. If the runtime lacks a hook review surface or misses Stop events, use manual finalize or the watcher.

To verify actual execution, observe a Stop event for a thread inside the configured scope and inspect its packet/recovery/ledger artifacts. Installed files or a healthy doctor report alone are insufficient evidence. In `data/index/codex_hook_events.jsonl`, `finalized` means processing finished, while `skipped` means no processing occurred. Events include the plugin root, script path and launcher Python to distinguish installations. An outside-scope skip can appear as a successful hook run in Codex.

## 6. Manual finalize and watcher fallback

Inspect available threads, then finalize a chosen ID:

```powershell
& $AcsCli codex-status --codex-home $AcsCodex
& $AcsCli codex-finalize --thread-id '<THREAD_ID>' `
  --codex-home $AcsCodex --project-root $AcsRoot --wiki-root $AcsWiki
```

Manual processing does not require hook trust. For a one-pass watcher run:

```powershell
& $AcsCli codex-watch --once --idle-seconds 300 `
  --codex-home $AcsCodex --project-root $AcsRoot --wiki-root $AcsWiki
```

`--once` writes artifacts for eligible idle threads; it is not a dry-run. The watcher scans the selected Codex home without the hook's project `cwd` filter, so older sessions from other projects may be exported into `$AcsRoot`. Raising `--idle-seconds` delays recently modified sessions but still permits older ones. `processed=0` means no eligible unprocessed threads were processed; it does not prove hook execution. Omit `--once` to keep polling; stop with Ctrl+C.

## 7. Diagnose, repair, and open the wiki

| Symptom | Check / action |
| --- | --- |
| CLI executable missing | Inspect `.venv` Python and pip output; confirm Python 3.11+ |
| Required doctor check fails | Read the named check and confirm explicit project/wiki/Codex paths |
| Doctor is healthy but no automatic packet | Check plugin enablement, hook trust, Stop event delivery, and `cwd` scope |
| Codex source files missing | Confirm the Codex home used by your runtime contains local sessions |
| Hook stops after a move/update | Compare installed config, Python path, hook definitions, and trust |
| Obsidian has no vault | Open the chosen wiki folder as a vault manually |

For required setup failures, request local ACS repair with explicit paths:

```powershell
& $AcsCli diagnose-codex --fix --codex-home $AcsCodex `
  --project-root $AcsRoot --wiki-root $AcsWiki
```

When required checks fail, repair reruns setup for the wiki skeleton, plugin/config, bundled hook, and marketplace assets. This also switches an existing ACS user-hook installation to the bundled default while preserving other handlers. It does not fix every warning, install all missing tools, or grant trust. Review hook changes afterward.

Open `<WIKI_ROOT>` in Obsidian with `Open folder as vault` if desired. Default `packet-only` stores session outputs in ACS `data/`, while reviewed wiki patches are optional. Treat source sessions, derived artifacts, local config, and provenance as private; inspect them before sharing.
