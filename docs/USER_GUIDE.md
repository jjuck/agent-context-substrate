# Agent Context Substrate 사용자 가이드

[English](./USER_GUIDE.en.md) · [한국어 README](../README.ko.md) · [Windows 설치](./WINDOWS_CODEX_APP_SETUP.ko.md)

ACS는 Hermes와 Codex 세션을 로컬 context packet, 복구 브리프, 검색 가능한 근거로 정리합니다. 이 문서는 일상 사용을 다룹니다. 유지 관리는 [Operations](./OPERATIONS.md), artifact 처리 과정은 [Pipeline](./PIPELINE.md)을 참고하세요.

## 1. 작업 선택

| 작업 | 시작 위치 |
| --- | --- |
| Windows Codex 설치 | [설치·hook 신뢰·진단 전용 가이드](./WINDOWS_CODEX_APP_SETUP.ko.md) |
| Hermes 설치 | 3절 |
| Codex thread 수동 처리 또는 watcher 실행 | 4절 |
| 이전 맥락 검색·복구 | 5절 |
| 검토할 wiki 변경 제안 | 6절 |
| artifact 누락 진단 | 8절 |

기본값은 `packet-only`입니다. raw export → summary → context packet → lint → recovery → ledger 순서로 처리하며, 기계용 artifact를 ACS `data/` 아래에 저장합니다. 세션 페이지를 Obsidian에 자동 승격하지 않습니다. V2 summary와 wiki 승격은 선택적인 추가 단계입니다.

## 2. 경로 확인

| 경로 | 용도 |
| --- | --- |
| `<PROJECT_ROOT>` | `data/`를 포함하는 ACS artifact 범위. 보통 ACS checkout |
| `<WIKI_ROOT>` | 사람이 읽는 LLM Wiki / Obsidian vault |
| `<HERMES_AGENT_ROOT>` | 기존 Hermes Agent checkout과 실행 환경 |
| `HERMES_HOME/state.db` (보통 `~/.hermes/state.db`) | Hermes 원본 세션 |
| `<CODEX_HOME>/state_5.sqlite`, `sessions/**/rollout-*.jsonl` | 로컬 Codex metadata/event. ACS는 읽기 전용으로 접근 |

세션 처리, 검색, hit 확장에 같은 project/wiki root를 사용하세요. `--project-root .`는 현재 디렉터리의 ACS 데이터를 뜻하며 컴퓨터의 모든 프로젝트를 뜻하지 않습니다. Codex Stop hook은 설정된 project root로 범위도 제한합니다. payload의 `cwd`가 그 밖에 있으면 건너뜁니다. Watcher의 범위는 다르므로 4절을 참고하세요.

| Artifact | `<PROJECT_ROOT>` 아래 위치 |
| --- | --- |
| Hermes raw export | `data/exports/<session_id>.json` |
| Codex raw export | `data/exports/raw/codex/<thread_id>.json` |
| Packet | `data/exports/context_packets/<id>.{json,md}` |
| Recovery | `data/exports/recovery/<id>.json` |
| Lint report | `data/exports/lint/` |
| Ledger / watcher 상태 | `data/index/` |
| 선택적 evidence / V2 summary | `data/exports/evidence/`, `data/exports/summaries/` |
| 선택적 claim / promotion / patch | `data/atoms/`, `data/promotions/`, `data/wiki_patches/` |

Obsidian은 실행에 필수가 아닙니다. 페이지를 읽고 정리하려면 `<WIKI_ROOT>`를 vault로 여세요. 초기화는 wiki 구조를 만들지만 Obsidian vault를 등록하거나 열지는 않습니다.

## 3. Hermes 설치 및 활성화

ACS checkout에서 Python 3.11+를 사용하세요. 꺾쇠 괄호 placeholder를 모두 실제 값으로 바꾸세요. 아래 예시는 POSIX shell 기준입니다. Windows Codex 설치에는 전용 PowerShell 안내가 있습니다.

```bash
cd '<PROJECT_ROOT>'
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
agent-context-substrate init-wiki --wiki-root '<WIKI_ROOT>'
agent-context-substrate install-plugin \
  --hermes-home ~/.hermes --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>'
agent-context-substrate install-context-engine \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>'
```

기존 설치를 갱신하려면 두 install 명령에 `--overwrite`를 추가하세요. 설치된 asset을 백업하고 교체합니다. Plugin/context engine 옆에 기기별 `local_config.py`를 기록합니다.

기존 Hermes 실행 환경에서 plugin을 켜세요.

```bash
cd '<HERMES_AGENT_ROOT>'
. venv/bin/activate
hermes plugins enable agent-context-substrate
```

Hermes 설정의 다른 항목을 유지하면서 아래 값을 선택하세요.

```yaml
plugins:
  enabled:
    - agent-context-substrate
context:
  engine: agent_context_substrate
```

Plugin은 finalize hook과 Telegram 명령을 제공합니다. Context engine은 `wiki_recovery_context`, `wiki_knowledge_search`, `wiki_knowledge_expand`를 제공합니다. Asset을 설치하는 것만으로 두 구성 요소가 활성화되지는 않습니다.

실행 중인 gateway는 Telegram `/restart` 또는 `hermes gateway restart`로 재시작하세요. 이어 ACS 환경에서 점검하세요.

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate
agent-context-substrate doctor \
  --hermes-home ~/.hermes --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --fail-on-issues
```

### Hermes 기본값과 제어

환경 변수는 설치된 로컬 설정보다 우선합니다. 아래 suffix 앞에 `AGENT_CONTEXT_SUBSTRATE_`를 붙이세요.

| Suffix | 기본값 | 효과 |
| --- | --- | --- |
| `PROJECT_ROOT` | 설치된 로컬 값, 없으면 `~/.hermes/agent-context-substrate` | ACS 데이터 범위 |
| `WIKI_ROOT` | 설치된 로컬 값, 없으면 `~/LLM Wiki` | Wiki 위치 |
| `AUTO_FINALIZE` | `true` | `false`로 자동 finalize 중지 |
| `MIN_MESSAGE_COUNT` | `3` | 더 짧은 세션 제외 |
| `ALLOWED_SOURCES` | `telegram,cli` | 자동 처리할 세션 source |
| `GATEWAY_POLICY` | `trigger-only` | Gateway hook은 trigger/backstop 역할 |
| `PROMOTION_MODE` | `packet-only` | 자동 결과를 ACS artifact에 저장 |
| `SKIP_TITLE_PATTERNS` | 비어 있음 | 건너뛸 제목 패턴, 쉼표로 구분 |
| `SUMMARY_MODE` | 비어 있음 | V2 summary 생성은 선택 사항 |
| `SUMMARY_JUDGE_MODE` | `off` | 선택적인 artifact 전용 평가 |

Gateway-source 세션은 기본적으로 제외됩니다. 환경 변수를 바꾸면 해당 Hermes 프로세스를 재시작하세요. Legacy `PROMOTION_MODE=full`은 wiki 페이지를 씁니다. 그 동작을 원할 때만 사용하세요.

| Telegram 명령 | 작업 |
| --- | --- |
| `/harness` | 상태, 경로, 정책 확인 |
| `/packet <session_id>` | 설정된 정책으로 선택한 세션 처리 |
| `/wiki-resume <session_id>` | 해당 복구 브리프 표시 |
| `/wiki-lint` | Wiki 및 artifact 일관성 점검 |

## 4. MCP 없이 Codex 처리

[Windows 설치 가이드](./WINDOWS_CODEX_APP_SETUP.ko.md)에 따라 설치하고 hook 신뢰를 검토하세요. Packaged integration은 Stop hook을 사용하며 watcher fallback을 제공합니다. MCP server는 없습니다.

ACS checkout의 PowerShell에서 경로를 명시하세요.

```powershell
$AcsCli = '.\.venv\Scripts\agent-context-substrate.exe'
$AcsRoot = (Resolve-Path -LiteralPath '.').Path
$AcsWiki = "$env:USERPROFILE\Documents\LLM Wiki"
$AcsCodex = "$env:USERPROFILE\.codex"
& $AcsCli codex-status --codex-home $AcsCodex
& $AcsCli codex-finalize --thread-id '<THREAD_ID>' `
  --codex-home $AcsCodex --project-root $AcsRoot --wiki-root $AcsWiki
```

`codex-status`에서 thread ID를 고르세요. 수동 finalize는 packet, recovery, lint, ledger artifact를 쓰며 hook 신뢰가 필요하지 않습니다. 원본 파일은 읽기 전용으로 유지됩니다.

현재 idle 상태인 thread를 한 번 처리하려면:

```powershell
& $AcsCli codex-watch --once --idle-seconds 300 `
  --codex-home $AcsCodex --project-root $AcsRoot --wiki-root $AcsWiki
```

이 명령은 dry-run이 아니라 실제 처리 명령입니다. 선택한 Codex home 전체에서 세션을 찾으며 Stop hook의 `cwd` 필터는 적용하지 않습니다. 조건에 맞는 오래된 thread도 선택한 ACS root로 export될 수 있습니다. Idle 기준을 높이면 최근 변경된 thread의 처리가 늦춰질 뿐, 오래된 thread가 제외되지는 않습니다.

계속 감시하려면 `--once`를 빼세요. `--interval-seconds`로 polling 간격을 설정하고 Ctrl+C로 중지합니다. Watcher는 처리한 rollout fingerprint를 `data/index/codex_watcher_state.json`에 기록합니다.

현재 Codex finalize는 packet-only summary 경로를 사용하며 `--summary-mode` flag가 없습니다. 그 결과에 claim 추출용 V2 artifact가 이미 포함되어 있다고 가정하지 마세요.

## 5. 맥락 검색·복구

설치된 CLI를 각 shell에서 사용하세요. 아래 예시는 POSIX 줄 이어쓰기 기준입니다.

```bash
agent-context-substrate search-knowledge \
  --query 'deployment decision' --mode knowledge \
  --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>'
agent-context-substrate expand-hit \
  --hit-id '<HIT_ID>' --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>'
```

검색 결과의 `hit_id`를 복사하세요. 복구 브리프에는 `--mode recovery`, 관계 탐색에는 `--mode graph`를 사용합니다. `--limit`, `--json`으로 결과를 조정합니다. `--include-raw`는 Hermes 원본 메시지를 포함하는 옵션이며 Codex home을 임의로 스캔하는 옵션이 아닙니다. Raw-message hit는 snippet/provenance를 제공하며 전체 확장은 비활성화되어 있습니다.

검색은 wiki 페이지, export된 packet, recovery 및 지원되는 artifact를 읽습니다. Codex 근거는 export를 통해 사용할 수 있습니다. 검색과 확장은 Obsidian을 수정하지 않습니다. 기본 제외 wiki 폴더는 `.obsidian/`, `_system/`, `90 보관/`입니다.

## 6. 선택적 V2 summary → claim → 검토한 wiki patch

다음 V2 build 명령은 **Hermes session ID**를 받습니다. 근거를 포함한 summary가 필요할 때 실행하세요.

```bash
agent-context-substrate build-context-packet \
  --session-id '<SESSION_ID>' --packet-id '<PACKET_ID>' \
  --task-title '<TASK>' --macro-context '<CONTEXT>' \
  --unit-title '<UNIT>' --goal '<GOAL>' \
  --summary-mode heuristic --summary-cache on --project-root '<PROJECT_ROOT>'
```

`heuristic`은 로컬에서 결정적으로 실행됩니다. `custom-command`는 JSON stdin/stdout을 처리하는 `--summarizer-command`가 필요합니다. `agent-llm`, `hybrid`는 LLM router를 제공하는 host integration이 필요하며 standalone CLI는 router를 제공하지 않습니다. `--summary-judge-mode hybrid`는 summary mode가 필요하지만 router 없이도 실행할 수 있습니다. Router가 없거나 실패하면 `judge_unavailable`과 함께 degraded mechanical verdict를 반환합니다. Semantic 판단에는 정상적인 host router가 필요합니다. Judge는 patch를 적용하는 대신 평가 artifact를 만듭니다.

V2 summary가 준비되면 같은 ACS root에서 진행하세요.

```bash
cd '<PROJECT_ROOT>'
agent-context-substrate extract-atoms --packet-id '<PACKET_ID>' --project-root .
agent-context-substrate propose-promotions --packet-id '<PACKET_ID>' --project-root .
agent-context-substrate plan-wiki-patches \
  --promotion-file 'data/promotions/<PACKET_ID>.json' \
  --wiki-root '<WIKI_ROOT>' --project-root .
agent-context-substrate apply-wiki-patch \
  --patch-file 'data/wiki_patches/<PACKET_ID>.json' \
  --wiki-root '<WIKI_ROOT>' --project-root .
```

Planning은 `pending` candidate를 사용합니다. 생성된 JSON/Markdown의 근거, 대상, diff를 검토하세요. `review-promotion --candidate-id '<ID>' --preview-evidence --project-root .`는 상태를 바꾸지 않고 미리 보여줍니다. Planning과 기본 patch 적용은 wiki 페이지를 쓰지 않습니다.

제안과 dry-run 결과를 검토한 뒤 apply 명령에 `--apply`를 추가해 다시 실행하세요. 사람의 검토는 workflow 요건이며 CLI가 강제하는 승인 gate는 아닙니다. 현재 alpha operation은 페이지 생성, managed claim block, section append를 다룹니다. 지원하지 않거나 충돌하는 변경은 건너뜁니다. 새 seed 페이지와 언어 metadata를 검토한 뒤 정리된 지식으로 사용하세요. 자세한 내용은 [Pipeline](./PIPELINE.md)을 참고하세요.

## 7. Wiki 언어와 lint 관리

초기화된 vault에는 `Home.md`, `index.md`, `SCHEMA.md`, `log.md`, 번호가 붙은 콘텐츠 폴더, `_system/`이 있습니다. 언어 설정은 `_system/config.yaml`, template은 `_system/templates/ko/`, `en/`에 있습니다.

사람용 페이지에는 title, type, category, status, tags와 함께 `lang: ko` 또는 `lang: en`을 넣으세요. 두 언어 모두 폴더 이름은 한국어로 유지할 수 있습니다. 페이지를 추가할 때 해당 언어 template을 사용하세요.

```bash
export WIKI_PATH='<WIKI_ROOT>'
agent-context-substrate lint-wiki --project-root '<PROJECT_ROOT>' --report-id wiki-lint
```

PowerShell에서는 `export` 대신 `$env:WIKI_PATH = $AcsWiki`를 사용하세요. Lint는 report를 쓰며 페이지를 고치지 않습니다. `--semantic`은 semantic artifact 점검을 포함하고, `--fail-on-issues`는 문제가 있을 때 0이 아닌 exit code를 반환합니다.

## 8. 진단 및 개인정보 보호

| 증상 | 확인 / 다음 조치 |
| --- | --- |
| Hermes `/harness`가 degraded | 경로/import 오류를 확인하고 ACS 환경에서 `doctor` 실행 |
| Hermes 설정이 이전 값 | 변경 후 gateway/프로세스 재시작 |
| Hermes 자동 finalize가 건너뛰어짐 | Source, 메시지 수, skip pattern, 정책 확인 |
| Codex Stop hook 결과가 없음 | Windows 가이드에서 설치, 신뢰, runtime, `cwd` 범위 확인 |
| Packet이 reused | Ledger와 필수 artifact 확인. 정상 재사용일 수 있음 |
| 검색 결과가 없음 | Project/wiki root가 일치하고 원본이 finalize로 export되었는지 확인 |
| Claim 추출 입력이 없음 | 먼저 V2 summary 생성. Legacy packet만으로는 부족 |
| Lint 언어/링크 오류 | Frontmatter 또는 링크 대상을 고치고 lint 재실행 |

원본 DB, rollout, export, summary, provenance, 설치된 로컬 설정에는 메시지, 비밀정보, 코드, 개인정보, 기기 경로가 들어갈 수 있습니다. 비공개로 보관하고 공유 전에 변경 사항을 확인하세요. 선택한 LLM/custom summary는 필터링한 근거를 설정된 provider나 process로 보낼 수 있습니다. Redaction이 모든 민감정보 제거를 보장하지는 않습니다.

유지 관리와 공개 배포 점검은 [Operations](./OPERATIONS.md), [Release checklist](./RELEASE_CHECKLIST.md)를 참고하세요. 설치 상태, CLI help, artifact 점검은 서로 다른 근거를 제공합니다. 어느 하나만으로 GUI hook 실행 성공을 증명할 수는 없습니다.
