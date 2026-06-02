# Windows Codex 앱 설치 가이드

[English](./WINDOWS_CODEX_APP_SETUP.md) · [한국어 README](../README.ko.md) · [사용자 가이드](./USER_GUIDE.md)

이 문서는 Windows Codex 앱 사용자가 Agent Context Substrate(ACS)를 GitHub repo에서 바로 설치할 때 필요한 절차를 설명합니다. 목표는 “Codex에게 repo URL을 주고 설치해 달라고 요청하면 스스로 진행할 수 있는” 흐름입니다.

ACS는 Codex 원본 세션을 **읽기 전용**으로 읽고, 정리된 artifact만 ACS 프로젝트의 `data\...` 아래에 씁니다. Obsidian LLM Wiki는 사람이 읽는 curated wiki로 유지합니다.

## 1. 먼저 인지해야 할 경로

| 항목 | Windows 기본 예시 | 설명 |
| --- | --- | --- |
| Codex home | `%USERPROFILE%\.codex` | Codex 앱의 로컬 설정과 세션 저장소 |
| Codex SQLite | `%USERPROFILE%\.codex\state_5.sqlite` | thread metadata. ACS가 읽기 전용으로 조회 |
| Codex rollout JSONL | `%USERPROFILE%\.codex\sessions\...\rollout-*.jsonl` | 실제 thread event. ACS가 읽기 전용으로 조회 |
| ACS project root | clone한 `agent-context-substrate` 폴더 | ACS 코드와 `data\...` artifact 저장 위치 |
| ACS artifacts | `<PROJECT_ROOT>\data\...` | raw export, packet, recovery, ledger, retrieval index |
| LLM Wiki root | `%USERPROFILE%\Documents\LLM Wiki` | Obsidian에서 열 수 있는 사람용 wiki |
| Codex plugin | `%USERPROFILE%\.codex\plugins\agent-context-substrate` | ACS Codex plugin asset |
| Codex user hook | `%USERPROFILE%\.codex\hooks.json` | Stop hook fallback 등록 위치 |

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

PowerShell에서 Codex CLI를 열고:

```powershell
codex
```

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

Hook 파일이나 명령이 바뀌면 Codex가 다시 review 대상으로 표시할 수 있습니다. installer는 이 trust를 자동 승인하지 않습니다.

## 6. Obsidian 안내

ACS는 `%USERPROFILE%\Documents\LLM Wiki` 폴더 구조를 만들 수 있지만, Obsidian 앱을 자동으로 열어 vault로 등록하지는 않습니다.

Obsidian을 설치했다면 Obsidian에서 `Open folder as vault`를 선택하고 아래 폴더를 엽니다.

```text
%USERPROFILE%\Documents\LLM Wiki
```

기본 자동 처리는 `packet-only`입니다. 즉 Codex thread 종료 때 Obsidian에 긴 자동 생성 페이지를 쏟아 넣지 않고, `<PROJECT_ROOT>\data\...` 아래에 context packet, recovery, ledger, retrieval artifact를 저장합니다.

## 7. Fallback 확인

Hook이 아직 trust되지 않았거나 Stop event를 놓친 경우 `codex-watch`를 fallback으로 실행할 수 있습니다.

```powershell
.\.venv\Scripts\agent-context-substrate.exe codex-watch `
  --once `
  --codex-home "$env:USERPROFILE\.codex" `
  --project-root (Resolve-Path -LiteralPath ".").Path `
  --wiki-root "$env:USERPROFILE\Documents\LLM Wiki" `
  --idle-seconds 999999
```

`processed=0`이어도 정상입니다. 위 명령은 오래된 thread를 갑자기 처리하지 않도록 큰 idle window를 사용합니다.

## 8. 순정 Codex에게 맡기는 프롬프트

새 Codex thread에 아래 프롬프트와 GitHub repo URL을 주면, Codex가 README와 이 문서를 보고 설치를 진행할 수 있어야 합니다.

```text
Windows Codex 앱에서 Agent Context Substrate를 설치해줘.

Repo: https://github.com/jjuck/agent-context-substrate

요구사항:
- Windows PowerShell 기준으로 설치해.
- Codex 원본 저장소는 %USERPROFILE%\.codex 아래의 state_5.sqlite와 sessions\...\rollout-*.jsonl임을 사용자에게 알려줘.
- LLM Wiki 기본 경로는 %USERPROFILE%\Documents\LLM Wiki로 잡고, 설치 전에 이 경로를 사용자에게 확인해.
- ACS artifact는 clone한 agent-context-substrate 프로젝트의 data\... 아래에 저장된다고 알려줘.
- scripts/setup-codex-windows.ps1를 기본 설치 경로로 사용해.
- 누락 도구가 있으면 Python.Python.3.13, Git.Git, Obsidian.Obsidian winget ID를 알려주고, 설치 전 사용자에게 확인해.
- 설치 후 doctor-codex, config-codex paths, diagnose-codex 명령을 안내해.
- non-managed hook trust는 자동 우회하지 말고, 설치 후 codex CLI에서 /hooks를 열어 agent-context-substrate Stop hook을 review/trust 하라고 안내해.
```

## 9. 자주 헷갈리는 점

- `기본 권한`, `자동검토`, `전체권한`은 Codex agent의 작업 승인/샌드박스 설정입니다. Hook trust와는 별개입니다.
- ACS는 Codex SQLite와 rollout JSONL을 수정하지 않습니다.
- `doctor-codex`는 설치 상태를 점검하고, `diagnose-codex --fix`는 안전한 ACS 로컬 파일만 복구합니다.
- Obsidian은 선택 의존성입니다. ACS는 LLM Wiki 폴더를 만들지만 Obsidian 앱/vault 등록은 사용자가 직접 확인해야 합니다.
