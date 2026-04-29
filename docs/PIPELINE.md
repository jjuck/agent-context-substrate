# Agent Context Substrate 파이프라인 문서

이 문서는 `agent-context-substrate`의 실제 데이터 흐름, module 책임, artifact lifecycle을 정리한 참조 문서입니다.

핵심 변화:

> session-finalize의 기본값은 이제 `packet-only`입니다. Obsidian durable page promotion은 명시적으로 요청한 경우에만 수행합니다.

## 1. 전체 흐름

### 1.1 기본 session finalize (`packet-only`)

```text
Hermes state.db
  -> SessionStore
  -> raw session bundle JSON
  -> MicroSummary
  -> UnitSummary
  -> ContextPacket
  -> ContextPacket JSON / Markdown export
  -> Wiki lint + internal artifact graph lint
  -> RecoveryBrief JSON
  -> SessionLedger completed record
```

기본 실행은 Obsidian에 query/concept/plan/architecture page를 생성하지 않습니다.

### 1.2 Legacy full promotion

```text
Hermes state.db
  -> raw export
  -> context packet
  -> query / concept / plan / architecture pages
  -> index.md / log.md / backlink updates
  -> lint
  -> recovery
  -> ledger
```

이 흐름은 `promotion_mode="full"`을 명시했을 때만 사용합니다. temp-root smoke나 legacy behavior 검증에는 유용하지만, live human-facing Obsidian vault의 기본 운영에는 권장하지 않습니다.

### 1.3 Request-time retrieval

```text
wiki_knowledge_search(query)
  -> durable wiki markdown pages
  -> context packet JSON artifacts
  -> unit/micro summaries inside packet JSON
  -> optional raw Hermes state.db messages
```

retrieval은 read-only입니다. 검색/확장만으로 Obsidian이 수정되지는 않습니다.

## 2. 단계별 구성

| 단계 | 모듈 | 입력 | 출력 | 핵심 책임 |
| --- | --- | --- | --- | --- |
| 0 | `paths.py` | 환경 변수 + `project_root` | `HarnessPaths` | `HERMES_HOME`, `WIKI_PATH`, `data/` 경로 해석 |
| 1 | `session_store.py` | `state.db`, `session_id` | session row + messages | raw Hermes 데이터 조회 |
| 2 | `raw_extract.py` | session + messages | bundle dict / JSON | 세션 단위 export |
| 3 | `summarizer.py` | raw bundle | `MicroSummary`, `UnitSummary` | request/outcome/key points/files 추출 |
| 4 | `context_packet.py` | unit + micro summaries | `ContextPacket`, JSON/MD | 재개 가능한 작업 packet 생성 |
| 5 | `integration.py` | session id + policy | `IntegrationResult` | packet-only/full finalize orchestration |
| 6 | `promotion.py` | packet / unit summary | wiki Markdown pages | legacy page promotion + backlink |
| 7 | `lint.py` | wiki + packet exports | lint JSON/MD | wiki quality + internal graph 검증 |
| 8 | `recovery.py` | ledger + packet | recovery JSON | 다음 세션용 compact brief |
| 9 | `retrieval.py` | query + roots | retrieval hits/details | read-only knowledge search |

## 3. 데이터 모델

### 3.1 `RawSessionReference`

raw 세션의 provenance pointer입니다.

주요 필드:

- `session_id`
- `message_ids`
- `source`
- `started_at`
- `ended_at`
- `title`

역할:

- summary/packet/recovery가 어떤 원본 세션 메시지에서 왔는지 추적
- recovery brief와 retrieval hit의 provenance 근거 제공

### 3.2 `MicroSummary`

대화 조각을 가장 작은 복구 단위로 압축한 결과입니다.

주요 필드:

- `micro_id`
- `session_id`
- `message_ids`
- `summary`
- `why_it_matters`
- `request`
- `outcome`
- `key_points`
- `follow_up_questions`
- `files`
- `entities`
- `concepts`
- `parent_unit_id`
- `provenance`

현재 요약은 LLM 호출이 아니라 heuristic 기반입니다.

### 3.3 `UnitSummary`

여러 micro summary를 작업 단위로 묶은 상위 요약입니다.

주요 필드:

- `unit_id`
- `session_id`
- `title`
- `goal`
- `decisions`
- `progress`
- `open_questions`
- `micro_ids`
- `related_pages`
- `provenance`

### 3.4 `ContextPacket`

다음 세션에서 빠르게 재개하기 위한 중간 산출물입니다.

주요 필드:

- `packet_id`
- `task_title`
- `macro_context`
- `unit_summaries`
- `micro_summaries`
- `raw_pointers`
- `critical_files`
- `open_questions`

출력:

```text
data/exports/context_packets/<packet_id>.json
data/exports/context_packets/<packet_id>.md
```

### 3.5 `RecoveryBrief`

agent나 `/wiki-resume`이 소비하는 compact recovery payload입니다.

주요 필드:

- `session_id`
- `packet_id`
- `task_title`
- `macro_context`
- `decisions`
- `critical_files`
- `open_questions`
- `related_pages`
- `provenance`
- `recovery_json_path`

출력:

```text
data/exports/recovery/<session_id>.json
```

### 3.6 `RetrievalHit` / `RetrievalHitDetail`

request-time retrieval 결과입니다.

주요 필드:

- `hit_id`
- `source_type`: `wiki`, `packet`, `unit_summary`, `micro_summary`, `raw_message`
- `source_path`
- `title`
- `snippet`
- `score`
- `provenance`

## 4. 경로와 설정

`HarnessPaths`가 해석하는 기본값:

| 항목 | 환경 변수 | 기본값 |
| --- | --- | --- |
| Hermes home | `HERMES_HOME` | `~/.hermes` |
| Hermes DB | derived | `HERMES_HOME/state.db` |
| Wiki root | `WIKI_PATH` | `~/wiki` |
| Project data | `--project-root` | CLI current directory |

project root 아래에는 다음이 사용됩니다.

```text
data/cache/
data/exports/
data/index/
```

## 5. Session finalize orchestration

### 5.1 `run_session_finalize_pipeline(...)`

```python
run_session_finalize_pipeline(
    session_id,
    project_root=Path(...),
    wiki_root=Path(...),
    promotion_mode="packet-only", # or "full"
)
```

동작:

1. ledger에서 기존 completed record 확인
2. promotion mode가 같고 artifact가 살아 있으면 reused result 반환
3. retry budget 초과 실패 record면 중단
4. raw export + packet build
5. `promotion_mode="full"`일 때만 legacy 4종 page promotion
6. lint export
7. base artifact path를 ledger에 기록
8. recovery brief export
9. recovery path까지 ledger에 다시 기록

### 5.2 지원 promotion mode

| Mode | 상태 | Obsidian write | 설명 |
| --- | --- | --- | --- |
| `packet-only` | 기본값 | 아니오 | raw/packet/lint/recovery/ledger만 생성 |
| `full` | legacy explicit | 예 | query/concept/plan/architecture 4종 page 생성 |

`draft`, `curated` 같은 모드는 정책 설계에는 있지만 현재 Python API에서는 아직 허용 mode가 아닙니다.

## 6. Legacy promotion layer

`promotion.py`의 현재 stable API:

- `promote_context_packet_to_query(...)` → `queries/<slug>.md`
- `promote_context_packet_to_plan(...)` → `plans/<slug>.md`
- `promote_unit_summary_to_concept(...)` → `concepts/<slug>.md`
- `promote_unit_summary_to_architecture(...)` → `architectures/<slug>.md`

공통 처리:

- YAML frontmatter
- `## Related Pages`
- `## Provenance`
- related page backlink 삽입
- target page `updated` 갱신
- CLI 사용 시 `index.md`, `log.md` 갱신

주의:

- 이 legacy layer는 old folder taxonomy(`queries`, `concepts`, `plans`, `architectures`)를 사용합니다.
- live Obsidian vault는 새 human-facing taxonomy(`01 지식`, `04 프로젝트` 등)를 사용하므로, 자동 full promotion은 기본값으로 쓰지 않습니다.

## 7. Lint layer

`lint.py`는 두 층을 검사합니다.

### 7.1 Durable wiki graph

- `missing_provenance_pages`
- `orphan_pages`
- `pages_missing_from_index`
- `broken_wikilinks`

### 7.2 Human-facing quality

- `numeric_slug_pages`
- `session_id_slug_pages`
- `generated_summary_only_pages`
- `multiline_frontmatter_title_pages`
- `transient_command_title_pages`
- `smoke_or_test_pages`
- `session_derived_plan_pages`
- `excessive_critical_files_pages`
- `missing_lang_pages`
- `unsupported_lang_pages`

### 7.3 Internal artifact graph

- `micro_summaries_missing_parent_unit`
- `micro_summaries_with_unknown_parent_unit`
- `unit_summaries_with_missing_micro_references`
- `packet_micro_summaries_unreferenced`
- `packets_missing_raw_pointers`

출력:

```text
data/exports/lint/<report_id>.json
data/exports/lint/<report_id>.md
```

## 8. 언어 설정과 lint

언어 설정은 Obsidian human-facing page 정책으로 적용됩니다.

```yaml
# <WIKI_PATH>/_system/config.yaml
wiki:
  default_language: ko
  supported_languages: [ko, en]
  filename_language: ko
  template_language: ko
  source_language_preserve: true
```

각 active page는 frontmatter에 `lang`을 가져야 합니다.

```yaml
---
title: Agent Context Substrate
lang: ko
type: project
category: project
status: active
---
```

`lint_wiki(...)`는 durable page에서 다음을 검출합니다.

- `missing_lang_pages`: `lang` 없음
- `unsupported_lang_pages`: `lang`이 `ko`, `en`이 아님

현재 retrieval은 `_system/`과 `90 보관/`을 기본 제외하므로 template/style/archive page가 검색 결과를 오염시키지 않습니다.

## 9. CLI와 파이프라인 대응

| CLI 명령 | 범위 | Obsidian write |
| --- | --- | --- |
| `extract-session` | raw export | 아니오 |
| `build-context-packet` | raw export + packet | 아니오 |
| `lint-wiki` | wiki + internal graph lint | report만 project `data/exports/lint`에 씀 |
| `promote-packet-query` | legacy query promotion | 예 |
| `promote-packet-plan` | legacy plan promotion | 예 |
| `promote-unit-concept` | legacy concept promotion | 예 |
| `promote-unit-architecture` | legacy architecture promotion | 예 |
| `run-e2e-pipeline` | raw + packet + legacy 4종 promotion + lint | 예 |

## 10. 대표 산출물 맵

| 산출물 | 경로 예시 | 생성 시점 |
| --- | --- | --- |
| raw export | `data/exports/<session_id>.json` | extract/packet/finalize/e2e |
| packet JSON | `data/exports/context_packets/<packet_id>.json` | packet/finalize/e2e |
| packet Markdown | `data/exports/context_packets/<packet_id>.md` | packet/finalize/e2e |
| lint JSON | `data/exports/lint/<report_id>.json` | lint/finalize/e2e |
| lint Markdown | `data/exports/lint/<report_id>.md` | lint/finalize/e2e |
| recovery JSON | `data/exports/recovery/<session_id>.json` | session finalize |
| ledger | `data/index/session_ledger.json` | session finalize |
| legacy query page | `WIKI_PATH/queries/<slug>.md` | explicit promotion/full/e2e |
| legacy concept page | `WIKI_PATH/concepts/<slug>.md` | explicit promotion/full/e2e |
| legacy plan page | `WIKI_PATH/plans/<slug>.md` | explicit promotion/full/e2e |
| legacy architecture page | `WIKI_PATH/architectures/<slug>.md` | explicit promotion/full/e2e |

## 11. 불변 조건

### Packet level

- 모든 `MicroSummary`는 적절한 `parent_unit_id`를 가진다.
- 모든 `UnitSummary.micro_ids`는 실제 micro summary를 가리킨다.
- 모든 `ContextPacket`은 `raw_pointers`를 가진다.
- `critical_files`는 관련 micro summary에서 파생된다.

### Wiki level

- active human-facing page에는 `lang: ko` 또는 `lang: en`이 있다.
- durable page는 provenance 근거를 가진다.
- broken wikilink가 없다.
- active page는 navigation/index에서 찾을 수 있다.
- generated/session-id/numeric page는 active human-facing graph에 두지 않는다.

## 12. 확장 포인트

우선순위가 높은 후속 작업:

1. Curated promotion target model
   - `01 지식`, `02 내 아이디어`, `04 프로젝트` 같은 human-facing folder에 template 기반 작성
2. Language-aware template renderer
   - `ko/en` template 선택과 frontmatter 생성 자동화
3. Source card ingest
   - `06 원천 자료` source card와 processed `01 지식` page 연결
4. Context engine compression compatibility
   - recovery/retrieval뿐 아니라 compression path까지 안전 검증
