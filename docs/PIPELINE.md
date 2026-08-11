# Agent Context Substrate Pipeline

이 문서는 ACS의 현재 런타임 아키텍처와 불변 조건을 설명하는 canonical reference입니다. 설치 절차는 `WINDOWS_CODEX_APP_SETUP*.md`, 사용자 명령은 `USER_GUIDE*.md`, 장애 대응은 `OPERATIONS.md`를 참고하세요.

## 1. Architecture At A Glance

```text
Hermes state.db -----------------------------------------------+
                                                               |
Codex Stop event                                               |
  -> durable SQLite job                                        |
  -> singleton drain worker                                    |
  -> fingerprint guard + global lock                           |
  -> state_5.sqlite + rollout JSONL ----------------------------+
                                                               |
                                                        source adapters
                                                               |
                                                        typed SessionBundle
                              |
                  build_finalize_artifacts(...)
                     /                    \
        ContextPacket V1              optional Summary V2
                                             |
                                atoms -> promotion candidates
                                             |
                                      WikiPageIntent
                                             |
                                   placement + patch plan
                                             |
                                      write-judge LLM
                                             |
                                  WikiApplyTransaction
                                             |
                           page + index/MOC + log + status
                                             |
                              lint + recovery + session ledger
```

핵심 경계는 `SessionBundle`입니다. Hermes와 Codex adapter는 원본 형식의 차이를 이 경계에서 끝내고, packet 및 summary artifact 생성은 공통 application service를 사용합니다.

## 2. Runtime Modes

### 2.1 Hermes And Standalone

`run_session_finalize_pipeline(...)`의 기본 promotion mode는 `packet-only`입니다.

```text
raw export
  -> ContextPacket JSON/Markdown
  -> lint report
  -> RecoveryBrief
  -> SessionLedger
```

`summary_mode`를 지정하면 evidence-backed V2 summary가 추가됩니다. legacy `promotion_mode=full`만 기존 `queries/`, `concepts/`, `plans/`, `architectures/` 페이지를 만듭니다.

### 2.2 Codex Stop Finalize

새 Codex 설치 기본값:

```text
trigger_strategy=hook-enqueue
summary_mode=auto
wiki_auto_mode=apply-flexible
wiki_write_judge_mode=auto
wiki_auto_min_score=0.85
workspace_scope=all
```

Stop hook은 현재 thread의 rollout fingerprint와 config digest를 SQLite queue에 commit하고 opportunistic singleton worker를 시작한 뒤 빠르게 반환합니다. Worker가 Codex CLI summary와 promotion 후보를 만든 뒤 write judge가 wiki 반영 여부와 정확한 candidate ID 집합을 결정하게 합니다. 선택되지 않은 candidate는 `pending` 상태를 유지합니다.

Judge 실패, 낮은 점수, 빈 선택 집합, unsafe target, stale page hash는 vault write로 이어지지 않습니다. proposal, decision, lint, ledger artifact는 사후 분석을 위해 남습니다.

### 2.3 Hook Queue, Worker, And Watcher

Codex integration의 기본은 `hook-enqueue`이고, watcher는 명시적인 history recovery/backfill 경로입니다.

- 설치 hook script는 import path와 stdin payload만 준비하는 얇은 bootstrap입니다.
- workspace 정책, wiki-root resolution, job snapshot, event log는 core `codex_hook.py`가 소유합니다.
- Hook은 새 Stop event만 `data/index/codex_jobs.sqlite3`에 durable enqueue하고 full finalize 완료를 기다리지 않습니다.
- Queue는 thread별 latest-wins coalescing, transactional lease, retry backoff, dead-letter 상태를 가집니다.
- Opportunistic worker는 singleton drain loop로 실행되며 queue가 비면 종료합니다. Worker crash 뒤에는 expired lease를 다음 worker가 reclaim합니다.
- Finalize/wiki global process lock은 hook worker, manual finalize, watcher가 동시에 mutation boundary에 진입하지 못하게 합니다.
- Finalize lock 경합은 attempt budget을 소모하지 않는 deferred retry이며, `worker_lock_contention_retry_seconds`가 재시도 간격을 제어합니다.
- Session ledger read-modify-write는 전용 process lock과 atomic replace를 사용합니다. Codex와 Hermes의 wiki mutation은 project-local lock에 더해 wiki-root 기반 shared vault lock을 사용해 adapter와 project 경계를 넘어 직렬화됩니다.
- Captured rollout fingerprint를 처리 전과 wiki write 직전에 재검증합니다. 변경된 generation은 stale apply를 하지 않고 최신 generation을 enqueue합니다.
- plugin hook이 신뢰되지 않았거나 Stop event를 놓친 경우 `codex-watch`가 같은 finalize pipeline을 명시적으로 실행할 수 있습니다. Watcher는 rollout history를 scan하므로 자동 worker나 migration backfill로 사용하지 않습니다.
- plugin hook과 user-level `hooks.json` fallback을 기본으로 동시에 켜지 않습니다.

## 3. Domain Boundaries

| Boundary | Main modules | Responsibility |
| --- | --- | --- |
| Source adapters | `session_store.py`, `raw_extract.py`, `codex_source.py` | 원본 session을 읽기 전용으로 읽고 `SessionBundle` 생성 |
| Finalize application service | `finalize_artifacts.py` | source-neutral packet, title/goal, optional V2 summary 생성 |
| LLM execution | `llm_runtime.py`, `codex_cli.py`, `codex_exec.py` | input safety, CLI discovery, isolated execution, strict JSON/JSONL parsing |
| Summary domain | `evidence.py`, `summarizer_backends.py`, `summary_pipeline.py`, `summary_lint.py` | evidence bundle, backend fallback, schema/lint 검증 |
| Knowledge intent | `atoms.py`, `wiki_intent.py`, `promotions.py` | claim을 promotion candidate와 soft page intent로 변환 |
| Wiki planning | `wiki_config.py`, `wiki_placement.py`, `wiki_patches.py` | placement policy, target grouping, managed/flexible patch 계획 |
| Write decision | `wiki_write_judge.py` | semantic apply/propose/review/skip 판단과 candidate selection |
| Write transaction | `wiki_apply_transaction.py`, `artifact_pipeline.py`, `wiki_registration.py` | page와 bookkeeping artifact의 원자적 적용 및 복구 |
| Quality and retrieval | `lint.py`, `semantic_lint.py`, `retrieval*.py`, `topic_map.py` | graph integrity, advisory quality, read-only search/expand |
| Durable jobs and locks | `codex_jobs.py`, `process_lock.py` | SQLite enqueue/lease/retry/dead-letter와 process 간 serialization |
| Orchestration | `integration.py`, `codex_integration.py`, `codex_hook.py` | host policy, ledger, recovery, hook/worker/watch entry points |

모듈 간 순환 의존은 허용하지 않습니다. 새 adapter는 source 경계에서 `SessionBundle`을 만들고 공통 finalize service를 호출해야 합니다.

## 4. Wiki Model

### 4.1 Emergent Root Placement

새 vault의 기본 config는 최소 정책만 가집니다.

```yaml
wiki:
  default_language: ko
  supported_languages: [ko, en]
  filename_language: ko
  template_language: ko
  source_language_preserve: true
  placement_policy: emergent-root
```

자동 flexible write의 기본 target은 `<Title>.md`입니다. 고정 category folder registry는 만들지 않습니다.

- `category`가 있으면 frontmatter와 index/MOC grouping에 보존합니다.
- `category`가 없으면 `Unclassified / Review Needed` index section에 등록합니다.
- `type`이 없으면 `knowledge`를 사용합니다.
- claim 언어를 안정적으로 추론할 수 있으면 candidate가 `language`를 제안합니다. 그 외에는 vault default를 사용합니다.
- `category`와 `type`은 열린 vocabulary이며 permission enum이 아닙니다.
- explicit safe Markdown target은 계속 존중합니다.

`placement_policy: registry-folder`와 `category_registry`는 기존 vault의 opt-in compatibility mode입니다. 이 모드에서 미등록 category는 fallback folder로 갈 수 있지만 write 자체를 차단하지 않습니다.

### 4.2 WikiPageIntent

`WikiPageIntent`는 target title, optional category, language, page type, placement reason을 묶는 soft value object입니다. 물리 경로를 결정하지 않으며 `resolve_wiki_placement(...)`가 vault policy와 결합해 최종 target을 계산합니다.

Generic subject만 있는 claim은 `context-packet.md` 같은 인공적인 canonical page를 강제하지 않고 review candidate로 남습니다.

### 4.3 Flexible Rendering

같은 최종 `resolved_target_path`를 가진 candidate만 하나의 operation으로 병합됩니다. category나 fallback 여부가 같다는 이유만으로 다른 title을 합치지 않습니다.

새 flexible page는 다음 최소 정보를 포함합니다.

```yaml
---
title: <semantic title>
lang: <candidate or vault language>
type: <candidate type or knowledge>
status: seed
review_needed: true
sources: [<deduplicated evidence references>]
---
```

본문에는 중복 제거 claim과 Sources and Evidence section이 들어갑니다. 실제 durable page가 존재할 때만 related wikilink를 추가합니다.

## 5. Judge And Mechanical Gates

Write judge는 semantic 판단을 담당하고 mechanical policy를 대체하지 않습니다.

Semantic decision:

- `apply_flexible`
- `apply_managed`
- `propose_only`
- `review_required`
- `skip`

Mechanical apply gate:

1. proposal과 operation schema가 유효하다.
2. operation에 evidence가 있다.
3. judge가 승인한 candidate ID만 포함한다.
4. target이 wiki root 밖으로 탈출하지 않는다.
5. replace operation의 base hash가 현재 page와 일치한다.
6. write mode와 operation type이 허용된다.

수동 `apply-wiki-patch`는 기본 dry-run입니다. `--apply`를 명시해도 위 조건을 우회하지 않습니다.

## 6. Atomic Wiki Apply

Non-dry-run apply는 `WikiApplyTransaction` 안에서 실행됩니다. transaction은 다음 경로의 이전 상태를 snapshot합니다.

- 모든 wiki operation target
- `index.md`
- `log.md`
- `data/wiki_patches/applied.jsonl`
- 관련 `data/promotions/<packet_id>.json`

Manifest는 `data/wiki_patches/transactions/<proposal_id>.json`에 기록됩니다.

```text
prepared -> page writes -> registration/status/log -> committed
                |
                +-- ordinary failure -> restore snapshots -> rolled_back
```

프로세스가 `prepared` 상태에서 종료되면 다음 apply 시도가 incomplete transaction을 먼저 복구한 뒤 새 작업을 시작합니다. 따라서 “page는 바뀌었지만 index/status가 남지 않은 상태”를 정상 완료로 취급하지 않습니다.

## 7. Lint Contract

`lint-wiki`는 blocking issue와 advisory를 구분합니다.

Blocking examples:

- missing provenance
- page missing from index
- page that no durable page or index can discover
- broken wikilink
- malformed internal packet/summary graph
- transient/session-derived page names that violate durable-page policy

Advisory examples:

- missing or unsupported `lang`
- thin prose or missing recommended sections
- insufficient related links when viable targets exist
- unregistered category in explicit registry mode

Emergent-root mode에서는 새로운 category 자체를 문제로 보지 않습니다. `blocking_issue_count=0`이 automation success gate이며 advisory는 인간 또는 후속 Janitor가 검토할 신호입니다.

## 8. Artifact Layout

```text
data/
  exports/
    raw/codex/<thread_id>.json
    context_packets/<packet_id>.json
    context_packets/<packet_id>.md
    evidence/<session_id>/<micro_id>.json
    summaries/<packet_id>-micro-v2.json
    summaries/<packet_id>-unit-v2.json
    recovery/<session_id>.json
    lint/<report_id>.json
  atoms/*.jsonl
  promotions/<packet_id>.json
  wiki_decisions/<packet_id>.json
  wiki_patches/<packet_id>.json
  wiki_patches/applied.jsonl
  wiki_patches/transactions/
  index/session_ledger.json
  index/codex_hook_events.jsonl
  index/codex_jobs.sqlite3
  index/codex_worker_status.json
  index/codex_watcher_state.json
```

Artifact root와 LLM Wiki root는 서로 다른 경계입니다. `project_root`는 machine artifact 저장소이며 active Codex workspace allowlist가 아닙니다.

## 9. Path Resolution

Wiki root precedence:

1. `AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT`
2. `WIKI_PATH`
3. installed `local_config.json["wiki_root"]`
4. `%USERPROFILE%\Documents\LLM Wiki` portable template

Resolver는 `%VAR%`, `$VAR`, `${VAR}`, `~`, relative path를 처리하고 effective path를 runtime에 계산합니다. 기본 설치는 사용자명이 포함된 absolute wiki path를 config의 진실로 저장하지 않습니다.

## 10. Extension Rules

새 integration 또는 feature는 다음 규칙을 지킵니다.

1. Host-specific parsing은 adapter에 둡니다.
2. Core domain은 typed object를 받고 raw dict 변환을 반복하지 않습니다.
3. 새 LLM 실행 경로는 `LLMInputSafetyOptions`와 shared runtime을 사용합니다.
4. 새 wiki writer는 `WikiApplyTransaction`과 동일한 commit boundary를 통과합니다.
5. 새로운 category/type은 emergent mode에서 차단 조건이 아닙니다.
6. 새 blocking lint는 데이터 손상, provenance, discoverability, unsafe path처럼 자동화 성공을 실제로 무효화하는 경우에만 추가합니다.
7. CLI와 hook/watch entry point는 domain 규칙을 복제하지 않고 application service에 위임합니다.
8. 비동기 trigger는 side effect 전에 durable enqueue하고, 모든 write 경계에서 captured fingerprint가 여전히 최신인지 확인합니다.
9. History scan과 새 Stop-event queue는 별도 개념입니다. 설치/upgrade가 과거 rollout을 자동 enqueue하지 않습니다.

## 11. Compatibility Surfaces

- 기존 absolute `wiki_root` config는 legacy source로 계속 해석합니다.
- 기존 promotion JSON의 optional intent fields가 없어도 로드합니다.
- `WikiPatchOperation.candidate_id`는 primary ID로 유지하고 `candidate_ids`로 병합 집합을 표현합니다.
- legacy explicit promotion CLI와 네 개의 고정 folder는 호환 목적으로 유지합니다.
- existing legacy wiki page를 자동 이동하지 않습니다.
