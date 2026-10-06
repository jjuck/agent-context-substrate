# Agent Context Substrate 운영 가이드

ACS의 로컬 세션 수집, 장애 진단, 보존과 복구를 위한 런북입니다. 설치는 [한국어 사용자 가이드](USER_GUIDE.md), [English guide](USER_GUIDE.en.md), [Windows 설정](WINDOWS_CODEX_APP_SETUP.ko.md)을 따릅니다. 배포 검증은 [Release checklist](RELEASE_CHECKLIST.md)를 사용합니다.

## 실행 환경과 경로

Python 3.11 이상과 설치된 `agent-context-substrate` CLI가 필요합니다. 아래 예시는 활성화된 가상환경에서 실행하며, `<...>`는 실제 경로 또는 ID로 바꿉니다. `--project-root`는 `data/`를 보관할 ACS 루트입니다.

| 입력/설정 | 실제 기본값과 확인 방법 |
| --- | --- |
| Hermes source | `HERMES_HOME/state.db`; `HERMES_HOME` 미설정 시 `~/.hermes` |
| Codex source | `--codex-home`, `CODEX_HOME`, `~/.codex` 순으로 선택; `state_5.sqlite`와 rollout JSONL 사용 |
| 일반 harness wiki | `WIKI_PATH`, 없으면 `~/wiki` |
| Hermes plugin/engine | 설치된 `local_config.py`; `AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT` / `AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT`로 override |
| 미설치 Hermes plugin 기본 경로 | `~/.hermes/agent-context-substrate`, `~/LLM Wiki` |
| Codex setup/doctor/config wiki | 명시하지 않으면 `~/Documents/LLM Wiki` |
| Codex watcher/search/expand wiki | `WIKI_PATH`, 없으면 `~/LLM Wiki` |
| CLI project root | 해당 옵션이 기본값을 제공하는 명령은 현재 작업 디렉터리 |

명령마다 wiki 기본값이 다르므로 운영 명령에는 경로를 명시합니다. `lint-wiki`에는 `--wiki-root` 옵션이 없으며 `WIKI_PATH`를 사용합니다. Windows의 `~`는 사용자 홈입니다. source checkout을 이동하면 설치된 설정의 경로도 확인하세요.

## 상태 확인: 쓰기 전 진단

```bash
agent-context-substrate --help
agent-context-substrate codex-status --codex-home '<CODEX_HOME>'
agent-context-substrate config-codex paths --codex-home '<CODEX_HOME>' --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>'
agent-context-substrate doctor-codex --codex-home '<CODEX_HOME>' --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>' --fail-on-issues
agent-context-substrate diagnose-codex --codex-home '<CODEX_HOME>' --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>'
```

이 명령은 설치 상태를 확인합니다. `doctor-codex`와 이를 호출하는 `diagnose-codex`는 `data/`를 생성하고 임시 파일을 쓰고 지워 쓰기 가능 여부를 검사합니다. `diagnose-codex --fix`, `config-codex set`, `setup-codex`는 쓰기 작업입니다. `setup-codex --dry-run`으로 계획을 먼저 확인할 수 있습니다. `doctor-codex`의 성공은 실제 Stop hook 실행 성공을 입증하지 않습니다.

Hermes에서는 `/harness`의 경로와 import 오류를 확인합니다. 설치 진단:

```bash
agent-context-substrate doctor --hermes-home '<HERMES_HOME>' --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>' --hermes-agent-root '<HERMES_AGENT_ROOT>' --fail-on-issues
```

## 기본 처리: packet-only

Hermes finalize 기본값은 `packet-only`입니다. Codex finalize도 packet-only로 실행됩니다. raw export, context packet, lint report, recovery JSON과 ledger를 만들며 curated wiki page를 자동 승격하지 않습니다. 완료 상태와 별개로 lint issue가 남을 수 있으므로 보고서를 확인합니다.

Codex의 한 thread를 수동 처리하려면:

```bash
agent-context-substrate codex-finalize --thread-id '<THREAD_ID>' --codex-home '<CODEX_HOME>' --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>'
```

Hermes는 `/packet <session_id>`로 처리합니다. 자동 finalize 기본 필터는 메시지 3개 이상, source `telegram` 또는 `cli`입니다. `/harness`에서 실제 필터와 `auto_finalize_enabled`를 확인합니다. gateway source는 기본 허용 목록에 없으며 정책 기본값은 `trigger-only`입니다.

Hermes raw export만 필요하면 `extract-session --session-id '<SESSION_ID>' --project-root '<PROJECT_ROOT>'`를 사용합니다. `build-context-packet`은 raw/packet을 만들지만 finalize의 ledger/recovery 완료를 대신하지 않습니다. 필요한 메타데이터 옵션은 해당 명령의 `--help`에서 확인합니다.

`run-e2e-pipeline`과 legacy promotion 명령은 `queries/`, `concepts/`, `plans/`, `architectures/`를 씁니다. 임시 wiki에서 먼저 검토합니다. `apply-wiki-patch`는 기본 dry-run이며 `--apply`를 지정해야 page를 씁니다.

## Stop hook과 watcher fallback

설치된 Codex hook은 `Stop` 이벤트의 `session_id`를 사용합니다. `cwd`가 설정된 `project_root` 밖이면 건너뜁니다. hook trust는 Codex의 `/hooks`에서 검토합니다. 설치 상태만으로 trust나 실행 여부를 판단하지 않습니다.

hook 실패/timeout은 대화를 막지 않고 `continue: true`와 오류 메시지를 반환합니다. 기본 timeout은 110초입니다. `data/index/codex_hook_events.jsonl`의 `skipped`, `failed`, `finalized` 이벤트와 detail을 확인합니다. `finalized`여도 lint report는 별도로 확인합니다.

`watcher_fallback=available`은 실행 중이라는 뜻이 아닙니다. 운영자가 watcher를 직접 시작해야 합니다:

```bash
agent-context-substrate codex-watch --codex-home '<CODEX_HOME>' --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>' --once
```

`--once` 없이 실행하면 기본 15초 간격으로, rollout 수정 후 90초 이상 지난 thread를 처리합니다. 이 명령은 여러 idle thread의 artifact를 쓸 수 있습니다. watcher는 rollout 경로, 수정 시각과 크기를 저장해 동일 fingerprint를 건너뜁니다. 처리 중 파일이 바뀌면 processed로 기록하지 않습니다. hook 성공도 watcher 상태 기록을 시도합니다.

watcher 처리 예외는 밖으로 전파되어 실행을 종료할 수 있습니다. 자동 재시작 서비스가 설치된다고 가정하지 말고 오류를 해결한 뒤 다시 실행합니다. 수동 `codex-finalize`는 재실행 시 같은 thread artifact를 다시 씁니다.

## 실패와 재시도

| 증상 | 진단과 조치 |
| --- | --- |
| unknown session/thread | ID와 source 홈 확인; Codex는 `codex-status`의 rollout 경로 확인, Hermes는 올바른 profile의 `state.db` 확인 |
| CLI를 찾지 못함 | 가상환경 활성화와 `python -m pip show agent-context-substrate` 확인; 동일 interpreter의 `python -m agent_context_substrate.cli --help`로 비교 |
| `/harness` degraded | `project_root_exists`, `wiki_root_exists`, `harness_importable`, `harness_import_error` 확인; plugin은 설정된 `project_root/src` 안에서 import해야 함 |
| hook가 아무 artifact도 만들지 않음 | trust, 설치된 `local_config.json`, interpreter, `cwd` 범위와 hook event detail 확인 |
| ledger failed | `session_finalize` 레코드의 `last_error`, `attempt_count`, `artifact_paths`와 실제 파일을 함께 확인 |
| retrieval hit 없음 | 동일한 project/wiki root로 검색했는지 확인; packet과 recovery 파일 존재 여부 확인 |

Hermes finalize는 완료 artifact가 존재하고 promotion/summary/judge 모드가 같으면 재사용합니다. 실패 기록은 기본 3회 누적 실패 후 `PipelineRetryExhaustedError`로 차단됩니다. Codex finalize에는 이 retry budget이나 완료 artifact 재사용 검사와 같은 제한이 없습니다.

retry budget을 소진하면 먼저 원인을 해결하고 ledger와 관련 artifact를 백업합니다. CLI에 retry-reset 명령은 없습니다. 필요할 때 writer를 멈춘 뒤 해당 `session_finalize` 세션 레코드만 수동 복구하고 변경 내역을 남깁니다. 전체 ledger 삭제를 일상적인 재시도 방법으로 사용하지 않습니다.

LLM/custom summary 모드는 opt-in입니다. backend 오류나 응답 검증 실패 시 heuristic fallback을 사용할 수 있으므로 summary의 `metadata` 필드에서 `fallback_from`, `fallback_reason`을 확인합니다. packet이 존재한다는 사실만으로 모델 요약 성공을 판단하지 않습니다.

## Wiki lint와 retrieval

wiki lint는 wiki를 읽고 ACS 루트에 보고서를 씁니다. Bash 예시:

```bash
WIKI_PATH='<WIKI_ROOT>' agent-context-substrate lint-wiki --project-root '<PROJECT_ROOT>' --report-id operations-check --fail-on-issues
agent-context-substrate search-knowledge --query '<QUERY>' --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>' --json
agent-context-substrate expand-hit --hit-id '<HIT_ID>' --project-root '<PROJECT_ROOT>' --wiki-root '<WIKI_ROOT>' --json
```

PowerShell에서는 `$env:WIKI_PATH = '<WIKI_ROOT>'` 설정 후 lint 명령을 실행하고 필요하면 이전 값을 복원합니다. `--fail-on-issues` 없이는 lint issue가 있어도 exit code가 0일 수 있습니다. `--semantic`은 promotion/wiki patch/atom 검사도 추가합니다.

보고서에서 provenance, index 등록, orphan, broken wikilink, numeric/session-ID/test page, 언어와 internal graph 문제를 확인합니다. 원천 근거와 실제 page title에 맞춰 수정하고 다시 lint합니다. active page는 `lang: ko` 또는 `lang: en`을 사용합니다. `_system/config.yaml`과 `_system/templates/ko`, `_system/templates/en`도 확인합니다. archive 제외 규칙은 [pipeline](PIPELINE.md)과 lint source를 참고합니다.

검색은 기본 raw 메시지를 포함하지 않습니다. `--include-raw`를 사용하면 raw Hermes source도 조회할 수 있습니다. wiki/packet/recovery 등 반환된 `hit_id`를 expand에 전달해 실제 내용과 provenance를 확인합니다. raw message hit는 expansion이 비활성화되어 있으므로 snippet과 provenance를 사용합니다.

## 백업, 저장소와 복구

출력은 `<PROJECT_ROOT>/data/` 아래에 저장됩니다:

```text
exports/<session_id>.json                     # Hermes raw
exports/raw/codex/<thread_id>.json             # Codex raw
exports/context_packets/<packet_id>.json, <packet_id>.md
exports/lint/<report_id>.json, <report_id>.md
exports/recovery/<session_id>.json
index/session_ledger.json
index/codex_watcher_state.json
index/codex_hook_events.jsonl
```

선택한 기능에 따라 `data/atoms/`, `promotions/`, `wiki_patches/`, `cache/` 등도 사용합니다. raw, 요약, lint/recovery 파일에는 대화, tool output, 로컬 경로와 민감한 정보가 포함될 수 있습니다. 공개 repo와 release asset에서 제외하고 `.gitignore`와 staged diff를 확인합니다.

설치/overwrite 전에는 wiki, ACS `data/`, runtime config, Codex `hooks.json`, plugin local config와 marketplace 설정을 별도 백업합니다. DB는 writer를 멈추거나 SQLite backup 방식으로 일관된 복사본을 만듭니다. 실행 중인 SQLite의 본체 파일만 복사해 완전한 백업이라고 간주하지 않습니다.

installer의 overwrite 백업 경로는 Hermes/Codex plugin의 경우 `<HOME>/_backups/plugins/`, context engine의 경우 `<HERMES_AGENT_ROOT>/plugins/context_engine/_backups/`입니다. 출력된 `backup_path`를 확인합니다. 이것이 wiki, DB나 모든 사용자 설정의 백업을 대신하지는 않습니다.

복구할 때 hook/watcher와 gateway writer를 멈추고 관련 설정, artifact와 index를 일관되게 복원합니다. ledger는 artifact 경로를 저장하므로 이동 후에도 경로가 유효한지 확인합니다. 같은 루트에 여러 writer를 동시에 실행하지 않습니다. Hermes module cache를 갱신해야 하면 메시징 중단이 가능한 시점에 gateway를 재시작합니다.

임시 smoke root, 중복 lint report와 cache는 용도를 확인한 뒤 정리합니다. 기본 자동 보존 기간이나 storage quota가 있다고 가정하지 않습니다. 사용량을 모니터링하고 packet/recovery/raw/index를 함께 보존합니다. 디버깅 중에는 오류 로그와 해당 packet/report를 같이 남깁니다.

## 운영 완료 확인

- 의도한 source와 ID를 처리했고 경로/packet-only 정책이 맞는가.
- raw, packet, recovery 파일이 있으며 ledger의 상태와 오류를 확인했는가.
- 완료 상태와 별개로 lint issue, fallback 여부와 retrieval 내용을 검토했는가.
- hook 실행 또는 watcher 실행을 실제 증거로 확인했는가.
- private artifact와 백업이 공개 배포에 섞이지 않았는가.

명령과 동작의 근거: [CLI](../src/agent_context_substrate/cli.py), [paths](../src/agent_context_substrate/paths.py), [Hermes finalize](../src/agent_context_substrate/integration.py), [Codex finalize/watch](../src/agent_context_substrate/codex_integration.py), [installer/smoke](../src/agent_context_substrate/distribution.py).
