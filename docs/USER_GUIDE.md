# Agent Context Substrate 사용자 가이드

[English User Guide](./USER_GUIDE.en.md) · [한국어 README](../README.ko.md) · [English README](../README.md)

이 문서는 `agent-context-substrate`를 실제 사용자 관점에서 설명합니다. 핵심은 **무엇이 어디에 저장되는지**, **Obsidian과 어떻게 분리되는지**, **언어 설정을 어떻게 쓰는지**, **Hermes에서 어떻게 켜고 끄는지**입니다.

현재 릴리스에서 packaged integration은 **Hermes Agent 전용**입니다. 프로젝트 이름은 여러 agent adapter를 수용할 장기 방향을 반영하지만, Claude Code/Codex/OpenCode/Gemini adapter는 아직 포함되어 있지 않습니다. 이전 프로젝트 이름은 `hermes-llm-wiki-harness`입니다.

## 1. 무엇을 해주는가

`Agent Context Substrate`는 Hermes 대화 세션을 장기적으로 재사용 가능한 지식 substrate로 바꾸는 도구입니다.

현재 기본 session-finalize 정책은 `packet-only`입니다.

```text
Hermes state.db
  -> raw session export
  -> micro/unit summary
  -> context packet
  -> lint report
  -> recovery brief
  -> ledger
```

즉, 기본 자동 처리에서는 Obsidian에 query/concept/plan/architecture page를 만들지 않습니다. Obsidian LLM Wiki는 사람이 읽기 좋은 semantic wiki로 유지하고, agent용 packet/recovery/lint/raw transcript는 harness project의 `data/exports/`에 둡니다.

## 2. 저장 계층

| 계층 | 위치 | 형식 | 역할 |
| --- | --- | --- | --- |
| Hermes 원본 세션 DB | `HERMES_HOME/state.db` 또는 `~/.hermes/state.db` | SQLite | 원본 대화와 세션 메타데이터 |
| Harness exports | `data/exports/` | JSON/Markdown | raw export, context packet, lint report, recovery brief |
| Harness ledger | `data/index/session_ledger.json` | JSON | 처리 상태, artifact 경로, retry/idempotency 기록 |
| Obsidian LLM Wiki | `WIKI_PATH` | Markdown | 사람이 읽는 curated wiki |

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

### 5.3 언어별 template

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
3. 해당 template을 복사합니다.
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

## 6. Hermes 연동 설치와 활성화

Hermes 연동은 두 부분입니다.

1. `agent-context-substrate` user plugin: session finalize hook과 `/harness`, `/packet`, `/wiki-resume`, `/wiki-lint` 명령을 제공합니다.
2. `agent_context_substrate` context engine: `wiki_recovery_context`, `wiki_knowledge_search`, `wiki_knowledge_expand` 도구를 제공합니다.

아래 placeholder를 실제 경로로 바꿉니다.

| Placeholder | 의미 |
| --- | --- |
| `<PROJECT_ROOT>` | harness project/data root |
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

## 7. Plugin 설정

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT` | 사용자 harness project path | harness package와 `data/` 위치 |
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

## 8. Telegram 명령

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

## 9. Agent가 자동으로 검색하는 방식

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

## 10. CLI 직접 사용

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

## 11. 자동 처리되지 않는 것

현재 기본 정책에서 자동 처리되지 않는 대상:

- `source=gateway` session
- 메시지가 `min_message_count`보다 적은 session
- skip title pattern에 걸리는 session
- 이미 completed 처리됐고 필요한 artifact가 살아 있는 session
- Obsidian durable page promotion (`promotion_mode=packet-only`인 경우)

Obsidian이 수정되는 경로:

- legacy `promotion_mode="full"`
- `run-e2e-pipeline`
- `promote-*` CLI commands
- 사람이 직접 curated page를 작성/수정하는 경우

## 12. privacy / release 주의점

이 harness는 로컬 private data를 다룹니다.

- `HERMES_HOME/state.db`에는 전체 대화, tool output, 파일 경로, 운영 메모가 들어갈 수 있습니다.
- `data/exports/**/*.json`과 `data/exports/**/*.md`에는 raw transcript 또는 상세 요약이 포함될 수 있습니다.
- Obsidian page와 provenance도 개인 프로젝트/조직 정보를 포함할 수 있습니다.
- API key, token, password, connection string, `.env` 파일은 절대 commit하지 않습니다.
- public 배포 전에는 `git status --short`, `.gitignore`, `docs/RELEASE_CHECKLIST.md`, `doctor`, `fresh-install-smoke`를 확인합니다.

## 13. 안전장치

- ledger 기반 idempotency
- completed artifact 존재 확인
- stale completed record 재빌드
- failed record retry budget 관리
- retry exhausted 시 중단
- late failure 발생 시 partial artifact 경로 보존
- packet-only 기본값
- gateway source 기본 제외
- qualitative lint
- retrieval read-only 기본값

## 14. 빠른 문제 해결

| 증상 | 확인할 것 | 해결 방향 |
| --- | --- | --- |
| `/harness`가 `degraded` | project/wiki path, import error | 경로와 venv/plugin 설정 확인 |
| `/wiki-lint`에서 `Missing language` | page frontmatter | active page에 `lang: ko` 또는 `lang: en` 추가 |
| `/wiki-lint`에서 broken link | wikilink target | 존재하지 않는 링크 수정 또는 page 생성 |
| `/packet`이 `reused`만 표시 | ledger completed record | 정상일 수 있음. 다른 promotion mode면 재처리됨 |
| 새 설정이 Telegram에 안 보임 | gateway process cache | gateway 재시작 필요 가능성 |
| 자동 처리 안 됨 | source, message count, policy | `allowed_sources`, `min_message_count`, session source 확인 |

## 15. 일반 경로 예시

```text
Hermes DB:
~/.hermes/state.db

Harness project:
<PROJECT_ROOT>

Obsidian LLM Wiki:
<WIKI_ROOT>

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
