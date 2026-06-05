# Agent Context Substrate 파이프라인 문서

이 문서는 `agent-context-substrate`의 실제 데이터 흐름, module 책임, artifact lifecycle을 정리한 참조 문서입니다.

핵심 변화:

> session-finalize의 기본값은 이제 `packet-only`입니다. Obsidian durable page promotion은 명시적으로 요청한 경우에만 수행합니다.

## 1. 전체 흐름

### 1.1 기본 session finalize (`packet-only`)

```text
Hermes state.db or Codex rollout JSONL
  -> SessionStore
  -> raw session bundle JSON
  -> MicroSummary
  -> UnitSummary
  -> ContextPacket
  -> ContextPacket JSON / Markdown export
  -> Wiki lint + internal artifact graph lint
  -> RecoveryBrief JSON + quality gate
  -> SessionLedger completed record
```

기본 실행은 Obsidian에 query/concept/plan/architecture page를 생성하지 않습니다.

### 1.2 선택 v2 summary + review-first wiki growth

`build-context-packet --summary-mode ...`를 사용하면 기존 packet artifact는 유지하면서 evidence-backed v2 summary artifact를 추가로 만듭니다.

```text
raw session bundle
  -> MicroEvidenceBundle
  -> SummarizerBackend
       ├── heuristic
       ├── agent-llm
       ├── hybrid
       ├── custom-command
       ├── codex-cli
       └── auto
  -> Summary lint / fallback
  -> MicroSummaryV2 / UnitSummaryV2
  -> optional SummaryJudge eval JSON (default off)
  -> ClaimAtom JSONL
  -> PromotionCandidate JSON/Markdown
  -> WikiPatchProposal JSON/Markdown
  -> dry-run review
  -> optional --apply guarded managed/flexible write
  -> optional --write-mode flexible page-revision proposal
```

핵심 정책:

- `heuristic`이 기본 안전 경로입니다.
- `agent-llm`과 `hybrid`는 host Agent의 LLM router를 재사용하는 opt-in 경로입니다.
- `codex-cli`는 `codex exec` subprocess를 read-only sandbox, `approval_policy=never`, `service_tier=fast`, `model_reasoning_effort=low`, `features.hooks=false`, inline bounded JSON input, JSONL output, `--output-schema`로 호출한 뒤 ACS schema/lint를 통과한 결과만 신뢰합니다.
- `auto`는 Codex CLI가 감지되면 `codex-cli`를 먼저 쓰고, unavailable/timeout/exit/error/invalid JSON/lint 실패 시 `heuristic`으로 fallback metadata를 남깁니다.
- ACS 내부 `codex exec` summary thread는 Codex SQLite/rollout에 남을 수 있으므로, discovery/watch/finalize 대상에서는 summary prompt prefix로 제외해 recursive ingestion을 막습니다.
- 직접 Codex OAuth 구현과 direct provider SDK는 core dependency가 아닙니다. Codex Python SDK는 app-server 기반 후속 실험 후보이고, 현재 MVP는 script-friendly한 `codex exec`를 사용합니다.
- `summary_judge.py` is a separate opt-in evaluator. It consumes mechanical lint, summaries, evidence, and recovery `quality_gate`, then writes `data/exports/evals/<packet_id>-summary-judge.json`. It does not rewrite summaries or apply wiki patches.
- `plan-wiki-patches --write-mode flexible` creates rubric-guided full-page draft/revision proposals instead of fixed section templates. Flexible proposals remain proposal-only unless metadata carries an approved semantic judge verdict; mechanical policy still checks safe target paths, evidence, and current page hashes.
- promotion candidate와 wiki patch proposal 생성은 Obsidian을 수정하지 않습니다.
- `apply-wiki-patch`도 기본은 dry-run이며, 실제 쓰기는 `--apply`가 있을 때만 합니다.
- alpha에서 기본 적용되는 wiki patch operation은 `create_page`, `insert_claim_block`, `append_managed_section`, `append_section`으로 제한합니다.
- `replace_page`는 `--write-mode flexible` proposal에서만 사용하며, apply 시 judge 승인 metadata와 현재 page hash preflight를 요구합니다.
- `add_link`, `mark_stale`는 proposal/실험 단계로 남기고 alpha 기본 apply에서는 skip합니다.

### 1.3 Legacy full promotion

```text
Hermes state.db or Codex rollout JSONL
  -> raw export
  -> context packet
  -> query / concept / plan / architecture pages
  -> index.md / log.md / backlink updates
  -> lint
  -> recovery
  -> ledger
```

이 흐름은 `promotion_mode="full"`을 명시했을 때만 사용합니다. temp-root smoke나 legacy behavior 검증에는 유용하지만, live human-facing Obsidian vault의 기본 운영에는 권장하지 않습니다.

### 1.4 Request-time retrieval

```text
wiki_knowledge_search(query, mode="knowledge")
  -> durable wiki markdown pages
  -> context packet JSON artifacts
  -> unit/micro summaries inside packet JSON
  -> topic map / promotion / wiki patch artifacts
  -> optional raw Hermes state.db messages

wiki_knowledge_search(query, mode="graph")
  -> topic map nodes / edges / paths
```

retrieval은 read-only입니다. 검색/확장만으로 Obsidian이 수정되지는 않습니다.


### 1.5 Distribution/install path

Package-managed installation is part of the pipeline surface now, not an external manual copy step.

```text
source package assets
  -> install-plugin
  -> ~/.hermes/plugins/agent-context-substrate
  -> setup-codex
  -> ~/.codex/plugins/agent-context-substrate
  -> install-context-engine
  -> <HERMES_AGENT_ROOT>/plugins/context_engine/agent_context_substrate
  -> doctor / doctor-codex / fresh-install-smoke
```

Hermes installers can write local `local_config.py` files containing the user's project/wiki roots. `setup-codex` writes `local_config.json` beside a non-MCP plugin skill and keeps `install-codex-plugin` available as the lower-level packaged asset install command. Public templates stay generic; local config carries machine-specific paths.

## 2. 단계별 구성

| 단계 | 모듈 | 입력 | 출력 | 핵심 책임 |
| --- | --- | --- | --- | --- |
| 0 | `paths.py` | 환경 변수 + `project_root` | `HarnessPaths` | `HERMES_HOME`, `WIKI_PATH`, `data/` 경로 해석 |
| 1 | `session_store.py` | `state.db`, `session_id` | session row + messages | raw Hermes 데이터 조회 |
| 1b | `codex_source.py` | `state_5.sqlite`, rollout JSONL, `thread_id` | `SessionBundle` | raw Codex source read-only 변환 |
| 2 | `raw_extract.py` | session + messages | bundle dict / JSON | 세션 단위 export |
| 3 | `summarizer.py` | raw bundle | `MicroSummary`, `UnitSummary`, v2 conversion helpers | request/outcome/key points/files 추출 |
| 4 | `context_packet.py` | unit + micro summaries | `ContextPacket`, JSON/MD | 재개 가능한 작업 packet 생성 |
| 5 | `evidence.py` | raw bundle | `MicroEvidenceBundle` JSON | bounded summarizer input + message id 보존 |
| 6 | `summarizer_backends.py` / `agent_llm_router.py` | evidence + routing hints | `MicroSummaryV2`, `UnitSummaryV2` | heuristic/agent-llm/hybrid/custom-command/codex-cli/auto backend |
| 7 | `summary_lint.py` | v2 summary + evidence | lint report object | evidence ids, empty summary, invented files 등 검증 |
| 8 | `atoms.py` | v2 summary | `data/atoms/claims.jsonl` | claim atom 추출 |
| 9 | `promotions.py` | claim atoms | `data/promotions/<packet_id>.json/.md` | wiki 반영 후보 제안 |
| 10 | `wiki_patches.py` | promotion candidates + wiki root | `data/wiki_patches/<packet_id>.json/.md` | dry-run patch proposal / guarded managed or flexible apply |
| 11 | `semantic_lint.py` | promotions + patch logs | semantic lint JSON/MD | promotion/wiki patch consistency 검사 |
| 12 | `topic_map.py` | wiki + substrate artifacts | `data/index/<report-id>.json/.md` | graph-style topic map 생성 |
| 13 | `integration.py` / `codex_integration.py` | session/thread id + policy | `IntegrationResult` | Hermes and Codex finalize orchestration |
| 14 | `promotion.py` | packet / unit summary | wiki Markdown pages | legacy page promotion + backlink |
| 15 | `lint.py` | wiki + packet exports | lint JSON/MD | wiki quality + internal graph 검증 |
| 16 | `recovery.py` | ledger + packet | recovery JSON + quality gate | 다음 세션용 compact brief와 재개 품질 검사 |
| 17 | `retrieval.py` | query + roots | retrieval hits/details | read-only knowledge/graph search |

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

### 3.5 v2 evidence and summaries

`MicroEvidenceBundle`은 LLM/custom command에 넘기기 전의 bounded input입니다.

주요 필드:

- `session_id`
- `micro_id`
- `message_ids`
- `user_messages`
- `assistant_messages`
- `heuristic_request`
- `heuristic_outcome`
- `files`
- `urls`
- `explicit_questions`

출력:

```text
data/exports/evidence/<session_id>/<micro_id>.json
```

`MicroSummaryV2`는 하나의 summary string을 세 목적별로 분리합니다.

- `recovery_summary`: 다음 세션 재개용
- `knowledge_summary`: 오래 남길 지식 후보
- `retrieval_summary`: 검색/index용
- `decisions`, `claims`, `action_items`: `EvidenceBackedText`로 message id 근거 포함
- `metadata`: mode, schema version, input hash, confidence, fallback info

`UnitSummaryV2`는 작업 단위의 상태, next actions, risk notes, wiki candidates를 분리합니다.

출력:

```text
data/exports/summaries/<packet_id>-micro-v2.json
data/exports/summaries/<packet_id>-unit-v2.json
data/cache/summaries/<cache_key>.json
```

### 3.6 Atoms, promotion candidates, wiki patches

Claim atom은 packet과 wiki 사이의 작은 지식 단위입니다.

```text
data/atoms/claims.jsonl
```

Promotion candidate는 “이 claim을 wiki에 반영할 가치가 있는가?”라는 검토 항목입니다.

```text
data/promotions/<packet_id>.json
data/promotions/<packet_id>.md
```

Wiki patch proposal은 실제 Obsidian 변경 전의 reviewable diff입니다.

```text
data/wiki_patches/<packet_id>.json
data/wiki_patches/<packet_id>.md
data/wiki_patches/applied.jsonl
```

현재 apply는 `create_page`와 `insert_claim_block` 중심이며, 기본은 dry-run입니다.

### 3.7 `RecoveryBrief`

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

### 3.8 `RetrievalHit` / `RetrievalHitDetail`

request-time retrieval 결과입니다.

주요 필드:

- `hit_id`
- `source_type`: `wiki`, `packet`, `unit_summary`, `micro_summary`, `topic_map_node`, `topic_map_edge`, `topic_map_path`, `promotion_candidate`, `wiki_patch`, `applied_patch`, `raw_message`
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
| Codex home | `CODEX_HOME` or `--codex-home` | `~/.codex` |
| Codex DB | derived | `~/.codex/state_5.sqlite` |
| Codex rollout JSONL | derived | `~/.codex/sessions/**/rollout-*.jsonl` |
| Wiki root | `WIKI_PATH` | `~/wiki` |
| Project data | `--project-root` | CLI current directory |

project root 아래에는 다음이 사용됩니다.

```text
data/atoms/
data/cache/
data/exports/
data/index/
data/promotions/
data/wiki_patches/
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
| `build-context-packet` | raw export + packet, optional v2 evidence/summaries | 아니오 |
| `extract-atoms` | v2 summary -> claim atoms | 아니오 |
| `propose-promotions` | claim atoms -> promotion candidates | 아니오 |
| `plan-wiki-patches` | promotion candidates -> patch proposals | 아니오 |
| `apply-wiki-patch` | patch proposal dry-run or guarded managed/flexible apply | 기본 아니오, `--apply`면 예 |
| `list-promotions` | promotion queue 조회 | 아니오 |
| `list-wiki-patches` | patch proposal/apply log 조회 | 아니오 |
| `lint-promotions` | promotion/wiki patch semantic lint | report만 project `data/lint`에 씀 |
| `build-topic-map` | graph report 생성 | report만 project `data/index`에 씀 |
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
| v2 evidence JSON | `data/exports/evidence/<session_id>/<micro_id>.json` | packet build with `--summary-mode` |
| v2 micro summary | `data/exports/summaries/<packet_id>-micro-v2.json` | packet build with `--summary-mode` |
| v2 unit summary | `data/exports/summaries/<packet_id>-unit-v2.json` | packet build with `--summary-mode` |
| summary cache | `data/cache/summaries/<cache_key>.json` | `--summary-cache on` |
| claim atoms | `data/atoms/claims.jsonl` | `extract-atoms` |
| promotion candidates | `data/promotions/<packet_id>.json/.md` | `propose-promotions` |
| wiki patch proposal | `data/wiki_patches/<packet_id>.json/.md` | `plan-wiki-patches` |
| applied patch log | `data/wiki_patches/applied.jsonl` | `apply-wiki-patch --apply` |
| topic map | `data/index/<report-id>.json/.md` | `build-topic-map` |
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

### Recovery brief level

- recovery brief는 `task_title`, `macro_context`, 마지막 work state(`decisions` 또는 `progress`), active context(`critical_files` 또는 `related_pages`), next step(`next_actions` 또는 `open_questions`), `provenance`를 quality gate로 검사한다.
- `quality_gate.ok`는 score가 0.8 이상이고 error issue가 없을 때만 true다.
- quality gate는 artifact에 기록되어 다음 세션에서 brief 신뢰도를 바로 볼 수 있게 한다.

Optional `summary_judge` treats the deterministic recovery `quality_gate` as input only. The LLM verdict is auxiliary and does not replace the deterministic gate.

### Semantic substrate level

- 모든 promotion candidate는 evidence ref와 review 가능한 target 상태를 가진다.
- 모든 wiki patch operation은 존재하는 promotion candidate를 가리킨다.
- applied 상태의 wiki patch operation은 `data/wiki_patches/applied.jsonl` record를 가진다.
- applied 상태의 promotion candidate는 대응 applied patch log를 가진다.

## 12. 확장 포인트

우선순위가 높은 후속 작업:

1. Atom layer 확장
   - 현재 claim 중심에서 decision/entity/concept/question JSONL까지 확장
2. Semantic lint 확장
   - structural MVP는 `claim_without_source`, `patch_without_candidate`, `applied_patch_missing_log`, `applied_promotion_without_applied_patch`, `promotion_backlog` 중심으로 유지
   - 단순 normalized-name `duplicate_concept` warning은 유지하되, `stale_claim`, `contradiction_unresolved` 같은 ontology/freshness 검사는 similarity 정책 이후 future로 보류
3. Wiki patch operation 확장
   - alpha 기본 apply는 `create_page`, `insert_claim_block`, `append_managed_section`, `append_section`에 고정
   - `replace_page`는 flexible proposal의 judge 승인 + 현재 page hash preflight가 있을 때만 적용
   - `add_link`, `mark_stale`는 실험/후속 opt-in 후보로 유지
   - `replace_section`, `merge_pages`, `split_page` 같은 broad edit은 review/rollback UX 이후 future로 보류
4. LLM safety hardening
   - JSON repair 1회, 입력 길이 제한 CLI, redaction 정책 CLI 옵션, 더 엄격한 summary lint
5. Language-aware template renderer
   - `ko/en` template 선택과 frontmatter 생성 자동화
6. Source card ingest
   - `06 원천 자료` source card와 processed `01 지식` page 연결
7. Context engine compression compatibility
   - recovery/retrieval뿐 아니라 compression path까지 안전 검증
