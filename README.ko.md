<div align="center">

# Agent Context Substrate

**Hermes와 Codex 대화 기록을 다시 찾고, 이어서 작업하고, 필요할 때 검색할 수 있는 개인 지식층으로 바꾸는 도구입니다.**

![Status](https://img.shields.io/badge/status-public%20alpha-orange) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) [![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

[English README](./README.md) · [빠른 시작](#빠른-시작) · [Windows Codex 앱 설치](#windows-codex-앱-빠른-설치) · [Hermes에 설치](#hermes에-설치) · [검증된 기준선](#검증된-기준선) · [사용자 가이드](./docs/USER_GUIDE.md) · [Windows 상세 가이드](./docs/WINDOWS_CODEX_APP_SETUP.ko.md)

</div>

## 한 줄로 말하면

`agent-context-substrate`는 Hermes Agent나 Codex 앱에서 나눈 긴 대화를 그냥 흘려보내지 않고, 나중에 다시 쓸 수 있는 **요약 파일, 복구 브리프, 검색 가능한 지식 자료**로 정리해주는 Python CLI 도구입니다.

현재 packaged adapter는 **Hermes Agent**와 **비-MCP Codex 로컬 세션 source**를 지원합니다. Codex 경로는 `~/.codex/state_5.sqlite`와 `~/.codex/sessions/**/rollout-*.jsonl`을 read-only로 읽고, plugin Stop hook을 primary trigger로 사용하며 `codex-watch` fallback을 유지합니다. 이 프로젝트의 이전 이름은 `hermes-llm-wiki-harness`였습니다.

Hermes는 `~/.hermes/state.db`에 대화 기록을 저장하고, Codex 앱은 `%USERPROFILE%\.codex\state_5.sqlite`와 rollout JSONL에 thread 정보를 저장합니다. 이 하네스는 원본을 읽기 전용으로 읽어서 다음을 만듭니다.

```text
Hermes 대화 DB 또는 Codex rollout JSONL
  -> 원본 세션 export
  -> context packet JSON / Markdown
  -> lint report JSON / Markdown
  -> recovery brief JSON
  -> session ledger
  -> Hermes가 필요할 때 읽는 검색 도구
```

## 왜 유용한가

긴 대화형 AI 작업에서는 이런 문제가 자주 생깁니다.

- 이전 세션에서 무슨 결정을 했는지 기억이 안 난다.
- Telegram이나 CLI 세션이 재시작되어 맥락이 사라진다.
- 프로젝트 설계, 파일 경로, 테스트 결과가 대화 속에 묻혀 있다.
- Obsidian에는 사람이 읽는 문서만 남기고 싶고, 자동 생성된 중간 산출물은 분리하고 싶다.

이 도구를 쓰면:

- 이전 Hermes/Codex 세션을 `context packet`으로 정리할 수 있습니다.
- 새 세션에서 빠르게 맥락을 복구할 수 있습니다.
- Hermes가 작업 중 필요하면 `wiki_knowledge_search`로 과거 지식을 직접 찾을 수 있습니다.
- Obsidian vault는 사람이 읽는 semantic wiki로 유지하고, 자동 생성 artifact는 프로젝트 `data/exports/`에 분리합니다.

## 기본 정책: packet-only

기본 자동 처리 모드는 **`packet-only`**입니다.

즉, 세션 종료/리셋 때 자동으로 Obsidian 문서를 마구 만들지 않습니다. 대신 아래 파일들을 프로젝트 안에 저장합니다.

```text
data/exports/<session_id>.json
data/exports/context_packets/<session_id>.json
data/exports/context_packets/<session_id>.md
data/exports/lint/<session_id>-lint.json
data/exports/lint/<session_id>-lint.md
data/exports/recovery/<session_id>.json
data/index/session_ledger.json
```

Obsidian은 사람이 직접 정리하는 지식 베이스로 남겨둡니다.

새로운 지식 성장 경로는 바로 쓰기가 아니라, 검토 가능한 제안 흐름입니다.

```text
ContextPacket
  -> EvidenceBundle
  -> MicroSummaryV2 / UnitSummaryV2
  -> claim atom
  -> promotion candidate
  -> wiki patch proposal
  -> 검토 후 Obsidian 반영
```

즉 `ContextPacket`은 wiki page가 아니라, wiki를 안전하게 키우기 위한 재료입니다.

## 빠른 사실

| 항목 | 값 |
| --- | --- |
| 상태 | Public alpha; v0.2.0 로컬 release candidate; Hermes Agent와 비-MCP Codex 로컬 연동 포함 |
| 실행 환경 | Python 3.11+ |
| 주 인터페이스 | CLI: `agent-context-substrate` |
| 현재 agent 지원 | Hermes Agent와 Codex 로컬 세션 |
| Hermes 연동 | user plugin `agent-context-substrate` + context engine `agent_context_substrate` |
| Codex 연동 | `codex-finalize`, `codex-watch`, `codex-status`, 비-MCP Codex plugin skill |
| 장기 확장 방향 | Claude Code, OpenCode, Gemini 등은 추후 adapter로 추가 가능하나 아직 packaged support는 없음 |
| 기본 산출물 | `data/exports/`, `data/index/session_ledger.json` |
| 기본 promotion mode | `packet-only` |
| 선택 요약 모드 | `heuristic`, `agent-llm`, `hybrid`, `custom-command`, `codex-cli`, `auto` |
| 권장 wiki 성장 경로 | atoms -> promotion candidates -> dry-run wiki patch proposals |
| Obsidian 역할 | 사람이 읽는 semantic wiki |
| 지원 wiki 언어 | `ko`, `en` |
| 라이선스 | MIT |

## 빠른 시작

Windows Codex 앱 사용자라면 먼저 [Windows Codex 앱 빠른 설치](#windows-codex-앱-빠른-설치)를 보세요. 아래 블록은 개발자용 smoke 경로입니다.

```bash
git clone https://github.com/jjuck/agent-context-substrate.git agent-context-substrate
cd agent-context-substrate
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
python -m pytest -q
ruff check .
.venv/bin/agent-context-substrate --help
```

기대 결과:

```text
305 passed, 12 skipped
```

그리고 `--help`에 다음 명령들이 보여야 합니다.

```text
init-wiki
install-plugin
install-codex-plugin
setup-codex
setup-codex-wizard
doctor-codex
diagnose-codex
config-codex
install-context-engine
doctor
fresh-install-smoke
codex-status
codex-finalize
codex-watch
extract-session
build-context-packet
lint-wiki
```

## Windows Codex 앱 빠른 설치

Codex 앱만 쓰는 사용자는 Hermes 섹션을 건너뛰고 이 절차로 시작하면 됩니다. 순정 Codex에게 GitHub repo URL만 주는 경우에도 아래 경로와 명령을 기준으로 설치하게 하면 됩니다.

설치 전에 사용자가 알아야 할 경로:

| 경로 | Windows 기본값 | 용도 |
| --- | --- | --- |
| Codex SQLite | `%USERPROFILE%\.codex\state_5.sqlite` | Codex thread metadata. ACS가 읽기 전용으로 조회 |
| Codex rollout | `%USERPROFILE%\.codex\sessions\...\rollout-*.jsonl` | Codex event stream. ACS가 읽기 전용으로 조회 |
| LLM Wiki | `%USERPROFILE%\Documents\LLM Wiki` | Obsidian에서 여는 사람용 wiki |
| ACS project data | `<PROJECT_ROOT>\data\...` | raw export, packet, recovery, ledger, retrieval artifact |

PowerShell 단일 설치:

```powershell
git clone https://github.com/jjuck/agent-context-substrate.git agent-context-substrate
cd agent-context-substrate
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
```

도구가 빠져 있으면 아래처럼 선택 설치를 허용할 수 있습니다. script가 쓰는 winget package ID는 `Python.Python.3.13`, `Git.Git`, `Obsidian.Obsidian`입니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -InstallMissingTools -InstallObsidian
```

plain `codex`가 `%APPDATA%\npm\codex.ps1` 같은 npm shim을 가리키면 Windows Codex 앱 CLI가 아닐 수 있습니다. `doctor-codex`와 setup script는 `%LOCALAPPDATA%\OpenAI\Codex\bin` 아래의 direct app CLI 후보를 보여주며, `/hooks` review에는 그 경로를 쓰는 편이 안전합니다.

설치 후 확인:

```powershell
.\.venv\Scripts\agent-context-substrate.exe doctor-codex --fail-on-issues
.\.venv\Scripts\agent-context-substrate.exe config-codex paths
```

문제가 있으면:

```powershell
.\.venv\Scripts\agent-context-substrate.exe diagnose-codex
.\.venv\Scripts\agent-context-substrate.exe diagnose-codex --fix
```

대화형으로 경로를 보며 설치하려면:

```powershell
.\.venv\Scripts\agent-context-substrate.exe setup-codex-wizard
```

마지막으로 Codex CLI에서 `/hooks`를 열거나 시작 시 `Hooks need review` modal이 뜨면 hook command를 확인한 뒤 `Trust all and continue` 또는 해당 trust 동작을 선택해야 자동 finalize가 실행됩니다. 이 단계는 `전체권한` 설정과 별개이며, installer가 몰래 우회하지 않습니다. 기본 설치는 plugin Stop hook 하나만 활성화하고, `~\.codex\hooks.json` fallback은 중복 Stop hook을 피하기 위해 기본으로 설치하지 않습니다. plugin hook을 쓸 수 없는 런타임에서만 `--user-hook-fallback`을 명시하세요.

실제 smoke에서는 짧은 Codex thread 종료 후 `Running Stop hook: Finalizing Codex thread into Agent Context Substrate`가 보이고, `data\index\codex_hook_events.jsonl`에 `status=finalized`가 남으며, `search-knowledge --mode recovery`로 방금 만든 recovery artifact가 검색되어야 합니다.

순정 Codex에게 GitHub repo만 주고 설치를 맡기려면 [Windows 상세 가이드의 프롬프트](./docs/WINDOWS_CODEX_APP_SETUP.ko.md#5-순정-codex에게-맡기는-프롬프트)를 그대로 붙여넣으세요.

## Hermes에 설치

아래 placeholder를 실제 경로로 바꾸세요.

| Placeholder | 의미 |
| --- | --- |
| `<PROJECT_ROOT>` | 이 repository checkout 또는 harness project root |
| `<WIKI_ROOT>` | Obsidian LLM Wiki vault root |
| `<HERMES_AGENT_ROOT>` | Hermes Agent root, 보통 `~/.hermes/hermes-agent` |

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate

# 1) Obsidian LLM Wiki 기본 구조 생성 또는 보강
.venv/bin/agent-context-substrate init-wiki \
  --wiki-root '<WIKI_ROOT>'

# 2) Hermes user plugin 설치
.venv/bin/agent-context-substrate install-plugin \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

# 3) Hermes context engine 설치
.venv/bin/agent-context-substrate install-context-engine \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

# 4) 설치 상태 점검
.venv/bin/agent-context-substrate doctor \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --fail-on-issues
```

Hermes plugin을 켭니다.

```bash
cd '<HERMES_AGENT_ROOT>'
. venv/bin/activate
hermes plugins enable agent-context-substrate
```

`~/.hermes/config.yaml`에서 context engine을 선택합니다.

```yaml
plugins:
  enabled:
    - agent-context-substrate

context:
  engine: agent_context_substrate
```

Telegram gateway가 이미 실행 중이었다면 설정 반영을 위해 재시작하세요.

```text
/restart
```

## Codex에 설치

Codex 연동은 hook-primary, watcher fallback 전략입니다. packaged plugin은 manifest `hooks`를 쓰지 않고 `hooks/hooks.json`에 Stop hook을 포함합니다. Codex `/hooks` review로 hook을 trust하면 Stop hook이 thread를 finalize하고, hook이 trust되지 않았거나 Stop event를 놓친 경우 `codex-watch`가 fallback으로 동작합니다.

Windows Codex 앱 사용자는 [Windows Codex 앱 빠른 설치](#windows-codex-앱-빠른-설치) 또는 [Windows 상세 가이드](./docs/WINDOWS_CODEX_APP_SETUP.ko.md)를 먼저 보는 것이 좋습니다. 아래 명령은 portable 개발자용 형태입니다.

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate

.venv/bin/agent-context-substrate install-codex-plugin \
  --codex-home ~/.codex \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

.venv/bin/agent-context-substrate codex-status --codex-home ~/.codex

# Expected mode:
# hook_support=supported
# hook_primary=installed
# watcher_fallback=available
```

Codex의 non-managed hook은 한 번 review/trust 해야 실행됩니다. Codex CLI에서 `/hooks`를 열고 `agent-context-substrate` Stop hook을 trust하세요. Hook 승인이 안 되었거나 Stop event를 놓친 환경에서는 watcher fallback을 명시적으로 실행할 수 있습니다.

기본으로 plugin hook과 `~/.codex/hooks.json` fallback을 함께 설치하지 마세요. 특정 Codex 런타임에서 plugin-bundled hook을 읽지 못할 때만 `setup-codex --user-hook-fallback` 또는 lower-level `install-codex-plugin --install-user-hook`을 사용하세요.

```bash
.venv/bin/agent-context-substrate codex-watch \
  --codex-home ~/.codex \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --interval-seconds 15 \
  --idle-seconds 90
```

수동 finalize도 가능합니다.

```bash
.venv/bin/agent-context-substrate codex-finalize \
  --thread-id '<CODEX_THREAD_ID>' \
  --codex-home ~/.codex \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>'
```

## 처음 설치가 제대로 됐는지 확인하기

실제 Obsidian vault를 건드리지 않고 temp directory에서 배포 경로를 테스트합니다.

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate
TMP_PROJECT=$(mktemp -d)
TMP_WIKI=$(mktemp -d)
TMP_AGENT=$(mktemp -d)

.venv/bin/agent-context-substrate fresh-install-smoke \
  --session-id '<SESSION_ID>' \
  --hermes-home ~/.hermes \
  --project-root "$TMP_PROJECT" \
  --wiki-root "$TMP_WIKI" \
  --hermes-agent-root "$TMP_AGENT"
```

성공 예시:

```text
fresh-install-smoke ok=True
retrieval_hit_count=1
expanded_content_length=14195
lint_issue_count=0
```

## 검증된 기준선

현재 public alpha 기준선은 공개 repository와 package-managed integration 경로에서 검증되었습니다.

| 항목 | 현재 결과 |
| --- | --- |
| 프로젝트 테스트 | `305 passed, 12 skipped` |
| Fresh install smoke | `fresh-install-smoke ok=True`, `retrieval_hit_count=1`, `expanded_content_length=14195`, `lint_issue_count=0` |
| 실제 wiki lint | `checked_pages=15`, `missing_provenance=0`, `orphan_pages=0`, `missing_from_index=0`, `broken_wikilinks=0` |
| Live Codex 연결 | plugin `agent-context-substrate`, Stop hook 설치됨, watcher fallback 사용 가능 |
| Live Hermes 연결 | plugin `agent-context-substrate`, context engine `agent_context_substrate`, retrieval tools 로드됨 |
| GitHub sync | `main`이 `jjuck/agent-context-substrate`에 push됨 |

release를 자르거나 installer/runtime 동작을 바꾸면 이 기준선을 다시 갱신하세요.

## 자주 쓰는 명령

| 명령 | 설명 |
| --- | --- |
| `extract-session` | Hermes 세션 하나를 raw JSON으로 export합니다. |
| `build-context-packet` | raw export와 context packet을 생성합니다. `--summary-mode`를 주면 v2 evidence/summary도 생성합니다. |
| `extract-atoms` | v2 summary에서 claim atom을 추출합니다. |
| `propose-promotions` | claim atom을 wiki 반영 후보로 제안합니다. Obsidian은 수정하지 않습니다. |
| `plan-wiki-patches` | promotion candidate를 dry-run wiki patch proposal로 바꿉니다. |
| `apply-wiki-patch` | 기본은 dry-run입니다. `--apply`를 명시해야 안전한 managed block만 씁니다. |
| `list-promotions` | promotion queue 상태를 봅니다. |
| `list-wiki-patches` | wiki patch proposal/apply 기록을 봅니다. |
| `lint-promotions` | promotion/wiki patch 기록에 대한 semantic lint를 실행합니다. |
| `build-topic-map` | wiki와 substrate artifact로 topic map report를 만듭니다. |
| `codex-status` | 로컬 Codex state와 hook/watch mode를 확인합니다. |
| `codex-finalize` | Codex thread 하나를 raw/context-packet/recovery artifact로 finalize합니다. |
| `codex-watch` | Codex rollout JSONL을 감시하고 idle thread를 한 번씩 처리합니다. |
| `search-knowledge` | durable knowledge/recovery/graph/raw source를 검색합니다. |
| `expand-hit` | retrieval hit id를 전체 local content로 확장합니다. |
| `lint-wiki` | Obsidian wiki와 packet artifact graph를 검사합니다. |
| `init-wiki` | human-facing wiki 폴더와 설정을 초기화합니다. |
| `install-plugin` | Hermes user plugin을 packaged asset에서 설치합니다. |
| `install-codex-plugin` | 비-MCP Codex plugin asset을 설치합니다. |
| `setup-codex` | Windows Codex 앱용 wiki/plugin/hook/diagnostic 설치를 한 번에 실행합니다. |
| `setup-codex-wizard` | 경로를 확인하며 Codex 설치를 진행하는 대화형 wizard입니다. |
| `doctor-codex` | Codex source, plugin, hook, wiki, artifact 경로를 점검합니다. |
| `diagnose-codex` | Codex 설치 문제와 복구 명령을 설명하고 `--fix`로 안전한 로컬 파일을 복구합니다. |
| `config-codex` | 설치된 Codex plugin `local_config.json`과 사용자-facing 경로를 확인/수정합니다. |
| `install-context-engine` | Hermes context engine을 packaged asset에서 설치합니다. |
| `doctor` | 설치 상태를 점검합니다. |
| `fresh-install-smoke` | 배포 경로를 end-to-end로 검사합니다. |

## Telegram에서 쓰는 명령

| 명령 | 용도 |
| --- | --- |
| `/harness` | plugin 상태, 경로, import 가능 여부 확인 |
| `/packet <session_id>` | 특정 세션을 수동으로 packet-only finalize |
| `/wiki-resume <session_id>` | 특정 세션의 recovery brief 확인 |
| `/wiki-lint` | wiki와 artifact lint 실행 |

## Hermes가 자동으로 검색하는 방식

`context.engine: agent_context_substrate`가 켜져 있으면 Hermes Agent는 작업 중 과거 지식이 필요할 때 read-only 검색 도구를 사용할 수 있습니다.

검색 순서:

1. Obsidian durable wiki pages
2. context packet JSON artifacts
3. packet 안의 unit/micro summaries
4. 필요할 때 raw Hermes `state.db` evidence
5. `codex-finalize` 이후 raw Codex export

노출 도구:

```text
wiki_recovery_context
wiki_knowledge_search
wiki_knowledge_expand
```

검색은 read-only입니다. 검색만으로 Obsidian 문서가 수정되지는 않습니다.

`build-topic-map`을 실행하면 wiki page, claim, promotion, wiki patch 사이의 연결을 `data/index/<report-id>.json`과 `.md`로 볼 수 있습니다.

## Obsidian Wiki 구조

권장 vault 구조:

```text
LLM Wiki/
  Home.md
  index.md
  SCHEMA.md
  log.md
  01 지식/
  02 내 아이디어/
  03 인물과 조직/
  04 프로젝트/
  05 계획/
  06 원천 자료/
  90 보관/
  _system/
```

active page는 `lang: ko` 또는 `lang: en`, provenance/source, type별 필수 섹션을 가져야 합니다. `lint-wiki`가 이를 검사합니다.

자동 보조 업데이트는 전체 페이지 rewrite보다 managed block을 권장합니다.

```md
<!-- acs:auto:claims:start -->
- 근거가 있는 claim `claim:<id>`
<!-- acs:auto:claims:end -->
```

중요한 canonical page는 patch proposal을 검토한 뒤에만 `--apply`하세요.

## v2 요약과 review-first wiki 성장

기본 `build-context-packet`은 기존 packet artifact만 만듭니다. v2 summary를 원할 때만 `--summary-mode`를 추가합니다.

```bash
agent-context-substrate build-context-packet \
  --session-id '<SESSION_ID>' \
  --packet-id '<PACKET_ID>' \
  --task-title '<task title>' \
  --macro-context '<macro context>' \
  --unit-title '<unit title>' \
  --goal '<goal>' \
  --summary-mode heuristic \
  --summary-cache on \
  --project-root '<PROJECT_ROOT>'
```

생성되는 추가 artifact:

```text
data/exports/evidence/<SESSION_ID>/<PACKET_ID>-micro-1.json
data/exports/summaries/<PACKET_ID>-micro-v2.json
data/exports/summaries/<PACKET_ID>-unit-v2.json
data/exports/evals/<PACKET_ID>-summary-judge.json   # --summary-judge-mode hybrid
data/cache/summaries/<cache_key>.json
```

Summary judge는 opt-in 평가 artifact입니다. Host integration이 Agent LLM router를 주입하면 recovery usefulness, hallucination risk, missing next steps, wiki-candidate noise를 평가합니다. summary를 수정하거나 wiki patch를 apply하지 않습니다.

wiki 반영은 아래처럼 제안부터 만듭니다.

```bash
agent-context-substrate extract-atoms --packet-id '<PACKET_ID>' --project-root '<PROJECT_ROOT>'
agent-context-substrate propose-promotions --packet-id '<PACKET_ID>' --project-root '<PROJECT_ROOT>'
agent-context-substrate plan-wiki-patches \
  --promotion-file '<PROJECT_ROOT>/data/promotions/<PACKET_ID>.json' \
  --wiki-root '<WIKI_ROOT>' \
  --project-root '<PROJECT_ROOT>'
```

검토 후 실제 반영할 때만 `apply-wiki-patch --apply`를 사용합니다.

참고: standalone CLI에서 바로 쓸 수 있는 모드는 `heuristic`, `custom-command`, `codex-cli`, `auto`입니다. `agent-llm`과 `hybrid`는 host integration이 Agent LLM router를 주입할 때 사용합니다. `auto`는 사용 가능한 Codex CLI가 있으면 `codex exec`를 read-only, `approval_policy=never`, `service_tier=fast`, low reasoning effort, hooks-disabled, inline bounded JSON input으로 호출하고, 실패하거나 JSON/lint 검증을 통과하지 못하면 heuristic summary로 fallback metadata를 남깁니다.

Codex 사용자는 ACS가 Codex OAuth token을 직접 읽거나 저장하지 않아도 LLM summary를 켤 수 있습니다.

```powershell
agent-context-substrate config-codex set --key summary_mode --value auto --project-root "<PROJECT_ROOT>"
```

| 선택지 | 사용 시점 | 주의점 |
| --- | --- | --- |
| `codex-cli` / `auto` | Codex CLI/App에 이미 로그인되어 있는 로컬 Codex 사용자 | subprocess 경로지만 ACS가 credential을 저장하지 않고 실패 시 heuristic으로 degrade |
| `custom-command` | 별도 local summarizer나 API wrapper를 이미 갖고 있을 때 | 인증, 비용, schema 출력, 안전장치는 command 작성자가 책임짐 |
| OpenAI Platform API key | CI나 Codex 밖 자동화에서 명시적 API 과금이 필요할 때 | 별도 key 발급과 사용량 비용이 필요 |
| 직접 Codex OAuth 구현 | 권장하지 않음 | token 저장/갱신/폐기/endpoint 안정성을 ACS가 떠안게 됨 |
| Codex Python SDK | app-server 기반 후속 실험 후보 | 이번 MVP는 sandbox/approval/JSONL/schema flag가 명확한 `codex exec`를 우선 사용 |

## 개인정보와 안전

이 프로젝트는 민감한 로컬 데이터를 다룹니다.

- `~/.hermes/state.db`에는 전체 대화, tool output, 파일 경로, 운영 메모가 들어갈 수 있습니다.
- Codex `%USERPROFILE%\.codex\state_5.sqlite`와 rollout JSONL에는 thread metadata, 메시지, tool call, 로컬 경로가 들어갈 수 있습니다.
- `data/exports/**/*.json`과 `data/exports/**/*.md`에는 raw transcript 또는 상세 요약이 포함될 수 있습니다.
- API key, token, password, `.env`, raw private session export는 commit하지 마세요.
- `.gitignore`는 `data/exports/`, ledger, cache, venv를 기본적으로 제외합니다.

## 더 읽기

- [English README](./README.md)
- [사용자 가이드](./docs/USER_GUIDE.md)
- [English User Guide](./docs/USER_GUIDE.en.md)
- [운영 가이드](./docs/OPERATIONS.md)
- [파이프라인 문서](./docs/PIPELINE.md)
- [릴리스 체크리스트](./docs/RELEASE_CHECKLIST.md)

## 현재 한계

- 현재 public alpha입니다. beta/stable 전까지 API, 문서, installer 동작이 바뀔 수 있습니다.
- atom은 현재 claim 중심으로 시작했습니다. decision/entity/concept/question atom은 후속 확장입니다.
- recovery brief 품질은 export된 recovery JSON의 `quality_gate` score/issue 목록으로 확인할 수 있습니다.
- semantic lint는 현재 promotion/wiki patch 구조 검사를 다룹니다. evidence 누락, target 누락, claim source, patch→candidate 무결성, applied patch log를 검사하며, 더 깊은 wiki health 검사는 후속 작업입니다.
- wiki patch apply는 의도적으로 좁고 managed block 중심입니다.
- legacy full promotion은 여전히 `queries/`, `concepts/`, `plans/`, `architectures/` 경로를 사용합니다.
- Hermes gateway는 plugin/context-engine 변경 뒤 재시작이 필요할 수 있습니다.
