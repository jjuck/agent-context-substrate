# Agent Context Substrate 사용자 가이드

[English User Guide](./USER_GUIDE.en.md) · [한국어 README](../README.ko.md) · [Windows Codex 앱 설치](./WINDOWS_CODEX_APP_SETUP.ko.md) · [English README](../README.md)

이 문서는 `agent-context-substrate`를 실제 사용자 관점에서 설명합니다. 핵심은 **무엇이 어디에 저장되는지**, **Obsidian과 어떻게 분리되는지**, **언어 설정을 어떻게 쓰는지**, **Hermes에서 어떻게 켜고 끄는지**입니다.

현재 릴리스에서 packaged integration은 **Hermes Agent**와 **비-MCP Codex 로컬 세션 source**를 포함합니다. Codex 경로는 `~/.codex/state_5.sqlite`와 `~/.codex/sessions/**/rollout-*.jsonl`을 read-only로 읽고, plugin Stop hook을 primary trigger로 사용하며 `codex-watch` fallback을 유지합니다. 이전 프로젝트 이름은 `hermes-llm-wiki-harness`입니다.

## 1. 무엇을 해주는가

`Agent Context Substrate`는 Hermes와 Codex 대화 세션을 장기적으로 재사용 가능한 지식 substrate로 바꾸는 도구입니다.

현재 기본 session-finalize 정책은 `packet-only`입니다.

```text
Hermes state.db 또는 Codex rollout JSONL
  -> raw session export
  -> micro/unit summary
  -> context packet
  -> lint report
  -> recovery brief
  -> ledger
```

즉, 기본 자동 처리에서는 Obsidian에 query/concept/plan/architecture page를 만들지 않습니다. Obsidian LLM Wiki는 사람이 읽기 좋은 semantic wiki로 유지하고, agent용 packet/recovery/lint/raw transcript는 Agent Context Substrate project의 `data/exports/`에 둡니다.

지식을 wiki로 키울 때도 바로 쓰지 않습니다. 먼저 evidence-backed summary, claim atom, promotion candidate, wiki patch proposal을 만든 뒤 사람이 검토하고 반영합니다.

## 2. 저장 계층

| 계층 | 위치 | 형식 | 역할 |
| --- | --- | --- | --- |
| Hermes 원본 세션 DB | `HERMES_HOME/state.db` 또는 `~/.hermes/state.db` | SQLite | 원본 대화와 세션 메타데이터 |
| Codex 로컬 세션 source | `~/.codex/state_5.sqlite`, `~/.codex/sessions/**/rollout-*.jsonl` | SQLite / JSONL | Codex thread metadata와 rollout event, read-only |
| Harness exports | `data/exports/` | JSON/Markdown | raw export, context packet, evidence, v2 summary, lint report, recovery brief |
| Harness atoms | `data/atoms/` | JSONL | packet에서 추출한 claim atom |
| Harness promotions | `data/promotions/` | JSON/Markdown | wiki 반영 후보 queue |
| Harness wiki patches | `data/wiki_patches/` | JSON/Markdown/JSONL | reviewable patch proposal과 apply log |
| Harness ledger/index | `data/index/` | JSON/Markdown | 처리 상태, topic map, artifact 경로, retry/idempotency 기록 |
| Obsidian LLM Wiki | `WIKI_PATH` | Markdown | 사람이 읽는 curated wiki |

Windows Codex 앱 사용자에게는 아래 실제 경로를 먼저 알려주는 것이 좋습니다.

```text
Codex 원본 SQLite:
%USERPROFILE%\.codex\state_5.sqlite

Codex rollout JSONL:
%USERPROFILE%\.codex\sessions\...\rollout-*.jsonl

권장 LLM Wiki:
%USERPROFILE%\Documents\LLM Wiki

ACS artifact:
<PROJECT_ROOT>\data\...
```

## 3. 기본 artifact

`packet-only` session finalize가 성공하면 보통 아래 artifact가 생깁니다.

```text
data/exports/<session_id>.json
data/exports/context_packets/<session_id>.json
data/exports/context_packets/<session_id>.md
data/exports/lint/<session_id>-lint.json
data/exports/lint/<session_id>-lint.md
data/exports/recovery/<session_id>.json
data/index/session_ledger.json

# --summary-mode 사용 시 추가
data/exports/evidence/<session_id>/<micro_id>.json
data/exports/summaries/<packet_id>-micro-v2.json
data/exports/summaries/<packet_id>-unit-v2.json

# review-first wiki growth 사용 시 추가
data/atoms/claims.jsonl
data/promotions/<packet_id>.json
data/promotions/<packet_id>.md
data/wiki_patches/<packet_id>.json
data/wiki_patches/<packet_id>.md
```

ledger에는 `promotion_mode`도 기록됩니다. 기존에 `full`로 처리한 세션이 있어도, 이후 `packet-only` 요청은 promotion mode가 다르므로 잘못 reuse하지 않습니다.

## 4. Obsidian human-facing wiki 구조

현재 사용자 vault 권장 구조는 다음과 같습니다.

```text
LLM Wiki/
  Home.md
  index.md              # harness lint compatibility catalog
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
    config.yaml
    templates/
      ko/
      en/
    styles/
      llm-wiki.css
```

폴더는 사람이 이해하기 쉬운 목적 기준으로 나누고, 기계 분류는 frontmatter로 보완합니다.

| Folder | 용도 |
| --- | --- |
| `01 지식/` | 처리된 지식, 개념, 비교, 패턴 |
| `02 내 아이디어/` | 사용자 발상, 설계 직관, 가설 |
| `03 인물과 조직/` | 사람, 회사, 연구소, 커뮤니티 |
| `04 프로젝트/` | 프로젝트 hub, SPEC, 사용설명서, 아키텍처, 다음 진행 |
| `05 계획/` | durable 계획과 roadmap |
| `06 원천 자료/` | article/repo/paper/docs/video source card |
| `90 보관/` | active graph에서 제외된 legacy/generated page |
| `_system/` | config, templates, CSS |

## 5. 언어 설정법

언어 설정은 Obsidian human-facing page의 생성/검증 정책입니다. 현재 지원 언어는 `ko`, `en`입니다.

### 5.1 Vault 기본 언어 설정

```yaml
# <WIKI_PATH>/_system/config.yaml
wiki:
  default_language: ko
  supported_languages: [ko, en]
  filename_language: ko
  template_language: ko
  source_language_preserve: true
```

| 필드 | 의미 |
| --- | --- |
| `default_language` | 새 human-facing page의 기본 언어 |
| `supported_languages` | lint가 허용하는 언어 코드 |
| `filename_language` | 새 파일명을 어떤 언어 관례로 만들지 |
| `template_language` | 기본 template 언어 |
| `source_language_preserve` | 원천 자료의 원문 언어를 보존할지 |

### 5.2 Page frontmatter

모든 active human-facing page는 `lang`을 가져야 합니다.

```yaml
---
title: Context Packet
lang: ko
type: knowledge
category: knowledge
status: active
tags: [context, hermes, recovery]
cssclasses: [knowledge-page]
---
```

영어 page 예시:

```yaml
---
title: Context Packet
lang: en
type: knowledge
category: knowledge
status: active
tags: [context, hermes, recovery]
cssclasses: [knowledge-page]
---
```

### 5.3 LLM Wiki rubric과 언어별 template

LLM Wiki는 고정 양식 생성기가 아니라 LLM이 유지보수하는 markdown 지식 그래프입니다. `_system/templates`는 사람과 agent가 참고하는 시작점이며, 실제 page 본문은 새 지식을 가장 잘 통합하는 구조를 자유롭게 사용할 수 있습니다.

자동화에서 끝까지 지키는 최소 계약은 page path 안전성, provenance/evidence, 유효한 wikilink, index/log 등록, review 상태, 불확실성/모순/open question 표시입니다. page type별 섹션명과 순서는 참고용 rubric으로만 취급합니다.

```text
_system/templates/ko/home.md
_system/templates/ko/knowledge.md
_system/templates/ko/project.md
_system/templates/en/home.md
_system/templates/en/knowledge.md
_system/templates/en/project.md
```

새 page를 만들 때:

1. page type을 고릅니다. (`knowledge`, `idea`, `source`, `project`, `spec`, `plan`, `decision` 등)
2. 언어를 고릅니다. (`ko` 또는 `en`)
3. 필요하면 해당 template을 시작점으로 복사합니다.
4. frontmatter의 `title`, `lang`, `type`, `category`, `status`, `tags`를 채웁니다.

### 5.4 언어 lint

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate
.venv/bin/agent-context-substrate lint-wiki \
  --project-root '<PROJECT_ROOT>' \
  --report-id language-check
```

문제가 있으면 report의 `Human-Facing Quality` 섹션에 다음 항목으로 표시됩니다.

- `Missing language`
- `Unsupported language`

언어와 섹션 구성 문제는 advisory로 보고됩니다. 자동화 gate를 막는 blocking issue는 provenance 누락, broken wikilink, index 누락, generated/session-id page, internal artifact graph 오류처럼 안전성과 graph 무결성에 직접 영향을 주는 항목입니다.

## 6. Hermes 연동 설치와 활성화

Hermes 연동은 두 부분입니다.

1. `agent-context-substrate` user plugin: session finalize hook과 `/harness`, `/packet`, `/wiki-resume`, `/wiki-lint` 명령을 제공합니다.
2. `agent_context_substrate` context engine: `wiki_recovery_context`, `wiki_knowledge_search`, `wiki_knowledge_expand` 도구를 제공합니다.

아래 placeholder를 실제 경로로 바꿉니다.

| Placeholder | 의미 |
| --- | --- |
| `<PROJECT_ROOT>` | Agent Context Substrate project/data root |
| `<WIKI_ROOT>` | Obsidian LLM Wiki vault root |
| `<HERMES_AGENT_ROOT>` | Hermes Agent root, 예: `~/.hermes/hermes-agent` |

### 6.1 packaged installer 실행

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate

.venv/bin/agent-context-substrate init-wiki \
  --wiki-root '<WIKI_ROOT>'

.venv/bin/agent-context-substrate install-plugin \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

.venv/bin/agent-context-substrate install-context-engine \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

.venv/bin/agent-context-substrate doctor \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --fail-on-issues
```

`install-plugin`은 `~/.hermes/plugins/agent-context-substrate/local_config.py`에 `<PROJECT_ROOT>`와 `<WIKI_ROOT>`를 기록합니다. 이 파일은 사용자별 local 설정이므로 public template의 hardcoded 경로와 분리됩니다.

### 6.2 plugin 활성화

```bash
cd '<HERMES_AGENT_ROOT>'
. venv/bin/activate
hermes plugins enable agent-context-substrate
```

활성화되면 `~/.hermes/config.yaml`에 대략 다음 설정이 들어갑니다.

```yaml
plugins:
  enabled:
    - agent-context-substrate
```

### 6.3 context engine 활성화

```yaml
context:
  engine: agent_context_substrate
```

이 설정이 있어야 Hermes agent가 아래 도구를 사용할 수 있습니다.

```text
wiki_recovery_context
wiki_knowledge_search
wiki_knowledge_expand
```

### 6.4 gateway 재시작

Telegram gateway가 이미 실행 중이면 plugin/config 변경을 바로 반영하지 못할 수 있습니다.

```text
/restart
```

진행 중인 긴 작업이 있으면 재시작 타이밍을 주의하세요.

## 7. Codex 연동 설치와 활성화

Codex 연동의 기본 전략은 hook-primary, watcher fallback입니다. packaged plugin은 manifest `hooks`를 쓰지 않고 `hooks/hooks.json`에 Stop hook을 포함합니다. Codex `/hooks` review로 hook을 trust하면 Stop hook이 thread를 finalize하고, hook이 trust되지 않았거나 Stop event를 놓친 경우 `codex-watch`가 fallback으로 동작합니다. 두 경로 모두 Codex 원본 파일을 read-only로 읽고 ACS artifact만 `<PROJECT_ROOT>/data/` 아래에 기록합니다.

Windows Codex 앱 사용자는 [Windows 상세 가이드](./WINDOWS_CODEX_APP_SETUP.ko.md)를 우선 보세요. 배포용 PowerShell 설치 흐름은 단일 bootstrap script를 기준으로 합니다.

```powershell
git clone https://github.com/jjuck/agent-context-substrate.git agent-context-substrate
cd agent-context-substrate
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
```

누락 도구까지 선택 설치하려면 `Python.Python.3.13`, `Git.Git`, `Obsidian.Obsidian` winget ID를 사용합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1 -InstallMissingTools -InstallObsidian
```

설치 후에는 아래 명령으로 상태와 경로를 확인합니다.

```powershell
.\.venv\Scripts\agent-context-substrate.exe doctor-codex --fail-on-issues
.\.venv\Scripts\agent-context-substrate.exe config-codex paths
.\.venv\Scripts\agent-context-substrate.exe diagnose-codex
```

경로를 확인하며 설치하려면 `setup-codex-wizard`를 사용합니다. `diagnose-codex --fix`는 wiki skeleton, Codex plugin Stop hook, local config처럼 안전한 ACS 로컬 파일만 복구합니다. `~/.codex/hooks.json` user hook fallback은 중복 Stop hook을 피하기 위해 명시적으로 요청한 경우에만 사용합니다.

Codex의 non-managed hook 정책상 실제 실행 전 `/hooks` review/trust는 여전히 필요합니다.

Hook 승인 확인 뒤 fallback dry run도 실행할 수 있습니다.

```powershell
.\.venv\Scripts\agent-context-substrate.exe codex-watch `
  --once `
  --codex-home $CodexHome `
  --project-root $ProjectRoot `
  --wiki-root $WikiRoot `
  --idle-seconds 999999
```

특정 thread를 수동으로 finalize할 수도 있습니다.

```powershell
.\.venv\Scripts\agent-context-substrate.exe codex-finalize `
  --thread-id "<CODEX_THREAD_ID>" `
  --codex-home $CodexHome `
  --project-root $ProjectRoot `
  --wiki-root $WikiRoot `
  --summary-mode auto
```

Codex raw export는 `data/exports/raw/codex/<thread_id>.json`에 저장됩니다. 이후 context packet, recovery, retrieval, atoms, promotions, wiki patch 명령은 Hermes session artifact와 같은 layout을 사용합니다.

`summary_mode=auto`는 ACS가 Codex credential을 직접 다루지 않으면서 LLM summary를 쓰고 싶을 때 권장하는 Codex UX입니다. 사용 가능한 Codex CLI를 감지한 뒤 `codex exec`를 read-only sandbox, `approval_policy=never`, `service_tier=fast`, low reasoning effort, `features.hooks=false`, inline bounded JSON input으로 실행하고 strict JSON을 ACS schema/lint로 검증합니다. timeout, CLI 실패, invalid JSON, lint 실패 시 heuristic summary로 degrade하고 summary metadata와 finalize ledger에 `fallback_from` / `fallback_reason`을 남깁니다.

| 선택지 | 사용 시점 | 주의점 |
| --- | --- | --- |
| `codex-cli` / `auto` | 로컬 Codex CLI/App에 이미 로그인되어 있을 때 | Codex CLI 인증을 재사용하며 ACS가 Codex OAuth token을 읽거나 저장하지 않습니다. |
| `custom-command` | 신뢰하는 local summarizer command가 있을 때 | command가 인증, API 사용량, schema 출력, 안전장치를 책임집니다. |
| OpenAI Platform API key | CI나 Codex 밖 자동화에서 명시적 API 과금이 필요할 때 | Codex 로그인과 별개로 key 발급과 API 비용이 필요합니다. |
| 직접 Codex OAuth 구현 | ACS에서는 피합니다. | token lifecycle과 private endpoint 안정성을 ACS가 책임지게 됩니다. |
| Codex Python SDK | app-server 기반 후속 실험 후보 | 이번 backend는 자동화 flag가 명확한 `codex exec`를 먼저 사용합니다. |

## 8. Plugin 설정

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT` | 사용자 project path | Agent Context Substrate package와 `data/` 위치 |
| `AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT` | 사용자 LLM Wiki vault path | Obsidian wiki root |
| `AGENT_CONTEXT_SUBSTRATE_AUTO_FINALIZE` | `true` | session finalize 자동 처리 |
| `AGENT_CONTEXT_SUBSTRATE_MIN_MESSAGE_COUNT` | `3` | 너무 짧은 session 제외 |
| `AGENT_CONTEXT_SUBSTRATE_ALLOWED_SOURCES` | `telegram,cli` | 자동 처리할 raw session source |
| `AGENT_CONTEXT_SUBSTRATE_GATEWAY_POLICY` | `trigger-only` | gateway source를 durable 대상에서 보수적으로 제외 |
| `AGENT_CONTEXT_SUBSTRATE_PROMOTION_MODE` | `packet-only` | `packet-only` 또는 legacy `full` |
| `AGENT_CONTEXT_SUBSTRATE_SKIP_TITLE_PATTERNS` | empty | 자동 처리 제외 title pattern |

권장 기본값:

```text
AGENT_CONTEXT_SUBSTRATE_PROMOTION_MODE=packet-only
AGENT_CONTEXT_SUBSTRATE_ALLOWED_SOURCES=telegram,cli
AGENT_CONTEXT_SUBSTRATE_GATEWAY_POLICY=trigger-only
```

## 9. Telegram 명령

### `/harness`

상태 확인:

```text
/harness
```

정상 예시:

```text
Agent Context Substrate plugin status
- health: ok
- project_root exists: True
- wiki_root exists: True
- harness_importable: True
- auto_finalize_enabled: True
- min_message_count: 3
- allowed_sources: telegram, cli
- promotion_mode: packet-only
- gateway_policy: trigger-only
- gateway source auto-finalize: disabled
```

### `/packet <session_id>`

특정 session을 수동 finalize합니다. 기본 설정이면 `packet-only`로 처리합니다.

```text
/packet 20260424_122938_c308ad
```

### `/wiki-resume <session_id>`

특정 session의 recovery brief를 확인합니다.

```text
/wiki-resume 20260424_122938_c308ad
```

### `/wiki-lint`

Obsidian human-facing wiki와 packet artifact graph를 검사합니다.

```text
/wiki-lint
```

## 10. Agent가 자동으로 검색하는 방식

`context.engine: agent_context_substrate`가 활성화되어 있으면 Hermes agent는 이전 지식이 필요할 때 read-only retrieval을 사용할 수 있습니다.

검색 순서:

1. Obsidian durable wiki pages
2. context packet JSON artifacts
3. unit/micro summary fields
4. 필요할 때 raw Hermes `state.db` evidence

검색에서 기본 제외되는 경로:

- `.obsidian/`
- `_system/`
- `90 보관/`

즉 `_system/templates`나 archive page는 일반 검색 결과를 오염시키지 않습니다.

## 11. CLI 직접 사용

### raw export

```bash
agent-context-substrate extract-session \
  --session-id <session_id> \
  --project-root .
```

### context packet

```bash
agent-context-substrate build-context-packet \
  --session-id <session_id> \
  --packet-id <packet_id> \
  --task-title "<task title>" \
  --macro-context "<macro context>" \
  --unit-title "<unit title>" \
  --goal "<goal>" \
  --project-root .
```

### wiki lint

```bash
export WIKI_PATH='<WIKI_ROOT>'

agent-context-substrate lint-wiki \
  --project-root . \
  --report-id wiki-lint
```

### v2 summary artifact 만들기

기본 `build-context-packet`은 기존 packet artifact만 만듭니다. 아래처럼 `--summary-mode`를 추가하면 evidence bundle과 v2 summary artifact도 생성합니다.

```bash
agent-context-substrate build-context-packet \
  --session-id <session_id> \
  --packet-id <packet_id> \
  --task-title "<task title>" \
  --macro-context "<macro context>" \
  --unit-title "<unit title>" \
  --goal "<goal>" \
  --summary-mode heuristic \
  --summary-cache on \
  --project-root .
```

요약 모드:

| 모드 | 의미 |
| --- | --- |
| `heuristic` | 기본 오프라인 요약. 비용/키/네트워크 없음. |
| `agent-llm` | host Agent가 제공하는 LLM router를 사용합니다. |
| `hybrid` | heuristic evidence + Agent LLM 해석을 조합합니다. |
| `custom-command` | 외부 command가 stdin JSON을 받아 stdout JSON을 반환합니다. |
| `codex-cli` | `codex exec`를 read-only sandbox, `approval_policy=never`, `service_tier=fast`, low reasoning effort, hooks-disabled, inline bounded JSON input, JSONL 출력, ACS schema/lint 검증으로 호출합니다. |
| `auto` | 사용 가능한 Codex CLI가 있으면 `codex-cli`를 우선 사용하고, 없으면 heuristic fallback metadata를 기록합니다. |

참고: standalone CLI에서 바로 쓸 수 있는 모드는 `heuristic`, `custom-command`, `codex-cli`, `auto`입니다. `agent-llm`과 `hybrid`는 host integration이 Agent LLM router를 주입할 때 사용합니다.

Summary judge evaluation is opt-in and artifact-only:

```bash
agent-context-substrate build-context-packet \
  --summary-mode heuristic \
  --summary-judge-mode hybrid \
  --project-root .
```

Host integration이 Agent LLM router를 주입하면 `hybrid` judge는 recovery usefulness, hallucination risk, missing next steps, wiki-candidate noise를 평가하고 `data/exports/evals/<packet_id>-summary-judge.json`만 씁니다. summary를 수정하거나 wiki patch를 apply하지 않습니다.

### review-first wiki growth

```bash
agent-context-substrate extract-atoms --packet-id <packet_id> --project-root .
agent-context-substrate propose-promotions --packet-id <packet_id> --project-root .
agent-context-substrate plan-wiki-patches \
  --promotion-file data/promotions/<packet_id>.json \
  --wiki-root '<WIKI_ROOT>' \
  --project-root .
```

기본 `plan-wiki-patches`는 기존 managed claim block proposal을 유지합니다. 고정 섹션 템플릿 대신 rubric 기반 전체 page draft/revision을 만들고 싶으면 명시적으로 flexible mode를 사용합니다.

```bash
agent-context-substrate plan-wiki-patches \
  --promotion-file data/promotions/<packet_id>.json \
  --write-mode flexible \
  --wiki-root '<WIKI_ROOT>' \
  --project-root .
```

Flexible proposal은 semantic judge 승인 metadata가 없으면 proposal-only로 남습니다. 실제 apply 단계에서도 safe target path, evidence, 현재 page hash, `--apply` 여부를 기계적으로 다시 확인합니다.

여기까지는 Obsidian을 수정하지 않습니다. 실제 쓰기는 patch Markdown/JSON을 검토한 뒤 아래처럼 명시합니다.

```bash
agent-context-substrate apply-wiki-patch \
  --patch-file data/wiki_patches/<packet_id>.json \
  --wiki-root '<WIKI_ROOT>' \
  --project-root . \
  --apply
```

## 12. 자동 처리되지 않는 것

현재 기본 정책에서 자동 처리되지 않는 대상:

- `source=gateway` session
- 메시지가 `min_message_count`보다 적은 session
- skip title pattern에 걸리는 session
- 이미 completed 처리됐고 필요한 artifact가 살아 있는 session
- Obsidian durable page promotion (`promotion_mode=packet-only`인 경우)
- v2 summary/atoms/promotions/wiki patches. 이들은 CLI로 명시적으로 실행합니다.

Obsidian이 수정되는 경로:

- legacy `promotion_mode="full"`
- `run-e2e-pipeline`
- `promote-*` CLI commands
- `apply-wiki-patch --apply`
- 사람이 직접 curated page를 작성/수정하는 경우

## 13. privacy / release 주의점

이 harness는 로컬 private data를 다룹니다.

- `HERMES_HOME/state.db`에는 전체 대화, tool output, 파일 경로, 운영 메모가 들어갈 수 있습니다.
- Codex `%USERPROFILE%\.codex\state_5.sqlite`와 rollout JSONL에는 thread metadata, 메시지, tool call, 로컬 경로가 들어갈 수 있습니다.
- `data/exports/**/*.json`과 `data/exports/**/*.md`에는 raw transcript 또는 상세 요약이 포함될 수 있습니다.
- Obsidian page와 provenance도 개인 프로젝트/조직 정보를 포함할 수 있습니다.
- API key, token, password, connection string, `.env` 파일은 절대 commit하지 않습니다.
- public 배포 전에는 `git status --short`, `.gitignore`, `docs/RELEASE_CHECKLIST.md`, `doctor`, `fresh-install-smoke`를 확인합니다.

## 14. 안전장치

- ledger 기반 idempotency
- completed artifact 존재 확인
- stale completed record 재빌드
- failed record retry budget 관리
- retry exhausted 시 중단
- late failure 발생 시 partial artifact 경로 보존
- packet-only 기본값
- gateway source 기본 제외
- qualitative lint
- summary lint와 fallback
- promotion/wiki patch semantic lint
- retrieval read-only 기본값
- wiki patch dry-run 기본값

## 15. 빠른 문제 해결

| 증상 | 확인할 것 | 해결 방향 |
| --- | --- | --- |
| `/harness`가 `degraded` | project/wiki path, import error | 경로와 venv/plugin 설정 확인 |
| `/wiki-lint`에서 `Missing language` | page frontmatter | active page에 `lang: ko` 또는 `lang: en` 추가 |
| `/wiki-lint`에서 broken link | wikilink target | 존재하지 않는 링크 수정 또는 page 생성 |
| `/packet`이 `reused`만 표시 | ledger completed record | 정상일 수 있음. 다른 promotion mode면 재처리됨 |
| 새 설정이 Telegram에 안 보임 | gateway process cache | gateway 재시작 필요 가능성 |
| 자동 처리 안 됨 | source, message count, policy | `allowed_sources`, `min_message_count`, session source 확인 |

## 16. 일반 경로 예시

```text
Hermes DB:
~/.hermes/state.db

Codex source:
%USERPROFILE%\.codex\state_5.sqlite
%USERPROFILE%\.codex\sessions\...\rollout-*.jsonl

Harness project:
<PROJECT_ROOT>

Obsidian LLM Wiki:
%USERPROFILE%\Documents\LLM Wiki 또는 <WIKI_ROOT>

권장 promotion mode:
packet-only

자동 처리 source:
telegram, cli

gateway policy:
trigger-only
```

WSL에서 이 프로젝트 경로는 Windows mount와 한글 사용자명을 포함하므로, terminal command는 `workdir` 대신 명령 내부 `cd`를 사용하세요.

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest -q
```
