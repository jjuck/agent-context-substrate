# Windows Codex 앱 설치 가이드

[English](./WINDOWS_CODEX_APP_SETUP.md) · [한국어 README](../README.ko.md) · [사용자 가이드](./USER_GUIDE.md)

이 문서는 Windows Codex 앱 사용자가 Agent Context Substrate(ACS)를 GitHub repo에서 바로 설치할 때 필요한 절차를 설명합니다. 목표는 “Codex에게 repo URL을 주고 설치해 달라고 요청하면 스스로 진행할 수 있는” 흐름입니다.

ACS는 Codex 원본 세션을 **읽기 전용**으로 읽고, 감사 가능한 artifact를 ACS 프로젝트의 `data\...` 아래에 씁니다. 설치된 Stop hook은 write judge가 승인한 `apply-flexible` patch로 LLM Wiki를 키웁니다.

## 1. 먼저 인지해야 할 경로

| 항목 | Windows 기본 예시 | 설명 |
| --- | --- | --- |
| Codex home | `%USERPROFILE%\.codex` | Codex 앱의 로컬 설정과 세션 저장소 |
| Codex SQLite | `%USERPROFILE%\.codex\state_5.sqlite` | thread metadata. ACS가 읽기 전용으로 조회 |
| Codex rollout JSONL | `%USERPROFILE%\.codex\sessions\...\rollout-*.jsonl` | 실제 thread event. ACS가 읽기 전용으로 조회 |
| ACS project root | clone한 `agent-context-substrate` 폴더 | ACS 코드와 `data\...` artifact 저장 위치 |
| ACS artifacts | `<PROJECT_ROOT>\data\...` | raw export, packet, recovery, ledger, retrieval index, wiki proposal, judge decision |
| LLM Wiki root | `%USERPROFILE%\Documents\LLM Wiki` default template | judge-approved patch가 반영되는 Obsidian LLM Wiki. `--wiki-root`를 명시하지 않으면 사용자별 절대 경로 대신 이 portable template을 저장합니다. |
| Codex plugin | `%USERPROFILE%\.codex\plugins\agent-context-substrate` | ACS Codex plugin asset |
| Codex user hook | `%USERPROFILE%\.codex\hooks.json` | 선택 Stop hook fallback. 기본 설치에서는 만들지 않음 |

## 2. 준비물과 자동 설치 범위

필수 준비물은 Windows Codex 앱, Python 3.11+, Git, PowerShell입니다. Obsidian은 ACS 실행 자체에는 필수가 아니지만, LLM Wiki를 사람이 읽고 정리하려면 설치하는 것이 좋습니다.

`scripts/setup-codex-windows.ps1`는 기본적으로 시스템 도구를 마음대로 설치하지 않습니다. 누락 도구 설치를 허용하려면 아래 winget ID를 사용합니다.

| 도구 | winget ID | 자동 설치 |
| --- | --- | --- |
| Python | `Python.Python.3.13` | `-InstallMissingTools`를 줄 때 |
| Git | `Git.Git` | `-InstallMissingTools`를 줄 때 |
| Obsidian | `Obsidian.Obsidian` | `-InstallObsidian`을 줄 때 |
| Codex 앱/CLI | 별도 설치 | 자동 설치하지 않음 |
| Hook trust | `/hooks`에서 직접 review/trust | 자동 우회하지 않음 |

일부 Windows 환경에서는 plain `codex`가 Windows Codex 앱 CLI가 아니라 `%APPDATA%\npm\codex.ps1` 또는 `codex.cmd` 같은 npm shim을 먼저 잡을 수 있습니다. setup script와 `doctor-codex`는 PATH의 모든 `codex` 후보와 `%LOCALAPPDATA%\Programs\OpenAI\Codex\bin`, `%LOCALAPPDATA%\OpenAI\Codex\bin` 아래 direct 후보를 함께 보여줍니다. direct `codex.exe`가 발견되면 `setup-codex`는 이를 `local_config.json`의 `codex_cli_command`로 저장해서 `summary_mode=auto`가 전역 PATH 순서에 덜 흔들리게 합니다.

## 3. 단일 PowerShell 설치

PowerShell에서 repo를 clone한 뒤 bootstrap script 하나를 실행합니다.

```powershell
git clone https://github.com/jjuck/agent-context-substrate.git agent-context-substrate
cd agent-context-substrate
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
```

도구 누락까지 처리하려면:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -InstallMissingTools -InstallObsidian
```

점검만 하고 설치하지 않으려면:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -CheckOnly
```

이 script는 `.venv`를 만들고 `pip install -e .`로 ACS를 설치한 뒤 아래 명령을 실행합니다.

```powershell
.\.venv\Scripts\agent-context-substrate.exe setup-codex --yes
```

기본 Windows setup은 plugin에 포함된 Stop hook 하나만 설치합니다. Codex는 여러 hook source의 matching hook을 모두 실행하므로, 기본 설치에서 `%USERPROFILE%\.codex\hooks.json` fallback까지 같이 만들면 Stop hook이 중복 실행될 수 있습니다. plugin hook을 쓸 수 없는 런타임에서만 명시적으로 fallback을 켭니다.

```powershell
.\.venv\Scripts\agent-context-substrate.exe setup-codex --yes --user-hook-fallback
```

## 4. 설치 후 확인 명령

상태 점검:

```powershell
.\.venv\Scripts\agent-context-substrate.exe doctor-codex --fail-on-issues
```

사용자-facing 경로 확인:

```powershell
.\.venv\Scripts\agent-context-substrate.exe config-codex paths
```

설치된 `local_config.json` 확인:

```powershell
.\.venv\Scripts\agent-context-substrate.exe config-codex show
```

Codex LLM summary와 judge-gated wiki write는 새 설치에서 기본으로 켜집니다. `setup-codex --yes`는 설치된 plugin `local_config.json`에 아래 값을 씁니다.

```json
{
  "summary_mode": "auto",
  "wiki_auto_mode": "apply-flexible",
  "wiki_write_judge_mode": "auto",
  "wiki_auto_min_score": 0.85
}
```

이 설정에서 Stop hook은 먼저 `codex exec`를 시도하고 CLI/timeout/JSON/lint 실패 시 heuristic summary로 fallback합니다. wiki write는 flexible patch를 계획한 뒤 write judge에게 LLM Wiki 반영 여부를 맡깁니다. judge 경로를 사용할 수 없거나 점수가 낮으면 Obsidian을 쓰지 않고 review-required proposal과 decision artifact를 남깁니다.

`auto` 경로는 `codex exec`를 read-only sandbox, `approval_policy=never`, `service_tier=fast`, low reasoning effort, hooks-disabled, inline bounded JSON input으로 실행한 뒤 반환된 strict JSON을 검증합니다.

```powershell
.\.venv\Scripts\agent-context-substrate.exe config-codex set --key summary_mode --value auto
.\.venv\Scripts\agent-context-substrate.exe config-codex set --key wiki_auto_mode --value apply-flexible
.\.venv\Scripts\agent-context-substrate.exe config-codex set --key wiki_write_judge_mode --value auto
```

이 명령들은 오래된 설치를 갱신하거나 정책을 바꿀 때만 직접 실행하면 됩니다.

선택된 Codex summary command가 실제 로그인된 Codex runtime을 호출할 수 있는지 확인하려면 아래 smoke를 명시적으로 실행합니다. 이 명령은 실제 `codex exec`를 호출하므로 기본 doctor에서는 자동 실행하지 않습니다.

```powershell
.\.venv\Scripts\agent-context-substrate.exe doctor-codex --summary-smoke
```

`doctor-codex`가 `%USERPROFILE%\.codex\config.toml`의 `service_tier="default"`를 경고하면 해당 줄을 제거하거나 `fast`/`flex`처럼 지원되는 값으로 바꾸세요. 표준/default 속도는 `service_tier`를 생략하는 방식입니다.

문제 진단:

```powershell
.\.venv\Scripts\agent-context-substrate.exe diagnose-codex
```

안전한 로컬 파일만 재설치/복구:

```powershell
.\.venv\Scripts\agent-context-substrate.exe diagnose-codex --fix
```

대화형 wizard:

```powershell
.\.venv\Scripts\agent-context-substrate.exe setup-codex-wizard
```

`setup-codex-wizard`는 Codex SQLite, rollout JSONL, LLM Wiki, ACS artifact 경로를 보여주고 확인을 받은 뒤 설치합니다.

## 5. Hook 승인

설치 명령은 hook 파일을 배치하지만, Codex 보안 정책상 non-managed command hook은 사용자가 한 번 review/trust 해야 실행됩니다. 이 단계는 `기본 권한`, `자동검토`, `전체권한` 같은 approval/sandbox 설정과 다릅니다.

설치 후 먼저 Codex 앱을 재시작하세요. GUI에서는 왼쪽 아래 설정 영역을 열고 hook 설정으로 들어간 뒤 `agent-context-substrate` plugin Stop hook 또는 user configuration Stop hook을 찾아 approve/trust 및 enable합니다.

PowerShell에서 Codex CLI를 열고:

```powershell
codex
```

`codex`가 npm shim이면 setup script나 `doctor-codex`가 표시한 direct app CLI 경로를 대신 사용하세요.

Codex CLI 입력창에서:

```text
/hooks
```

다음 hook을 찾아 Trust, Allow, Enable 계열의 선택지를 고릅니다.

```text
agent-context-substrate
codex_stop_finalize.py
Finalizing Codex thread into Agent Context Substrate
```

시작 시 다음과 같은 modal이 뜰 수도 있습니다.

```text
Hooks need review
1 hook is new or changed
1. Review hooks
2. Trust all and continue
3. Continue without trusting
```

먼저 hook command가 설치된 `agent-context-substrate` Stop hook을 가리키는지 review한 뒤 `Trust all and continue` 또는 해당 hook trust 동작을 선택하세요. 설치를 맡은 agent는 이 단계 전에 사용자에게 “Codex CLI의 agent-context-substrate Stop hook을 review/trust로 허용해도 될까요?”라고 물어야 합니다.

Hook 파일이나 명령이 바뀌면 Codex가 다시 review 대상으로 표시할 수 있습니다. installer는 이 trust를 자동 승인하지 않습니다.

## 6. Obsidian 안내

ACS는 `%USERPROFILE%\Documents\LLM Wiki` default template에서 런타임에 해석된 effective wiki 폴더 구조를 만들 수 있지만, Obsidian 앱을 자동으로 열어 vault로 등록하지는 않습니다.

Obsidian을 설치했다면 Obsidian에서 `Open folder as vault`를 선택하고 아래 폴더를 엽니다.

```text
%USERPROFILE%\Documents\LLM Wiki
```

기본 자동 처리는 `apply-flexible` + `wiki_write_judge_mode=auto`입니다. Codex thread 종료 때 `<PROJECT_ROOT>\data\...` 아래에 context packet, recovery, ledger, retrieval artifact, wiki proposal, judge decision을 남기고, write judge가 승인하고 patch safety check를 통과할 때만 LLM Wiki Markdown을 갱신합니다.

## 7. 실제 Stop hook smoke test

Hook trust 후 짧은 Codex thread를 하나 실행하고 turn을 종료합니다. 성공하면 다음 문구가 보입니다.

```text
Running Stop hook: Finalizing Codex thread into Agent Context Substrate
```

그 다음 아래를 확인합니다.

```powershell
Get-Content .\data\index\codex_hook_events.jsonl -Tail 5
Get-ChildItem .\data\exports\raw\codex -File | Sort-Object LastWriteTime -Descending | Select-Object -First 3
Get-ChildItem .\data\context_packets -File | Sort-Object LastWriteTime -Descending | Select-Object -First 3
Get-ChildItem .\data\recovery -File | Sort-Object LastWriteTime -Descending | Select-Object -First 3
Get-ChildItem .\data\exports\summaries -File | Sort-Object LastWriteTime -Descending | Select-Object -First 3
.\.venv\Scripts\agent-context-substrate.exe search-knowledge --query "<unique smoke text>" --mode recovery
```

hook event에는 `status=finalized`가 있어야 하고, `search-knowledge`는 방금 생성된 recovery packet을 찾아야 합니다. summary JSON metadata에는 `mode=codex-cli` 또는 heuristic `fallback_from` / `fallback_reason`이 남아야 합니다. wiki decision artifact에는 judge가 `apply_flexible`을 승인했는지, 아니면 review-required로 남겼는지가 기록됩니다.

## 8. Fallback 확인

Hook이 아직 trust되지 않았거나 Stop event를 놓친 경우 `codex-watch`를 fallback으로 실행할 수 있습니다.

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

`processed=0`이어도 정상입니다. 위 명령은 오래된 thread를 갑자기 처리하지 않도록 큰 idle window를 사용합니다.

## 9. 순정 Codex에게 맡기는 프롬프트

새 Codex thread에 아래 프롬프트와 GitHub repo URL을 주면, Codex가 README와 이 문서를 보고 설치를 진행할 수 있어야 합니다.

```text
Windows Codex 앱에서 Agent Context Substrate를 설치해줘.

Repo: https://github.com/jjuck/agent-context-substrate

요구사항:
- Windows PowerShell 기준으로 설치해.
- Codex 원본 저장소는 %USERPROFILE%\.codex 아래의 state_5.sqlite와 sessions\...\rollout-*.jsonl임을 사용자에게 알려줘.
- LLM Wiki 기본값은 %USERPROFILE%\Documents\LLM Wiki portable template으로 설명하고, 런타임 effective path를 설치 전에 사용자에게 확인해.
- ACS artifact는 clone한 agent-context-substrate 프로젝트의 data\... 아래에 저장된다고 알려줘.
- scripts/setup-codex-windows.ps1를 기본 설치 경로로 사용해.
- 새 설치 기본값은 summary_mode=auto, wiki_auto_mode=apply-flexible, wiki_write_judge_mode=auto, wiki_auto_min_score=0.85라고 설명해.
- LLM Wiki 내용은 사용자가 매번 wiki write를 요청할 때만 쌓이는 것이 아니라, write judge가 evidence-backed flexible patch를 승인할 때 반영된다고 설명해.
- plain codex가 npm shim이면 /hooks review에는 setup-codex 또는 doctor-codex가 표시한 direct codex.exe 경로를 우선 사용해.
- 누락 도구가 있으면 Python.Python.3.13, Git.Git, Obsidian.Obsidian winget ID를 알려주고, 설치 전 사용자에게 확인해.
- 설치 후 doctor-codex, config-codex paths, diagnose-codex 명령을 안내해.
- non-managed hook trust는 자동 우회하지 말고, 사용자에게 승인 질문을 한 뒤 /hooks 또는 Hooks need review modal에서 agent-context-substrate Stop hook을 review/trust 해.
- 기본 설치에서는 ~/.codex/hooks.json fallback을 만들지 마. plugin hook을 쓸 수 없을 때만 --user-hook-fallback을 설명해.
- 마지막에는 실제 interactive Stop hook smoke test로 Running Stop hook: Finalizing Codex thread into Agent Context Substrate, codex_hook_events.jsonl status=finalized, data\... artifact 생성, summary metadata, wiki decision artifact, search-knowledge recovery hit까지 확인해.
```

## 10. 자주 헷갈리는 점

- `기본 권한`, `자동검토`, `전체권한`은 Codex agent의 작업 승인/샌드박스 설정입니다. Hook trust와는 별개입니다.
- ACS는 Codex SQLite와 rollout JSONL을 수정하지 않습니다.
- 새 Codex 설치의 기본값은 judge-gated `apply-flexible`입니다. judge 실패나 낮은 confidence는 LLM Wiki를 쓰지 않고 review-required artifact로 남깁니다.
- `doctor-codex`는 설치 상태를 점검하고, `diagnose-codex --fix`는 안전한 ACS 로컬 파일만 복구합니다.
- `--user-hook-fallback`은 선택 경로입니다. plugin hook이 정상 동작하는 환경에서는 같이 켜지 않는 것이 중복 Stop hook을 피하는 기본값입니다.
- Obsidian은 선택 의존성입니다. ACS는 LLM Wiki 폴더를 만들지만 Obsidian 앱/vault 등록은 사용자가 직접 확인해야 합니다.
