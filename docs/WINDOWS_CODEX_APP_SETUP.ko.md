# Windows Codex 앱 설치 가이드

[English](./WINDOWS_CODEX_APP_SETUP.md) · [한국어 README](../README.ko.md) · [사용자 가이드](./USER_GUIDE.md) · [Operations](./OPERATIONS.md)

이 가이드에서 ACS 설치, hook 신뢰 검토, 로컬 설치 진단을 진행하세요. ACS는 Codex 원본 세션을 읽기 전용으로 읽고 설정된 project root 아래에 파생 artifact를 씁니다. 일상 검색, 수동 finalize, 선택적 wiki 갱신은 [사용자 가이드](./USER_GUIDE.md), artifact 동작은 [Pipeline](./PIPELINE.md)을 참고하세요.

## 1. 경로와 범위 선택

| 항목 | 기본값 / 예시 |
| --- | --- |
| Codex home | `%USERPROFILE%\.codex` |
| Codex metadata | `<CODEX_HOME>\state_5.sqlite` |
| Codex rollout | `<CODEX_HOME>\sessions\...\rollout-*.jsonl` |
| ACS project root | Clone한 `agent-context-substrate` checkout |
| ACS artifact | `<PROJECT_ROOT>\data\...` |
| LLM Wiki | `%USERPROFILE%\Documents\LLM Wiki` |
| 설치된 plugin | `<CODEX_HOME>\plugins\agent-context-substrate` |
| User hook (명시적 선택) | `<CODEX_HOME>\hooks.json` |

`project_root`는 ACS artifact 범위이자 Stop hook의 `cwd` 필터입니다. 기본 checkout root가 **다른 repository의 작업까지 자동 수집하지는 않습니다**. Stop payload의 `cwd`가 설정된 root 밖이면 건너뜁니다. 의도한 범위를 선택하세요. 수동 finalize와 watcher의 세션 선택 방식은 다릅니다.

ACS checkout과 `.venv`를 유지하세요. Editable install이며 설치된 hook은 설정된 Python/project 경로를 참조합니다. 이동하거나 삭제하면 설정/설치를 갱신해야 합니다.

## 2. 준비물 확인

Python 3.11+, Git, PowerShell, 로컬 세션 파일을 제공하는 Codex runtime을 사용하세요. Obsidian은 선택 사항입니다. Bootstrap은 명령 존재 여부를 확인합니다. `py`나 `python`을 찾았다는 것만으로 선택된 interpreter 버전이나 Codex GUI hook 동작을 확인할 수는 없습니다.

| 도구 | Bootstrap 설치 옵션 |
| --- | --- |
| Python | `-InstallMissingTools`, winget `Python.Python.3.13` |
| Git | `-InstallMissingTools`, winget `Git.Git` |
| Obsidian | `-InstallObsidian`, winget `Obsidian.Obsidian` |
| Codex 앱/CLI | 별도 설치. Bootstrap에서 설치하지 않음 |

도구 설치 후 PATH 갱신을 위해 새 terminal이 필요할 수 있습니다. Script는 `.venv`를 만들 때 `py -3`를 우선 사용합니다. Python이 여러 버전이면 생성된 interpreter를 확인하세요.

## 3. PowerShell에서 설치

저장소의 [설치 스크립트](../scripts/setup-codex-windows.ps1)를 실행합니다.

```powershell
git clone https://github.com/jjuck/agent-context-substrate.git agent-context-substrate
cd agent-context-substrate
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -CheckOnly
```

`-CheckOnly`는 ACS setup 전에 종료합니다. 준비물 확인만 하려면 설치 switch **없이** 실행하세요. 도구 처리가 종료 지점보다 먼저 실행되므로 설치 switch와 조합하면 누락된 시스템 도구를 설치할 수 있습니다.

표시된 기본 경로로 ACS를 설치하세요.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
```

다른 wiki나 Codex home에는 `-WikiRoot`, `-CodexHome`을 지정하세요. `-ProjectRoot`는 editable install과 artifact에 사용할 ACS checkout을 선택합니다. ACS package가 있는 경로여야 하므로 다른 repository의 세션을 수집하려고 bootstrap의 이 옵션을 그 repository로 지정할 수는 없습니다. 누락된 도구 설치를 허용하려면:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -InstallMissingTools -InstallObsidian
```

Script는 `.venv` 생성, pip 갱신, `pip install -e .`로 ACS 설치 후 명시한 경로로 `setup-codex --yes`를 실행합니다. Setup은 wiki 초기화, bundled hook이 포함된 plugin/config 설치, 개인 marketplace/cache 등록, 로컬 진단을 수행합니다. `--yes`는 setup 선택을 수락하며 hook 신뢰를 부여하지 않습니다.

0.2.2에서는 Stop 실행 경로를 하나만 설치합니다. `setup-codex`, wizard, 진단 복구의 기본값은 bundled plugin hook이며 전역 ACS user hook을 추가하지 않습니다. `setup-codex`와 `install-codex-plugin`은 `--install-user-hook`을 명시하면 user hook으로 전환하고 설치본의 bundled hook을 비웁니다. `setup-codex --no-user-hook`은 bundled 기본값을 선택하는 호환 옵션으로 유지되며 `--install-user-hook`과 함께 사용할 수 없습니다. Bundled 방식으로 되돌릴 때는 user hook에서 ACS handler만 제거하고 다른 handler는 보존합니다. Doctor는 bundled hook이 설치되어 있으면 user hook 부재를 경고하지 않습니다. Watcher는 별도로 시작하는 fallback입니다.

Windows bundled 명령은 shell별 `%PLUGIN_ROOT%` 확장 대신 Python에서 환경변수를 읽습니다. Marketplace cache는 manifest 버전 경로를 사용하며 실행 중인 host가 참조할 수 있는 이전 cache를 보존합니다. 재설치 후 Codex에서 개인 plugin을 갱신/재설치하고, 실제 로드된 버전과 hook을 확인한 다음 이전 cache 정리를 판단하세요.

기존 개인 marketplace 설치를 직접 재설치할 때는 `--personal-marketplace-root '<MARKETPLACE_ROOT>'`를 다시 지정하세요. 누락하면 파일을 변경하기 전에 거부하므로, 등록된 plugin 복사본은 그대로인데 user hook만 꺼지는 상태를 방지합니다. `setup-codex`는 선택한 marketplace root를 자동 전달합니다.

CLI가 준비된 뒤 경로를 대화형으로 검토하려면:

```powershell
.\.venv\Scripts\agent-context-substrate.exe setup-codex-wizard
```

Setup 파일을 쓰지 않고 ACS 설치 계획을 확인하려면:

```powershell
.\.venv\Scripts\agent-context-substrate.exe setup-codex --dry-run
```

## 4. 설치 상태와 runtime을 구분해 확인

ACS checkout에서 실행하세요.

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

사용자 지정 경로를 골랐다면 변수 값을 바꾸세요. `config-codex paths`는 인수/기본값으로 계산한 경로를 표시합니다. `config-codex show`는 설치된 `local_config.json`을 읽습니다. 표시된 경로가 설치 설정에서 왔다고 가정하지 말고 둘을 비교하세요.

`doctor-codex`는 로컬 파일, 설정 일치, interpreter 버전, 데이터 디렉터리 쓰기 가능 여부를 확인합니다. `--fail-on-issues` 사용 시 필수 항목 실패는 0이 아닌 exit code를 반환합니다. 경고가 있어도 `ok=True`일 수 있습니다. `hook_support`는 ACS의 지원 가정을 표시하고 `hook_primary_installed`는 hook 파일을 확인합니다. 어느 값도 Codex가 hook을 로드·활성화·신뢰·실행했다는 증거가 아닙니다. 원본 metadata 존재 여부와 runtime 동작은 따로 확인해야 합니다.

## 5. Hook 활성화와 신뢰

ACS는 plugin 디렉터리 아래 기본 `hooks/hooks.json`을 제공합니다. 공식 [plugin packaging 문서](https://developers.openai.com/plugins/build/plugins)는 기본 hook 탐색을 설명합니다. 탐색이나 plugin 설치/활성화가 non-managed command hook의 신뢰를 부여하지는 않습니다.

사용 중인 Codex runtime에서 ACS plugin이 활성화되어 있는지 확인하세요. Hook 검토는 공식 [hooks 문서](https://developers.openai.com/docs/hooks)의 안내대로 Codex CLI를 열고 `/hooks`를 입력하세요.

```powershell
codex
```

```text
/hooks
```

`agent-context-substrate`, `codex_stop_finalize.py`, `Finalizing Codex thread into Agent Context Substrate`에 해당하는 명령/경로를 검토하고 제공되는 검토 화면에서 신뢰를 부여하세요. 사용 중인 runtime의 제어 기능을 따르세요. 이 가이드는 GUI 상태를 테스트했다고 주장하거나 특정 버튼 이름을 전제하지 않습니다.

Full Access, sandbox 설정, approval mode는 hook 신뢰와 별개입니다. 재설치/복구를 포함해 hook 정의나 명령이 바뀌면 다시 검토해야 할 수 있습니다. ACS setup은 이 단계를 우회하지 않습니다. Runtime에 hook 검토 화면이 없거나 Stop event를 놓치면 수동 finalize나 watcher를 사용하세요.

실제 실행을 검증하려면 설정된 범위 안의 thread에서 Stop event가 발생한 뒤 해당 packet/recovery/ledger artifact를 확인하세요. 설치된 파일이나 정상 doctor report만으로는 충분하지 않습니다. `data/index/codex_hook_events.jsonl`에서 `finalized`는 처리 완료, `skipped`는 미처리를 뜻합니다. 설치본을 구분할 수 있도록 plugin root, script path, 실행 Python도 기록합니다. 범위 밖이라 건너뛴 경우에도 Codex 화면에는 hook 성공으로 표시될 수 있습니다.

## 6. 수동 finalize 및 watcher fallback

Thread를 확인한 뒤 선택한 ID를 처리하세요.

```powershell
& $AcsCli codex-status --codex-home $AcsCodex
& $AcsCli codex-finalize --thread-id '<THREAD_ID>' `
  --codex-home $AcsCodex --project-root $AcsRoot --wiki-root $AcsWiki
```

수동 처리는 hook 신뢰가 필요하지 않습니다. Watcher를 한 번 실행하려면:

```powershell
& $AcsCli codex-watch --once --idle-seconds 300 `
  --codex-home $AcsCodex --project-root $AcsRoot --wiki-root $AcsWiki
```

`--once`는 조건에 맞는 idle thread의 artifact를 쓰며 dry-run이 아닙니다. Watcher는 hook의 project `cwd` 필터 없이 선택한 Codex home을 탐색하므로 다른 프로젝트의 오래된 세션도 `$AcsRoot`로 export할 수 있습니다. `--idle-seconds`를 높이면 최근 변경된 세션 처리가 늦춰질 뿐 오래된 세션은 여전히 대상이 될 수 있습니다. `processed=0`은 처리할 미처리 thread가 없었다는 뜻이며 hook 실행을 증명하지 않습니다. 계속 감시하려면 `--once`를 빼고 Ctrl+C로 중지하세요.

## 7. 진단·복구 및 wiki 열기

| 증상 | 확인 / 조치 |
| --- | --- |
| CLI executable이 없음 | `.venv` Python과 pip 출력 확인. Python 3.11+인지 확인 |
| 필수 doctor 항목 실패 | 해당 항목과 명시한 project/wiki/Codex 경로 확인 |
| Doctor는 정상인데 자동 packet 없음 | Plugin 활성화, hook 신뢰, Stop event 전달, `cwd` 범위 확인 |
| Codex 원본 파일 없음 | Runtime이 사용하는 Codex home에 로컬 세션이 있는지 확인 |
| 이동/갱신 후 hook 중지 | 설치 설정, Python 경로, hook 정의, 신뢰 비교 |
| Obsidian에 vault 없음 | 선택한 wiki 폴더를 직접 vault로 열기 |

필수 setup 항목이 실패하면 경로를 명시해 로컬 ACS 복구를 요청하세요.

```powershell
& $AcsCli diagnose-codex --fix --codex-home $AcsCodex `
  --project-root $AcsRoot --wiki-root $AcsWiki
```

필수 항목 실패 시 복구는 wiki 구조, plugin/config, bundled hook, marketplace asset에 대해 setup을 다시 실행합니다. 기존 ACS user hook 설치도 bundled 기본값으로 전환하며 다른 handler는 보존합니다. 모든 경고를 고치거나 누락 도구를 전부 설치하거나 신뢰를 부여하지는 않습니다. 이후 hook 변경을 검토하세요.

필요하면 Obsidian의 `Open folder as vault`로 `<WIKI_ROOT>`를 여세요. 기본 `packet-only`는 세션 결과를 ACS `data/`에 저장하며 검토한 wiki patch는 선택 사항입니다. 원본 세션, 파생 artifact, 로컬 설정, provenance는 비공개로 취급하고 공유 전에 확인하세요.
