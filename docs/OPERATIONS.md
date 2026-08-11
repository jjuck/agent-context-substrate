# Agent Context Substrate 운영 가이드

이 문서는 설치가 끝난 ACS를 검증하고 운영하며 장애를 복구하는 canonical runbook입니다. 아키텍처는 [PIPELINE.md](./PIPELINE.md), 설치는 [WINDOWS_CODEX_APP_SETUP.ko.md](./WINDOWS_CODEX_APP_SETUP.ko.md)를 참고하세요.

## 1. 운영 목표

운영자는 다음 상태를 보장합니다.

1. Hermes/Codex 원본 session store는 read-only로 취급한다.
2. Machine artifact는 `<PROJECT_ROOT>/data`, human-facing knowledge는 resolved `<WIKI_ROOT>`에 분리한다.
3. Codex Stop hook은 finalize job을 먼저 durable queue에 남기고 빠르게 반환한다.
4. Singleton worker는 summary, judge, apply 결과를 ledger, queue, event log에 남긴다.
5. 승인된 candidate만 transaction으로 적용한다.
6. 최종 blocking lint는 0으로 유지하고 advisory는 사후 품질 backlog로 관리한다.

## 2. 현재 기준선

2026-07-21, v0.2.0 workspace 기준:

```text
python -m pytest -q  -> 408 passed, 12 skipped
python -m ruff check . -> All checks passed
Codex live E2E -> summary_mode=codex-cli
Codex live E2E -> wiki_write_decision=apply_flexible, score=0.95
Codex live E2E -> wiki_apply_applied_count=1, lint_issue_count=0
```

이 숫자는 release evidence이지 영구 상수가 아닙니다. behavior 변경 후에는 `CHANGELOG.md`와 release checklist의 최신 검증 결과를 함께 갱신합니다.

## 3. 핵심 경로

| Purpose | Path or resolver |
| --- | --- |
| Hermes source | `HERMES_HOME/state.db` |
| Codex metadata | `%USERPROFILE%\.codex\state_5.sqlite` |
| Codex rollout | `%USERPROFILE%\.codex\sessions\**\rollout-*.jsonl` |
| ACS artifacts | `<PROJECT_ROOT>/data` |
| LLM Wiki | runtime-resolved `<WIKI_ROOT>` |
| Hook events | `<PROJECT_ROOT>/data/index/codex_hook_events.jsonl` |
| Durable Codex queue | `<PROJECT_ROOT>/data/index/codex_jobs.sqlite3` |
| Worker heartbeat/status | `<PROJECT_ROOT>/data/index/codex_worker_status.json` |
| Watcher state | `<PROJECT_ROOT>/data/index/codex_watcher_state.json` |
| Session ledger | `<PROJECT_ROOT>/data/index/session_ledger.json` |
| Wiki transaction manifests | `<PROJECT_ROOT>/data/wiki_patches/transactions/` |

Wiki root precedence:

1. `AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT`
2. `WIKI_PATH`
3. installed `local_config.json["wiki_root"]`
4. `%USERPROFILE%\Documents\LLM Wiki`

`config-codex paths`는 configured template과 effective path를 구분해서 보여줍니다.

## 4. 시작 전 점검

```bash
python -m agent_context_substrate.cli --help
python -m agent_context_substrate.cli lint-wiki --help
python -m pytest -q
python -m ruff check .
git diff --check
```

Windows Codex:

```powershell
.\.venv\Scripts\agent-context-substrate.exe codex-status
.\.venv\Scripts\agent-context-substrate.exe doctor-codex --fail-on-issues
.\.venv\Scripts\agent-context-substrate.exe config-codex show
.\.venv\Scripts\agent-context-substrate.exe config-codex paths
```

정상 기본값:

```text
hook_support=supported
hook_primary=installed
watcher_fallback=available
trigger_strategy=hook-enqueue
summary_mode=auto
wiki_auto_mode=apply-flexible
wiki_write_judge_mode=auto
wiki_auto_min_score=0.85
workspace_scope=all
```

`doctor-codex --summary-smoke`는 signed-in `codex exec`를 실제로 호출하므로 필요할 때 명시적으로 실행합니다.

## 5. 표준 운영 모드

### 5.1 Hermes Or Standalone Packet Only

```bash
agent-context-substrate build-context-packet \
  --session-id '<SESSION_ID>' \
  --packet-id '<PACKET_ID>' \
  --task-title '<TASK_TITLE>' \
  --macro-context '<MACRO_CONTEXT>' \
  --unit-title '<UNIT_TITLE>' \
  --goal '<GOAL>' \
  --project-root '<PROJECT_ROOT>'
```

V2 summary가 필요하면 `--summary-mode heuristic|custom-command|codex-cli|auto`를 추가합니다. Hermes/standalone finalize는 명시하지 않는 한 wiki full promotion을 실행하지 않습니다.

### 5.2 Manual Codex Finalize

```powershell
agent-context-substrate codex-finalize `
  --thread-id '<THREAD_ID>' `
  --codex-home "$HOME\.codex" `
  --project-root '<PROJECT_ROOT>' `
  --wiki-root '<WIKI_ROOT>' `
  --summary-mode auto `
  --wiki-auto-mode apply-flexible `
  --wiki-write-judge-mode auto `
  --wiki-auto-min-score 0.85
```

성공 확인:

- `data/exports/context_packets/<thread_id>.json`
- `data/exports/summaries/<thread_id>-micro-v2.json`
- `data/wiki_decisions/<thread_id>.json`
- `data/wiki_patches/<thread_id>.json`
- ledger의 `status=completed`
- `wiki_apply_dry_run=False`인 경우 `wiki_apply_applied_count>0`
- `lint_issue_count=0`

Judge가 `review_required`, `propose_only`, `skip`을 반환하거나 score가 기준보다 낮으면 `wiki_apply_dry_run=True` 또는 적용 0건이 정상입니다.

### 5.3 Durable Stop Queue

기본 Stop 경로는 다음과 같습니다.

```text
Stop hook
  -> rollout fingerprint와 config digest를 SQLite에 commit
  -> opportunistic singleton worker 시작
  -> 즉시 반환

worker
  -> newest runnable job lease
  -> fingerprint 확인
  -> global finalize/wiki lock 아래 pipeline 실행
  -> wiki write 직전 fingerprint 재확인
  -> complete 또는 backoff retry/dead-letter
  -> queue가 비면 종료
```

같은 thread에서 Stop event가 연속으로 오면 queued generation은 latest-wins로 합쳐집니다. 실행 중 rollout이 변경되면 stale job이 wiki를 쓰지 않고 최신 fingerprint job을 다시 enqueue합니다. Worker가 비정상 종료되어도 lease 만료 뒤 다음 Stop worker가 job을 회수할 수 있습니다. 설치 시점의 과거 rollout은 queue에 넣지 않으므로 migration 직후 대량 backfill이 발생하지 않습니다.

다른 finalize가 global lock을 점유 중이면 worker는 이를 transient failure로 세지 않고 job을 `retry` 상태로 defer합니다. 이때 attempt budget은 소비하지 않으며, 재시도 간격은 `worker_lock_contention_retry_seconds`로 제어합니다(기본 60초, 유효 범위 5~300초).

Artifact ledger의 read-modify-write와 wiki vault mutation은 각각 process lock으로 직렬화됩니다. 특히 같은 wiki root를 공유하는 Codex와 Hermes 경로는 동일한 vault lock을 사용하므로 서로 다른 project나 adapter가 `index.md`, `log.md`, transaction manifest를 동시에 갱신하지 않습니다.

주요 lock 경로는 project의 `data/index/codex_worker.lock`, `data/index/codex_finalize.lock`, `data/index/wiki_writer.lock`, `data/index/session_ledger.json.lock`과 OS 임시 디렉터리의 wiki-root 해시 lock입니다. Lock 파일은 해제 후에도 재사용을 위해 남으므로 파일 존재만으로 점유 또는 장애를 판단하지 마세요. `codex-status`의 worker/queue 상태와 실제 lock 획득 결과를 함께 확인합니다.

운영 확인은 `codex-status`와 `data/index/codex_jobs.sqlite3`의 queue health를 기준으로 합니다. `queued`는 대기, `leased`는 처리 중, `retry`는 backoff 대기, `dead_letter`는 retry budget 소진입니다. `codex-jobs list --status dead_letter`로 last error를 확인하고, 원인을 해결한 뒤 `codex-jobs retry --job-id <ID>`로 명시적으로 재처리하세요. SQLite 파일을 직접 수정하거나 삭제해서 상태를 숨기지 않습니다.

`codex-status`는 `trigger_strategy`, `job_queue_path`, `queue_pending_count`, `queued`, `leased`, `retry`, `dead_letter`, oldest pending age와 함께 `worker_status`, heartbeat age, last error를 출력합니다. Queue가 비었고 worker status가 `idle`이면 정상입니다. Worker를 계속 떠 있는 service로 해석하지 마세요.

자동 spawn이 실패했거나 수정 후 drain을 수동 검증해야 할 때만 설치 plugin root를 지정해 worker를 실행합니다.

```powershell
agent-context-substrate codex-worker `
  --plugin-root "$HOME\.codex\plugins\agent-context-substrate" `
  --max-jobs 1
```

`--max-jobs`를 생략하면 현재 runnable queue를 drain합니다. 이 명령도 singleton worker lock을 사용하므로 이미 worker가 실행 중이면 중복 consumer가 되지 않습니다. Primary 설치 plugin의 `local_config.json`이 canonical config이며 cache 경로에서 시작된 worker도 이를 우선 resolve합니다.

Hook event log에서 `enqueued`는 durable commit, `refreshed`는 rollout/config snapshot 교체, `retry`는 backoff 예약, `dead-letter`는 retry budget 소진, `finalized`는 worker pipeline 완료를 뜻합니다.

### 5.4 Watcher Recovery And Backfill

```powershell
agent-context-substrate codex-watch `
  --codex-home "$HOME\.codex" `
  --project-root '<PROJECT_ROOT>' `
  --wiki-root '<WIKI_ROOT>' `
  --once
```

`codex-watch`는 queue worker가 아니라 rollout history scanner입니다. Plugin Stop hook이 정상 동작하면 상시 실행하지 않습니다. Hook 미신뢰, 구형 runtime, 누락 event의 명시적인 복구/backfill에만 사용합니다.

기본 idle window로 무심코 실행하면 오래된 eligible thread를 대량 처리할 수 있습니다. 첫 연결 확인에는 `--once --idle-seconds 999999`처럼 보수적인 window를 사용하세요. 실제 backfill 전에는 candidate 범위와 watcher state를 확인하고, wiki와 artifact root를 백업한 뒤 처리 window를 의도적으로 정합니다. Queue와 watcher를 동시에 돌려도 global lock이 apply를 직렬화하지만, 중복 작업 비용까지 없애 주지는 않습니다.

### 5.5 Legacy Full Promotion

Legacy 네 페이지 promotion은 임시 wiki에서 먼저 검증합니다.

```bash
TMP_WIKI=$(mktemp -d)
WIKI_PATH="$TMP_WIKI" agent-context-substrate run-e2e-pipeline \
  --session-id '<SESSION_ID>' \
  --packet-id '<PACKET_ID>' \
  --task-title '<TASK_TITLE>' \
  --macro-context '<MACRO_CONTEXT>' \
  --unit-title '<UNIT_TITLE>' \
  --goal '<GOAL>' \
  --report-id legacy-smoke \
  --project-root '<PROJECT_ROOT>'
```

이 경로만 `queries/`, `concepts/`, `plans/`, `architectures/`를 사용합니다.

## 6. Wiki 운영

새 vault의 기본 config:

```yaml
wiki:
  default_language: ko
  supported_languages: [ko, en]
  filename_language: ko
  template_language: ko
  source_language_preserve: true
  placement_policy: emergent-root
```

운영 원칙:

- 새 flexible page는 기본적으로 vault root에 생성합니다.
- `category`는 optional metadata이며 write permission이 아닙니다.
- 새 category를 발견해도 자동 write를 막지 않습니다.
- category 없는 page는 index의 `Unclassified / Review Needed`에 등록합니다.
- `review_needed: true`는 실패가 아니라 사후 검토 신호입니다.
- 실제 durable target이 있을 때만 wikilink를 추가합니다.

## 7. Lint 해석

```bash
WIKI_PATH='<WIKI_ROOT>' agent-context-substrate lint-wiki \
  --project-root '<PROJECT_ROOT>' \
  --report-id operations-check \
  --fail-on-issues
```

`lint-wiki`는 별도 `--wiki-root` 옵션 대신 공통 resolver를 사용합니다. 설치 config를 쓰지 않는 수동 점검에서는 위처럼 `WIKI_PATH`를 해당 프로세스에만 지정합니다.

### Blocking

자동화 성공을 무효화하는 문제입니다.

- `missing_provenance_pages`
- `orphan_pages`
- `pages_missing_from_index`
- `broken_wikilinks`
- internal packet/summary reference failures
- transient, smoke, session-ID page naming 같은 durable-page 위반

`index.md`의 wikilink도 discoverability inbound로 인정합니다.

### Advisory

작업은 성공시키되 검토 backlog로 남깁니다.

- `missing_lang_pages`
- `unsupported_lang_pages`
- `missing_required_sections_pages`
- `thin_content_pages`
- `unexplained_english_terms_pages`
- `insufficient_related_links_pages`
- strict/registry mode의 `unregistered_category_pages`

Emergent-root mode에서는 새로운 category를 advisory로도 보고하지 않습니다.

## 8. Wiki Transaction 점검

정상 apply manifest는 `committed`로 끝납니다. `rolled_back`은 적용 중 오류가 있었지만 snapshot 복구가 완료됐다는 뜻입니다.

`prepared`가 남아 있으면 이전 프로세스가 commit 또는 rollback 전에 종료된 것입니다. 다음 동일 proposal apply가 자동 복구를 먼저 수행합니다. 수동으로 page/index/log 중 일부만 고치지 말고 proposal을 다시 apply해 복구 경계를 통과시키세요.

점검 대상:

```text
data/wiki_patches/transactions/<proposal_id>.json
data/wiki_patches/transactions/<proposal_id>.snapshots/
data/wiki_patches/applied.jsonl
data/promotions/<packet_id>.json
<WIKI_ROOT>/index.md
<WIKI_ROOT>/log.md
```

## 9. 장애 대응

### 9.1 Stop Hook이 실행되지 않음

1. Codex 앱을 재시작합니다.
2. Settings -> Hooks에서 ACS Stop hook을 trust/enable합니다.
3. `codex-status`에서 `hook_primary=installed`를 확인합니다.
4. `trigger_strategy=hook-enqueue`인지 확인합니다.
5. `data/index/codex_hook_events.jsonl`의 최근 `skipped` 또는 `failed` detail을 확인합니다.
6. 누락 event를 복구해야 할 때만 보수적인 idle window로 `codex-watch --once`를 실행합니다.

### 9.2 Hook은 끝났지만 Finalize가 아직 완료되지 않음

One-shot Stop hook이 빠르게 끝나는 것은 정상입니다. 이는 finalize 완료가 아니라 durable enqueue 완료를 뜻합니다.

1. `codex-status`에서 queue depth와 상태를 확인합니다.
2. `queued`/`leased`이면 background worker 완료를 기다립니다.
3. `retry`이면 `available_at`과 last error를 확인합니다.
4. `dead_letter`이면 반복 실패 원인을 먼저 해결하고 명시적으로 재처리합니다.
5. `leased` 상태가 비정상적으로 오래되면 다음 worker가 lease expiry 후 reclaim하는지 확인합니다.

### 9.3 Workspace가 Skip됨

기본 `workspace_scope=all`에서는 workspace guard skip이 없어야 합니다. Restricted 설치라면 `allowed_workspace_roots`에 현재 `cwd`의 상위 root가 있는지 확인합니다.

### 9.4 Codex Summary가 Heuristic으로 Fallback

Summary JSON metadata의 `fallback_reason`을 확인합니다.

- `codex_cli_unavailable`: direct Codex CLI 경로 확인
- `command_failed`: 로그인 상태, timeout, service tier 확인
- `invalid_json`: worker output/schema 회귀 확인
- `lint:*`: evidence ID와 summary invariant 확인

진단:

```powershell
agent-context-substrate doctor-codex --summary-smoke
agent-context-substrate diagnose-codex
```

PATH의 `codex`가 npm shim이면 doctor가 찾은 direct app CLI를 `codex_cli_command`로 사용합니다.

### 9.5 Judge는 승인했지만 Apply 0건

확인 순서:

1. decision의 `candidate_ids`가 실제 pending candidate와 일치하는가
2. proposal operation의 `candidate_ids`가 선택 집합 안에 있는가
3. page base hash가 현재 page와 일치하는가
4. target이 wiki root 내부인가
5. promotion candidate가 이미 applied/rejected 상태인가

### 9.6 Lint가 실패함

- provenance 누락: frontmatter `sources` 또는 본문 evidence를 추가합니다.
- index 누락: 자동 registration 실패 여부와 transaction manifest를 확인합니다.
- orphan: index 또는 실제 durable page에서 링크합니다.
- broken link: 존재하는 target으로 수정하거나 불필요한 link를 제거합니다.

가짜 related page를 만들어 lint 숫자만 맞추지 않습니다.

### 9.7 Unknown Session Or Thread

- Hermes: `HERMES_HOME`과 `state.db` profile을 확인합니다.
- Codex: `codex-status`가 표시하는 thread ID와 rollout path를 확인합니다.
- Codex worker가 만든 내부 summary/judge thread는 ingestion 대상에서 제외될 수 있습니다.

## 10. Privacy And Release

- `data/exports`, SQLite, rollout JSONL, recovery, packet, lint report를 private data로 취급합니다.
- API key, OAuth token, password, `.env`, connection string을 commit하지 않습니다.
- Public release 전에 `git status --short --untracked-files=all`을 확인합니다.
- 실제 사용자 wiki를 E2E fixture로 사용하지 않습니다. Temp project와 temp wiki에서 먼저 검증합니다.
- 설치본 검증 시 source, active plugin, marketplace cache의 핵심 asset hash를 비교합니다.
- Hook script 변경 후 plugin을 재설치합니다. Editable Python runtime 변경은 같은 project `src`를 가리키는 설치에서 즉시 반영됩니다.

## 11. 보존과 정리

| Data | Policy |
| --- | --- |
| raw exports | private, 목적 달성 후 삭제 가능 |
| context packets | recovery/retrieval에 필요하면 보존 |
| summary/evidence | judge와 provenance audit 기간 동안 보존 |
| promotion/decision/patch | write 감사 기록으로 보존 |
| transaction snapshots | committed/rolled_back 확인 후 retention 정책으로 정리 가능 |
| session ledger | 재실행/idempotency를 위해 보존 |
| hook event log | size-based rotation 가능 |
| Codex job queue | completed/dead-letter audit와 crash recovery에 필요. 운영 중 파일 직접 삭제 금지 |
| watcher state | rollout fingerprint 재처리를 막기 위해 보존 |

`Unclassified / Review Needed`가 커지면 category 정리를 수동으로 하거나 향후 Janitor/notification pipeline을 붙일 수 있습니다. Category 증가 자체는 운영 장애가 아닙니다.
