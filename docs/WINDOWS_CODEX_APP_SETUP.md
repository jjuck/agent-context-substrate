# Windows Codex App Setup

[한국어](./WINDOWS_CODEX_APP_SETUP.ko.md) · [README](../README.md) · [User Guide](./USER_GUIDE.en.md)

This guide is for Windows Codex app users who want Agent Context Substrate (ACS) installed from the GitHub repo. The target flow is simple: give a fresh Codex thread the repo URL and ask it to install ACS.

ACS reads Codex session files **read-only**, writes audit artifacts under the cloned project `data\...` directory, and lets the installed Stop hook grow the LLM Wiki through judge-approved `apply-flexible` patches.

## 1. Paths users should know

| Item | Windows default example | Meaning |
| --- | --- | --- |
| Codex home | `%USERPROFILE%\.codex` | Local Codex settings and sessions |
| Codex SQLite | `%USERPROFILE%\.codex\state_5.sqlite` | Thread metadata, read-only for ACS |
| Codex rollout JSONL | `%USERPROFILE%\.codex\sessions\...\rollout-*.jsonl` | Thread event stream, read-only for ACS |
| ACS project root | cloned `agent-context-substrate` folder | Code plus generated `data\...` artifacts |
| ACS artifacts | `<PROJECT_ROOT>\data\...` | Raw exports, packets, recovery, ledger, retrieval index, wiki proposals, judge decisions |
| LLM Wiki root | `%USERPROFILE%\Documents\LLM Wiki` default template | Human-facing Obsidian wiki updated by judge-approved patches; setup stores the template unless `--wiki-root` is explicit |
| Codex plugin | `%USERPROFILE%\.codex\plugins\agent-context-substrate` | Installed ACS Codex plugin asset |
| Codex user hook | `%USERPROFILE%\.codex\hooks.json` | Optional Stop hook fallback; not installed by default |

## 2. Prerequisites and automatic install scope

Required tools are the Windows Codex app, Python 3.11+, Git, and PowerShell. Obsidian is optional for ACS execution, but recommended if the user wants to read and curate the LLM Wiki.

`scripts/setup-codex-windows.ps1` does not install system tools by default. If the user opts in, it can use these winget package IDs:

| Tool | winget ID | Automatic install |
| --- | --- | --- |
| Python | `Python.Python.3.13` | With `-InstallMissingTools` |
| Git | `Git.Git` | With `-InstallMissingTools` |
| Obsidian | `Obsidian.Obsidian` | With `-InstallObsidian` |
| Codex app/CLI | Separate install | Not installed automatically |
| Hook trust | Review/trust in `/hooks` | Never bypassed automatically |

On some Windows machines, plain `codex` on PATH resolves to an npm shim such as
`%APPDATA%\npm\codex.ps1` or `codex.cmd` instead of the Windows Codex app CLI.
The setup script and `doctor-codex` report all PATH `codex` candidates plus
known direct candidates under `%LOCALAPPDATA%\Programs\OpenAI\Codex\bin` and
`%LOCALAPPDATA%\OpenAI\Codex\bin`. When a direct `codex.exe` is found,
`setup-codex` pins it into `local_config.json` as `codex_cli_command` so
`summary_mode=auto` does not depend on global PATH ordering.

## 3. Single PowerShell install

Clone the repo and run one bootstrap script:

```powershell
git clone https://github.com/jjuck/agent-context-substrate.git agent-context-substrate
cd agent-context-substrate
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
```

To let the script install missing tools:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -InstallMissingTools -InstallObsidian
```

To check prerequisites without installing:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -CheckOnly
```

The script creates `.venv`, runs `pip install -e .`, then runs:

```powershell
.\.venv\Scripts\agent-context-substrate.exe setup-codex --yes
```

Default Windows setup installs the plugin-bundled Stop hook only. It does not
also register `%USERPROFILE%\.codex\hooks.json`, because Codex loads matching
hooks from multiple sources and would run duplicate Stop hooks. If plugin hooks
are unavailable in a specific runtime, opt in explicitly:

```powershell
.\.venv\Scripts\agent-context-substrate.exe setup-codex --yes --user-hook-fallback
```

## 4. Verify and inspect setup

Health check:

```powershell
.\.venv\Scripts\agent-context-substrate.exe doctor-codex --fail-on-issues
```

User-facing paths:

```powershell
.\.venv\Scripts\agent-context-substrate.exe config-codex paths
```

Installed `local_config.json`:

```powershell
.\.venv\Scripts\agent-context-substrate.exe config-codex show
```

Codex LLM summaries and judge-gated wiki writes are on by default in new installs.
`setup-codex --yes` writes these values into the installed plugin
`local_config.json`:

```json
{
  "summary_mode": "auto",
  "wiki_auto_mode": "apply-flexible",
  "wiki_write_judge_mode": "auto",
  "wiki_auto_min_score": 0.85
}
```

With that config, the Stop hook tries `codex exec` first and falls back to
heuristic summaries on CLI, timeout, JSON, or lint failure. For wiki writes, it
plans a flexible patch and asks the write judge whether the LLM Wiki should be
updated. If the judge path is unavailable or below the minimum score, ACS leaves
a review-required proposal and decision artifact instead of writing the vault.

The `auto` path runs `codex exec` with read-only sandboxing, `approval_policy=never`,
`service_tier=fast`, low reasoning effort, hooks disabled, and inline bounded JSON
input before validating the returned strict JSON.

```powershell
.\.venv\Scripts\agent-context-substrate.exe config-codex set --key summary_mode --value auto
.\.venv\Scripts\agent-context-substrate.exe config-codex set --key wiki_auto_mode --value apply-flexible
.\.venv\Scripts\agent-context-substrate.exe config-codex set --key wiki_write_judge_mode --value auto
```

Use those commands only when updating an older install or changing policy.

Then verify the selected Codex summary command. The smoke is opt-in because it
calls the signed-in Codex runtime:

```powershell
.\.venv\Scripts\agent-context-substrate.exe doctor-codex --summary-smoke
```

If `doctor-codex` reports `service_tier="default"` in `%USERPROFILE%\.codex\config.toml`,
remove that line or set a supported value such as `fast` or `flex`. Omitting
`service_tier` is the standard/default speed behavior.

Diagnostics:

```powershell
.\.venv\Scripts\agent-context-substrate.exe diagnose-codex
```

Safe local repair:

```powershell
.\.venv\Scripts\agent-context-substrate.exe diagnose-codex --fix
```

Interactive path review:

```powershell
.\.venv\Scripts\agent-context-substrate.exe setup-codex-wizard
```

`setup-codex-wizard` shows the Codex SQLite, rollout JSONL, LLM Wiki, and ACS artifact paths before installing.

## 5. Trust the hook once

The installer places the hook files, but Codex requires a user review before non-managed command hooks run. This is separate from Full Access or approval-mode settings.

First restart the Codex app after installation. In the GUI, open the bottom-left
settings area, open hook settings, find the `agent-context-substrate` plugin Stop
hook or user configuration Stop hook, then approve/trust and enable it.

CLI review is also supported. Open Codex CLI:

```powershell
codex
```

If `codex` is an npm shim, use the direct CLI path reported by the setup script
or `doctor-codex` instead.

Then enter:

```text
/hooks
```

Trust or allow the hook that mentions:

```text
agent-context-substrate
codex_stop_finalize.py
Finalizing Codex thread into Agent Context Substrate
```

If Codex shows a startup modal like:

```text
Hooks need review
1 hook is new or changed
1. Review hooks
2. Trust all and continue
3. Continue without trusting
```

review the hook command first. After confirming it points to the installed
`agent-context-substrate` Stop hook, choose `Trust all and continue` or the
equivalent trust action for that reviewed hook. An installing agent should ask
the user before doing this: "May I review and trust the Codex CLI
agent-context-substrate Stop hook now?"

Codex may require review again if the hook file or command changes. The installer does not auto-approve this trust step.

## 6. Obsidian

ACS can create the effective wiki folder resolved from the `%USERPROFILE%\Documents\LLM Wiki` default template, but it does not automatically open or register the vault in Obsidian.

If Obsidian is installed, open Obsidian, choose `Open folder as vault`, and select the effective path from `config-codex paths`:

```text
%USERPROFILE%\Documents\LLM Wiki
```

The default automatic mode is `apply-flexible` with `wiki_write_judge_mode=auto`. Codex thread finalization writes context packets, recovery, ledger, retrieval artifacts, wiki proposals, and judge decisions under `<PROJECT_ROOT>\data\...`; it updates the LLM Wiki only when the write judge approves and the patch safety checks pass.

## 7. Real Stop hook smoke test

After hook trust, run a short interactive Codex thread and end the turn. A
successful hook run shows:

```text
Running Stop hook: Finalizing Codex thread into Agent Context Substrate
```

Then inspect the new ACS artifacts:

```powershell
Get-Content .\data\index\codex_hook_events.jsonl -Tail 5
Get-ChildItem .\data\exports\raw\codex -File | Sort-Object LastWriteTime -Descending | Select-Object -First 3
Get-ChildItem .\data\context_packets -File | Sort-Object LastWriteTime -Descending | Select-Object -First 3
Get-ChildItem .\data\recovery -File | Sort-Object LastWriteTime -Descending | Select-Object -First 3
Get-ChildItem .\data\exports\summaries -File | Sort-Object LastWriteTime -Descending | Select-Object -First 3
.\.venv\Scripts\agent-context-substrate.exe search-knowledge --query "<unique smoke text>" --mode recovery
```

The hook event should include `status=finalized`, and `search-knowledge` should
return the recovery packet for the smoke thread. The summary JSON metadata
should show either `mode=codex-cli` or a heuristic `fallback_from` /
`fallback_reason`. The wiki decision artifact should show whether the judge
approved an `apply_flexible` write or left the proposal for review.

## 8. Fallback verification

If the hook has not been trusted yet, or if a Stop event is missed, `codex-watch` remains available as fallback.

```powershell
.\.venv\Scripts\agent-context-substrate.exe codex-watch `
  --once `
  --codex-home "$env:USERPROFILE\.codex" `
  --project-root (Resolve-Path -LiteralPath ".").Path `
  --wiki-root "$env:USERPROFILE\Documents\LLM Wiki" `
  --summary-mode auto `
  --wiki-auto-mode apply-flexible `
  --wiki-write-judge-mode auto `
  --idle-seconds 999999
```

`processed=0` is fine. The command uses a large idle window to avoid unexpectedly processing old threads.

## 9. Prompt for a fresh Codex install

Paste this into a fresh Codex thread if you want Codex to install ACS from the GitHub repo.

```text
Install Agent Context Substrate for the Windows Codex app.

Repo: https://github.com/jjuck/agent-context-substrate

Requirements:
- Use Windows PowerShell commands.
- Tell me that Codex source data lives under %USERPROFILE%\.codex: state_5.sqlite plus sessions\...\rollout-*.jsonl.
- Treat %USERPROFILE%\Documents\LLM Wiki as the portable default LLM Wiki template, explain the effective path, and confirm before installing.
- Tell me that ACS artifacts are written under the cloned agent-context-substrate project data\... directory.
- Use scripts/setup-codex-windows.ps1 as the default install path.
- Explain that new installs default to summary_mode=auto, wiki_auto_mode=apply-flexible, wiki_write_judge_mode=auto, and wiki_auto_min_score=0.85.
- Explain that LLM Wiki content is added when the write judge approves evidence-backed flexible patches, not only when the user explicitly asks for each wiki write.
- If plain codex resolves to an npm shim, prefer the direct codex.exe path reported by setup-codex or doctor-codex for /hooks review.
- If tools are missing, mention Python.Python.3.13, Git.Git, and Obsidian.Obsidian winget package IDs, then ask before installing them.
- After install, explain doctor-codex, config-codex paths, and diagnose-codex.
- Do not bypass non-managed hook trust. Ask me before reviewing/trusting the hook, then use /hooks or the Hooks need review modal to review the agent-context-substrate Stop hook.
- Do not install ~/.codex/hooks.json by default. Mention --user-hook-fallback only if plugin hooks are unavailable.
- For final validation, run a real interactive Stop hook smoke test and confirm Running Stop hook: Finalizing Codex thread into Agent Context Substrate, codex_hook_events.jsonl status=finalized, generated data\... artifacts, summary metadata, wiki decision artifact, and a search-knowledge recovery hit.
```

## 10. Common confusion

- Full Access, approval mode, and sandbox settings are not the same as hook trust.
- ACS does not modify Codex SQLite or rollout JSONL files.
- New Codex installs default to judge-gated `apply-flexible`; failed or low-confidence judge runs leave review-required artifacts instead of writing the LLM Wiki.
- `doctor-codex` checks setup health; `diagnose-codex --fix` repairs only safe ACS local files.
- `--user-hook-fallback` is optional and should not be used together with a working plugin hook unless you are intentionally testing duplicate-hook behavior.
- Obsidian is optional. ACS creates the LLM Wiki folder, but the user must open it as a vault in Obsidian.
