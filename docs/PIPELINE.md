# Agent Context Substrate 파이프라인 / Runtime architecture

이 문서는 소스 스냅샷 `ea83152`의 실행 경로, 기본값, 산출물과 provenance를 설명합니다. 설계 목표와 현재 구현을 구분하며 라이브 설치나 테스트 성공을 보증하지 않습니다. 사용 절차는 [한국어 가이드](USER_GUIDE.md)와 [English guide](USER_GUIDE.en.md)를 참고하세요.

## 1. 아키텍처와 게시 다이어그램

기본 경로는 heuristic 요약으로 세션을 복구 가능한 packet으로 만드는 것입니다. 생성 데이터는 artifact project root의 `data/`에 저장합니다. 기본 finalize는 human-facing wiki page를 만들지 않습니다.

```text
Hermes state.db -> SessionStore -> SessionBundle ─┐
                                               ├-> heuristic MicroSummary / UnitSummary
Codex SQLite + rollout JSONL -> SessionBundle ───┘   -> ContextPacket JSON / Markdown
                                                   -> wiki + artifact graph lint
                                                   -> ledger -> RecoveryBrief + quality_gate

Hermes / core opt-in V2:
SessionBundle -> evidence -> summarizer backend -> lint / fallback
             -> V2 micro / unit summaries -> optional judge report
             -> structured atoms -> claim-based promotion candidates
             -> wiki patch proposal -> dry-run -> explicit --apply

Request time: knowledge / recovery / graph search -> expand-hit -> provenance
```

현재 기본 builders는 세션마다 micro 1개와 unit 1개를 만듭니다. 여러 micro/unit을 지원하는 모델이 있다고 해서 자동으로 계층형 분할을 수행하는 것은 아닙니다.

[게시 아키텍처 다이어그램](https://jjuck.github.io/agent-context-substrate/site/)은 `ea83152` 기준의 설명용 스냅샷입니다. 실제 게시 파일은 `docs/site/index.html`, 미리보기는 `docs/site/preview.png`, Pages root의 `docs/index.html`은 `site/` redirect입니다. README의 다이어그램 링크도 같은 Pages URL을 사용합니다. 정적 사이트는 ACS 실행 데이터나 wiki의 저장소가 아니며 CLI/소스가 동작과 기본값의 근거입니다.

## 2. 모듈 경계

| 경계 | 소스 | 책임 |
| --- | --- | --- |
| Hermes 입력 | [`session_store.py`](../src/agent_context_substrate/session_store.py), [`raw_extract.py`](../src/agent_context_substrate/raw_extract.py) | DB 조회, raw JSON export, typed bundle 변환 |
| Codex 입력 | [`codex_source.py`](../src/agent_context_substrate/codex_source.py) | read-only SQLite discovery, rollout 필터링과 bundle 변환 |
| 공통 모델 | [`session_bundle.py`](../src/agent_context_substrate/session_bundle.py), [`models.py`](../src/agent_context_substrate/models.py) | typed 세션 경계, artifact serialization, raw pointers |
| 기본 packet | [`packet_builder.py`](../src/agent_context_substrate/packet_builder.py), [`summarizer.py`](../src/agent_context_substrate/summarizer.py), [`context_packet.py`](../src/agent_context_substrate/context_packet.py) | heuristic 추출, packet 구성/export |
| V2 | [`summary_pipeline.py`](../src/agent_context_substrate/summary_pipeline.py), [`evidence.py`](../src/agent_context_substrate/evidence.py), [`summarizer_backends.py`](../src/agent_context_substrate/summarizer_backends.py) | evidence, backend, cache, invariant 검사와 export |
| LLM 연결 | [`agent_llm_router.py`](../src/agent_context_substrate/agent_llm_router.py) | host router/Hermes auxiliary client 연결; provider SDK를 core에서 요구하지 않음 |
| 검토와 쓰기 | [`artifact_pipeline.py`](../src/agent_context_substrate/artifact_pipeline.py), [`atoms.py`](../src/agent_context_substrate/atoms.py), [`promotions.py`](../src/agent_context_substrate/promotions.py), [`wiki_patches.py`](../src/agent_context_substrate/wiki_patches.py) | atoms, 후보, proposal, 제한된 apply와 기록 |
| finalize | [`integration.py`](../src/agent_context_substrate/integration.py), [`codex_integration.py`](../src/agent_context_substrate/codex_integration.py) | host별 orchestration; 기능 범위는 서로 다름 |
| 복구/기록 | [`recovery.py`](../src/agent_context_substrate/recovery.py), [`ledger.py`](../src/agent_context_substrate/ledger.py) | compact brief, 품질 이슈, completed/failed 기록 |
| 검색 | [`retrieval.py`](../src/agent_context_substrate/retrieval.py), `retrieval_*.py`, [`topic_map.py`](../src/agent_context_substrate/topic_map.py) | lexical ranking, source loading, hit ID/확장, graph |
| 검사 | [`lint.py`](../src/agent_context_substrate/lint.py), [`summary_lint.py`](../src/agent_context_substrate/summary_lint.py), [`semantic_lint.py`](../src/agent_context_substrate/semantic_lint.py), [`summary_judge.py`](../src/agent_context_substrate/summary_judge.py) | wiki/artifact lint, V2 acceptance, promotion consistency, 선택적 평가 |

## 3. Hermes와 Codex finalize

| 항목 | Hermes | Codex |
| --- | --- | --- |
| 진입점 | user plugin `on_session_finalize`, `run_session_finalize_pipeline(...)` | Stop hook → `codex-finalize`; `codex-watch` fallback |
| 기본 산출물 | raw, heuristic packet, lint, recovery, ledger | 동일한 종류; raw export 경로는 별도 |
| wiki promotion | `packet-only` 기본; 명시적 `full` 지원 | packet-only 고정; promotion 옵션 없음 |
| V2 | 기본 미생성; `summary_mode` 지정 시 생성 | finalize/watch API에 V2 옵션 없음 |
| Summary Judge | `off` 기본; V2와 함께 `hybrid` opt-in | finalize/watch에서 사용하지 않음 |
| 중복 처리 | completed artifact 존재와 promotion/summary/judge mode 일치 시 재사용 | 직접 finalize는 다시 생성; watcher는 rollout fingerprint 사용 |
| 실패 처리 | failed ledger, 기본 retry budget 3; 예외 전파 | failed ledger; Stop hook 오류는 대화 종료를 막지 않음 |

두 finalize 경로는 기본 artifact paths를 ledger에 기록한 뒤 recovery를 만들고 recovery path를 포함해 다시 기록합니다. `completed`는 lint 이슈가 없거나 recovery 품질이 좋다는 뜻이 아닙니다. 실패 시 partial artifact가 남을 수 있습니다.

### Hermes control gates

[`user_plugin/config.py`](../src/agent_context_substrate/assets/user_plugin/agent_context_substrate/config.py)와 [`runtime.py`](../src/agent_context_substrate/assets/user_plugin/agent_context_substrate/runtime.py)의 기본 정책:

- `AGENT_CONTEXT_SUBSTRATE_AUTO_FINALIZE=true`: 자동 finalize 활성화. session ID가 없으면 무시합니다.
- `AGENT_CONTEXT_SUBSTRATE_MIN_MESSAGE_COUNT=3`: 최소 메시지 수.
- `AGENT_CONTEXT_SUBSTRATE_ALLOWED_SOURCES=telegram,cli`: raw bundle source 허용 목록.
- `AGENT_CONTEXT_SUBSTRATE_SKIP_TITLE_PATTERNS`: 기본 빈 목록; regex로 제목 제외.
- `AGENT_CONTEXT_SUBSTRATE_GATEWAY_POLICY=trigger-only`: gateway는 세션 경계 trigger라는 설정입니다. hook platform과 raw source는 다르며 실제 eligibility는 source/message/title 검사로 결정합니다.
- `AGENT_CONTEXT_SUBSTRATE_PROMOTION_MODE=packet-only`, `AGENT_CONTEXT_SUBSTRATE_SUMMARY_MODE` 빈 값, `AGENT_CONTEXT_SUBSTRATE_SUMMARY_CACHE=false`, `AGENT_CONTEXT_SUBSTRATE_SUMMARY_JUDGE_MODE=off`.

자동 hook policy와 직접 Python finalize API는 별개입니다. `run_session_finalize_pipeline(...)` 자체가 hook eligibility 검사를 대신하지 않습니다.

### Codex control gates와 한계

[`codex_hook.py`](../src/agent_context_substrate/codex_hook.py)는 `Stop`, `session_id`, 유효한 plugin `local_config.json`, `project_root`와 `wiki_root`, 설정 project root 안의 `cwd`를 요구합니다. 설치와 hook trust는 host의 별도 조건입니다. hook 파일 존재를 확인하는 `codex-status`만으로 실제 Stop 실행을 검증할 수 없습니다.

Stop hook은 설정 project root에서 CLI를 호출하며 기본 timeout은 110초입니다. 성공 후 watcher state를 갱신합니다. 오류/timeout은 `continue: true`로 반환하고 `codex-watch` fallback을 안내합니다.

Watcher 기본값은 interval 15초, idle 90초입니다. `rollout_path`, `mtime_ns`, `size` fingerprint가 바뀌고 idle 조건을 만족하면 처리합니다. idle은 세션 종료의 증거가 아닙니다. watcher에는 Stop hook의 `cwd` containment gate나 Hermes의 source/message/title eligibility gate가 없습니다. 직접 `codex-finalize`도 hook gate를 거치지 않습니다. fallback 범위는 선택한 Codex home의 discovery 결과입니다.

Codex 통합은 local session source와 non-MCP skill/hook입니다. Codex host LLM router, Hermes context-engine preload/compression 또는 request-time tool 등록을 이 adapter가 제공한다고 해석하면 안 됩니다.

## 4. 기본 heuristic과 opt-in V2

`build-context-packet`에서 `--summary-mode`를 생략하면 기존 heuristic `MicroSummary`, `UnitSummary`, `ContextPacket`만 만듭니다. `--summary-mode heuristic`은 V2 evidence/summary artifact를 추가 export하는 명시적 opt-in입니다. V2가 기존 packet을 대체하지는 않습니다.

| V2 mode | 실제 사용 조건 |
| --- | --- |
| `heuristic` | standalone CLI/core API에서 가능; 외부 LLM 호출 없음 |
| `custom-command` | `--summarizer-command` 필요; JSON stdin → strict JSON stdout, shell 없는 subprocess |
| `agent-llm` | injected host Agent LLM router 필요 |
| `hybrid` | heuristic evidence와 host Agent LLM router 사용 |

standalone CLI handler는 `agent-llm`/`hybrid`를 거절합니다. parser choices에 나타나는 것만으로 독립 CLI에서 실행 가능하다는 뜻은 아닙니다. Hermes plugin은 host/auxiliary router 연결을 시도합니다. model/budget은 routing hint이며 별도 provider 설정이나 키를 core에서 강제하지 않습니다.

V2 micro summary는 `recovery_summary`, `knowledge_summary`, `retrieval_summary`를 구분합니다. decisions/claims/action items에는 evidence-backed text를 사용합니다. metadata에는 mode, schema/prompt version, input hash, confidence와 fallback 정보를 기록합니다. backend의 parse/repair/lint/fallback 이후에도 `summary_pipeline.py`가 session ID, evidence와 micro/unit references를 검사하고 invariant 위반이면 export를 거절합니다. cache를 읽을 때도 검사합니다.

외부 summarizer 입력의 기본 safety는 redact on, 최대 12,000자, code snippets off, local path policy redact입니다. 이 설정은 외부 호출용 payload에 적용합니다. 로컬 raw/evidence/packet/cache 전체를 익명화하는 정책으로 간주하면 안 됩니다.

`summary_judge_mode=hybrid`는 선택적 평가 JSON을 생성하며 기본값은 `off`입니다. V2 없이 judge를 요청하면 거절됩니다. Judge는 mechanical lint와 summary/evidence, Hermes finalize에서는 recovery `quality_gate`도 입력으로 사용합니다. router 실패 시 mechanical verdict로 내려가며 summary를 고치거나 wiki patch를 적용하는 gate가 아닙니다.

## 5. Atoms → 검토 → wiki patch

`extract-atoms`는 V2 micro summary에서 **claim, decision, entity, concept, question**을 각각 JSONL로 export합니다. `ea83152`의 [`export_atoms(...)`](../src/agent_context_substrate/artifact_pipeline.py)와 CLI help가 다섯 종류를 구현합니다. 그러나 `propose-promotions`가 읽는 것은 **claim atoms만**입니다. 다른 atom 유형이 바로 promotion/patch 입력이 되는 것은 아닙니다.

후보 생성과 patch 계획은 project artifact만 쓰며 wiki를 수정하지 않습니다. `review-promotion`의 accept/reject/supersede/apply는 후보 상태 기록입니다. `apply` 상태 기록과 실제 wiki 쓰기는 별개입니다. 후보 accepted 상태가 모든 patch apply의 필수 승인 gate라고 가정하면 안 됩니다.

`apply-wiki-patch`는 `--apply`가 없으면 dry-run입니다. 지원 write operations는 `create_page`, `insert_claim_block`, `append_section`, `append_managed_section`입니다. proposed operation status, 안전한 wiki target, 지원 operation, create/managed-block conflict를 검사합니다. `add_link`, `mark_stale` 등 지원 밖 operation은 skip합니다. skipped reasons를 확인해야 하며 apply는 여러 파일을 묶은 원자적 transaction이나 rollback 기능이 아닙니다.

실제 적용된 operation은 `applied.jsonl`에 기록하고 promotion 후보 상태를 갱신합니다. Seed page 생성은 언어별 curated template renderer가 아니므로 human-facing wiki의 `lang`, navigation, provenance 요구사항은 별도 lint/review 대상입니다.

명시적 `promotion_mode="full"`, `promote-packet-query`, `promote-packet-plan`, `promote-unit-concept`, `promote-unit-architecture`, `run-e2e-pipeline`은 legacy wiki write 경로입니다. `queries/`, `concepts/`, `plans/`, `architectures/`와 index/log/backlinks를 사용합니다. review-first patch 경로와 혼동하지 마세요. `draft`/`curated` finalize modes는 현재 허용되지 않습니다.

## 6. 데이터 경로와 provenance

### Root 해석

| 설정 면 | 실제 기본값과 우선순위 |
| --- | --- |
| core `HarnessPaths` home | 명시적 `home_dir` → `HOME` → OS home expansion |
| Hermes home | 명시적 `hermes_home` → `HERMES_HOME` → `<home>/.hermes`; DB는 `state.db` |
| core wiki root | 명시적 `wiki_root` → `WIKI_PATH` → `<home>/wiki` |
| CLI project root | `--project-root` → 실행 시 current directory |
| Hermes packaged plugin | project/wiki 환경 변수 → installer local config → `~/.hermes/agent-context-substrate`, `~/LLM Wiki` |
| Hermes context engine | 환경 변수/local config 사용; wiki는 `WIKI_PATH`도 참조; fallback `~/LLM Wiki` |
| Codex home | 명시적 `--codex-home` → `CODEX_HOME` → `(HOME 또는 Path.home())/.codex` |
| Codex setup/doctor wiki | 명시적 root → `Path.home()/Documents/LLM Wiki` |
| Codex watch/search/expand CLI wiki | 명시적 `--wiki-root` → `WIKI_PATH` → `Path.home()/LLM Wiki` |
| Codex finalize wiki | `--wiki-root` 필수; hook은 local config 값을 전달 |

설정 면마다 wiki 기본값이 다릅니다. 자동 hook과 수동 CLI가 같은 root를 쓰도록 explicit roots/local config를 확인하세요. source checkout과 artifact project root는 목적이 다르며 이 문서가 checkout 위치를 변경하지는 않습니다.

### 산출물

아래 경로는 artifact project root 기준입니다. 해당 단계의 실행이 필요하며 기본 finalize가 전부 만들지는 않습니다.

| 산출물 | 경로 | 생성 단계 |
| --- | --- | --- |
| Hermes raw | `data/exports/<session_id>.json` | extract / packet / Hermes finalize |
| Codex raw | `data/exports/raw/codex/<thread_id>.json` | Codex finalize/watch |
| ContextPacket | `data/exports/context_packets/<packet_id>.json`, `.md` | packet / finalize |
| wiki + artifact lint | `data/exports/lint/<report_id>.json`, `.md` | lint / finalize |
| RecoveryBrief | `data/exports/recovery/<session_id>.json` | finalize; Codex session ID는 thread ID |
| SessionLedger | `data/index/session_ledger.json` | finalize |
| watcher state | `data/index/codex_watcher_state.json` | watch / 성공한 Stop hook |
| V2 evidence | `data/exports/evidence/<session_id>/<micro_id>.json` | V2 opt-in |
| V2 summaries | `data/exports/summaries/<packet_id>-micro-v2.json`, `<packet_id>-unit-v2.json` | V2 opt-in |
| summary cache | `data/cache/summaries/<cache_key>.json` | cache on |
| judge verdict | `data/exports/evals/<packet_id>-summary-judge.json` | judge opt-in |
| atoms | `data/atoms/claims.jsonl`, `decisions.jsonl`, `entities.jsonl`, `concepts.jsonl`, `questions.jsonl` | extract-atoms |
| promotion candidates | `data/promotions/<packet_id>.json`, `.md` | propose-promotions |
| wiki patch proposal | `data/wiki_patches/<packet_id>.json`, `.md` | plan-wiki-patches |
| applied patch log | `data/wiki_patches/applied.jsonl` | 실제 적용된 operation |
| semantic lint | `data/lint/<report_id>.json`, `.md` | lint-promotions |
| topic map | `data/index/<report_id>.json`, `.md` | build-topic-map |

`RawSessionReference`가 source, session/thread ID, message IDs와 timestamps/title을 보존합니다. source refs는 `hermes-session:<id>#messages=...` 또는 `codex-thread:<id>#messages=...`입니다. Hermes message IDs는 DB ID이고 Codex message IDs는 rollout의 **1-based line numbers**입니다. Codex line numbers를 Hermes DB 조회에 사용하면 안 됩니다.

Codex SQLite는 `mode=ro`로 읽고 기본 discovery는 `state_5.sqlite`의 thread/rollout 정보를 사용합니다. DB discovery 결과가 없으면 `sessions/**/rollout-*.jsonl` glob으로 내려갑니다. user/assistant/function-call/function-output 이벤트를 변환하고 system/developer/reasoning/encrypted content를 제외합니다. 일반적인 secret/email 패턴을 가리고 tool output은 기본 12,000자로 제한합니다. 이 export는 원본 rollout의 완전한 복사본이 아닙니다.

Packet raw pointers → summary/evidence message IDs → atom source refs → promotion evidence → patch candidate/packet IDs가 추적 연결입니다. 원본 DB/rollout을 삭제하거나 수정하면 pointer가 있어도 원문을 재확인하지 못할 수 있습니다.

## 7. 검색, lint, recovery 품질

`search_knowledge(...)`와 `expand_hit(...)`는 read-only이며 현재 vectorless lexical retrieval입니다. Hermes context engine은 `wiki_knowledge_search`/`wiki_knowledge_expand`를 노출하고 Codex는 `search-knowledge`/`expand-hit` CLI를 사용합니다.

| Mode | 입력 |
| --- | --- |
| `knowledge` | wiki Markdown, packet 내부 unit/micro summaries, topic map, promotion/patch/applied records |
| `recovery` | RecoveryBrief와 packet recovery 필드; source priority를 먼저 적용 |
| `graph` | 저장된 topic-map nodes/edges/paths; graph depth로 주변 연결 확장 |

Wiki 검색은 `_system/`, `90 보관/`, dot folders를 제외합니다. `include_raw`는 기본 false이며 현재 raw 검색은 Hermes `state.db` 메시지입니다. Codex raw export를 같은 옵션으로 검색하는 adapter는 없습니다. V2 export 파일이나 atom JSONL 전체가 독립 검색 source라고 가정하지 마세요.

wiki lint는 provenance, index/orphan/broken links, `lang: ko|en`, generated/transient page quality를 검사합니다. 내부 graph lint는 micro parent, unit micro references, packet raw pointers를 검사합니다. semantic lint는 promotion/atom/patch 기록의 일관성을 검사하며 모든 모순·중복·staleness를 자동 해결하지 않습니다.

RecoveryBrief는 task/macro context, decisions/progress, files/pages, next actions/open questions, provenance를 담습니다. `quality_gate`는 누락 항목과 score를 보고합니다. finalize 성공과 독립적인 품질 신호이며 부족한 brief의 저장을 자동 차단하지 않습니다.

## 8. 설치와 이식성

[`distribution.py`](../src/agent_context_substrate/distribution.py)가 packaged assets를 설치합니다. Hermes `install-plugin`은 `~/.hermes/plugins/agent-context-substrate`, `install-context-engine`은 `<HERMES_AGENT_ROOT>/plugins/context_engine/agent_context_substrate`를 사용합니다. `setup-codex`는 Codex plugin, local JSON config, hook/marketplace 설정을 다루며 `install-codex-plugin`은 하위 asset 설치 명령입니다. plugin은 MCP server/app을 등록하지 않습니다. `doctor`, `doctor-codex`, `fresh-install-smoke`는 진단/검증 명령이지 여기서 실행 성공을 주장하는 근거가 아닙니다.

공통 `SessionBundle`이 있어도 Hermes 중심 경계가 남아 있습니다. `HarnessPaths.state_db_path`, `extract-session`, `build-context-packet`, raw-message retrieval은 Hermes 입력을 사용합니다. `RawSessionReference.source_ref()`는 Codex 외의 source를 Hermes prefix로 처리하므로 새 adapter에는 provenance namespace 변경도 필요합니다.

과거 HOME/Windows custom-command parsing 문제를 현재 결함으로 유지하지 않습니다. `paths.py`는 `HOME`을 우선하며 external command splitter는 Unix `shlex.split`과 Windows `CommandLineToArgvW`를 구분하고 shell 없는 실행을 유지합니다. 공백 포함 경로는 quoting이 필요합니다. 생성 `local_config.py`는 source escape 문자열이 아닌 runtime `Path` 값으로 확인해야 합니다. Windows symlink 검증은 OS 권한/Developer Mode에 영향을 받으므로 해당 환경의 skip을 보안 검증 통과로 간주하면 안 됩니다.

추가 agent 지원을 주장하기 전에는 explicit roots, source/role/event mapping, provenance namespace, host LLM router, lifecycle hook/watcher scope, platform path/command handling을 검증해야 합니다. 현재 packaged integration 범위는 Hermes와 local Codex이며 범용 adapter protocol이나 모든 Windows 설정 지원을 보장하지 않습니다.

## 9. CLI 확인과 설계 문서의 경계

최신 옵션은 로컬 CLI help로 확인하세요. 다음은 설정이나 raw 세션을 변경하지 않는 help 조회입니다.

```powershell
agent-context-substrate build-context-packet --help
agent-context-substrate codex-finalize --help
agent-context-substrate codex-watch --help
agent-context-substrate extract-atoms --help
agent-context-substrate apply-wiki-patch --help
agent-context-substrate search-knowledge --help
```

[`cli.py`](../src/agent_context_substrate/cli.py)와 `commands/`가 실제 명령 계약입니다. patch apply는 `--patch-file`과 선택적 `--apply`를 사용하며 `--patch-id`/`--dry-run`은 현재 apply parser 옵션이 아닙니다. `build-topic-map`은 source graph 생성 명령이며 query 기반 graph 검색은 `search-knowledge --mode graph`입니다.

과거 `spec.md`와 세 구현 계획은 현재 안내에서 제거했으며 Git 이력에 남아 있습니다. 아직 평가할 설계 목표는 curated promotion target과 언어별 wiki template rendering, 외부 참조의 source-card ingestion입니다. 구현한다면 명시적 provenance와 wiki 변경 전 검토가 필요합니다. 이는 현재 기능이나 release 약속이 아닙니다. snapshot과 소스가 runtime 설명의 기준이며 한국어/영어 가이드도 동일한 default/opt-in/adapter 구분을 유지합니다.
