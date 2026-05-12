# Agent Context Substrate 운영 가이드

이 문서는 `agent-context-substrate`를 실제로 돌릴 때 필요한 운영 기준과 런북입니다.

## 1. 운영 목표

현재 운영 목표는 다음입니다.

> Hermes session을 재현 가능한 packet/recovery/retrieval artifact로 정리하고, Obsidian vault는 사람용 semantic wiki로 유지한다.

운영자가 보장해야 할 것:

1. 입력 경로가 올바르다. (`HERMES_HOME/state.db`, `WIKI_PATH`, `--project-root`)
2. `packet-only` 기본 정책이 유지된다.
3. artifact가 `data/exports/`와 ledger에 남는다.
4. 실제 Obsidian active graph는 lint상 깨끗하다.
5. 언어 설정(`lang: ko|en`)이 active page에 적용된다.

## 2. 실행 전 체크리스트

### 필수 준비물

- Python 3.11+
- Hermes 세션 DB (`HERMES_HOME/state.db`)
- Agent Context Substrate project root
- Obsidian LLM Wiki vault

### 권장 초기화

```bash
cd '<PROJECT_ROOT>'
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
python -m pytest -q
```

### packaged integration install

기존 live Hermes 환경에 설치할 때는 먼저 설정과 plugin/context-engine directory를 백업한 뒤 packaged installer를 실행합니다.

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

설치 후 Hermes에서 `agent-context-substrate` plugin을 enable하고 `context.engine: agent_context_substrate`를 선택합니다. 이미 실행 중인 Telegram gateway는 module cache 때문에 restart가 필요할 수 있습니다.

### fresh install smoke

배포 검증은 temp root로 먼저 수행합니다.

```bash
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

성공 기준:

```text
fresh-install-smoke ok=True
lint_issue_count=0
retrieval_hit_count>0
expanded_content_length>0
```

### 환경 변수 확인

```bash
echo "$HERMES_HOME"
echo "$WIKI_PATH"
echo "$AGENT_CONTEXT_SUBSTRATE_PROMOTION_MODE"
```

기본값:

```text
HERMES_HOME=~/.hermes
WIKI_PATH=~/wiki
AGENT_CONTEXT_SUBSTRATE_PROMOTION_MODE=packet-only
```


## 2.1 현재 검증된 기준선

v0.2.0 로컬 release candidate 기준으로 확인된 운영 기준선입니다.

| 항목 | 결과 |
| --- | --- |
| GitHub remote | `origin/main` → `jjuck/agent-context-substrate` |
| Project tests | `216 passed` |
| Fresh install smoke | `ok=True`, `retrieval_hit_count=1`, `expanded_content_length=14195`, `lint_issue_count=0` |
| Real wiki lint | `checked_pages=15`, `missing_provenance=0`, `orphan_pages=0`, `missing_from_index=0`, `broken_wikilinks=0` |
| Live runtime | plugin `agent-context-substrate`, context engine `agent_context_substrate`, gateway running |

이 표는 운영 기준선입니다. installer, context-engine, plugin, lint, retrieval을 바꾸면 다시 갱신하세요.

## 3. 경로 기준

### 입력

```text
Hermes DB: HERMES_HOME/state.db
session_id: CLI 인자 또는 plugin hook에서 전달
```

### Harness 출력

```text
data/exports/<session_id>.json
data/exports/context_packets/<packet_id>.json
data/exports/context_packets/<packet_id>.md
data/exports/lint/<report_id>.json
data/exports/lint/<report_id>.md
data/exports/recovery/<session_id>.json
data/index/session_ledger.json
```

### Obsidian vault

현재 사용자 vault:

```text
<WIKI_ROOT>
```

권장 active structure:

```text
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

## 4. 표준 운영 모드

### 4.1 Raw export만 필요한 경우

```bash
agent-context-substrate extract-session \
  --session-id <session_id> \
  --project-root .
```

확인:

- `data/exports/<session_id>.json` 생성
- JSON 안에 `session`, `messages`, `slice`, `message_count` 존재

### 4.2 Context packet까지만 만드는 경우

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

확인:

- raw export JSON 생성
- packet JSON/Markdown 생성
- stdout에 `micro_summaries=...`, `unit_summaries=...`, `critical_files=...` 출력

### 4.3 Session finalize 기본 운영

Hermes plugin의 `/new` 또는 `/packet <session_id>` 경로는 기본적으로 `packet-only`를 사용합니다.

생성:

- raw export
- context packet
- lint report
- recovery brief
- ledger record

생성하지 않음:

- `queries/`
- `concepts/`
- `plans/`
- `architectures/`

### 4.4 Legacy full promotion이 필요한 경우

실제 human-facing vault가 아니라 임시 wiki에서 먼저 실행하세요.

```bash
TMP_WIKI=$(mktemp -d)
export WIKI_PATH="$TMP_WIKI"

agent-context-substrate run-e2e-pipeline \
  --session-id <session_id> \
  --packet-id <packet_id> \
  --task-title "<task title>" \
  --macro-context "<macro context>" \
  --unit-title "<unit title>" \
  --goal "<goal>" \
  --report-id <report_id> \
  --project-root .
```

주의:

- `run-e2e-pipeline`은 legacy query/concept/plan/architecture page를 생성합니다.
- live vault 기본 운영에는 `packet-only`가 더 안전합니다.

## 5. 언어 설정 운영법

### 5.1 Vault config 확인

```bash
python - <<'PY'
from pathlib import Path
print(Path('<WIKI_ROOT>/_system/config.yaml').read_text(encoding='utf-8'))
PY
```

기대값:

```yaml
wiki:
  default_language: ko
  supported_languages: [ko, en]
  filename_language: ko
  template_language: ko
  source_language_preserve: true
```

### 5.2 Active page 작성 기준

모든 active human-facing page에 아래 중 하나를 둡니다.

```yaml
lang: ko
```

또는:

```yaml
lang: en
```

### 5.3 Template 사용 기준

```text
_system/templates/ko/<type>.md
_system/templates/en/<type>.md
```

새 page를 만들 때 `template_language`를 우선 사용하고, 원천 자료가 영어이면 source card에는 `lang: en`을 사용할 수 있습니다.

### 5.4 언어 lint

```bash
agent-context-substrate lint-wiki \
  --project-root . \
  --report-id language-check
```

문제 항목:

- `missing_lang_pages`
- `unsupported_lang_pages`

## 6. Lint 해석 기준

### Structural graph

| 항목 | 의미 | 기준 |
| --- | --- | --- |
| `missing_provenance_pages` | provenance 누락 | active page는 provenance 또는 sources를 가져야 함 |
| `orphan_pages` | inbound link 없음 | 가능하면 0 |
| `pages_missing_from_index` | `index.md` 누락 | 현재 harness lint 호환을 위해 0 유지 |
| `broken_wikilinks` | 존재하지 않는 target | 반드시 0 |

### Human-facing quality

| 항목 | 의미 | 기준 |
| --- | --- | --- |
| `numeric_slug_pages` | `7.md` 같은 page | active graph에서 금지 |
| `session_id_slug_pages` | session id page | active graph에서 금지 |
| `generated_summary_only_pages` | 자동 요약만 있는 page | active graph에서 금지 |
| `smoke_or_test_pages` | 검증/임시 page | active graph에서 금지 |
| `missing_lang_pages` | 언어 누락 | active graph에서 금지 |
| `unsupported_lang_pages` | `ko/en` 외 언어 | active graph에서 금지 |

### Internal artifact graph

- `micro_summaries_missing_parent_unit`
- `micro_summaries_with_unknown_parent_unit`
- `unit_summaries_with_missing_micro_references`
- `packet_micro_summaries_unreferenced`
- `packets_missing_raw_pointers`

## 7. 표준 검증 명령

### Harness full suite

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate
python -m pytest -q
```

### Real wiki lint

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate
.venv/bin/agent-context-substrate lint-wiki \
  --project-root '<PROJECT_ROOT>' \
  --report-id real-wiki-smoke
```

기대값:

```text
missing_provenance=0
orphan_pages=0
missing_from_index=0
broken_wikilinks=0
Human-facing quality issues=0
Internal graph issues=0
```

### Retrieval smoke

Hermes tool이 활성화되어 있으면:

```text
wiki_knowledge_search("Agent Context Substrate Context Packet")
```

기대:

- `04 프로젝트/Agent Context Substrate.md` 같은 human-facing wiki hit
- context packet artifact hit

## 8. privacy / release 운영 기준

배포 또는 commit 전에는 아래를 확인합니다.

- `data/exports/`, `data/index/session_ledger.json`, temp wiki directory는 private/generated artifact로 취급합니다.
- raw `state.db` export에는 전체 메시지와 tool output이 포함될 수 있습니다.
- lint/recovery/context packet markdown도 민감한 요약이나 파일 경로를 포함할 수 있습니다.
- API key, token, password, connection string, `.env`는 절대 commit하지 않습니다.
- `.gitignore`가 generated artifact를 제외하는지 확인하고 `git status --short`를 검토합니다.
- public release 전에는 `docs/RELEASE_CHECKLIST.md`를 따라 `doctor`, `fresh-install-smoke`, real wiki lint를 모두 통과시킵니다.

## 9. 장애 대응 런북

### 9.1 `Unknown session_id`

원인:

- session id 오타
- 잘못된 `HERMES_HOME`
- 다른 Hermes profile의 DB를 보고 있음

대응:

```bash
echo "$HERMES_HOME"
test -f "$HERMES_HOME/state.db" && echo ok || echo missing
```

### 9.2 CLI 명령을 찾지 못함

```bash
cd '<PROJECT_ROOT>'
. .venv/bin/activate
pip install -e '.[dev]'
.venv/bin/agent-context-substrate --help
```

### 9.3 `/harness`가 `degraded`

확인:

- `project_root exists`
- `wiki_root exists`
- `harness_importable`
- `harness_import_error`

대응:

- `AGENT_CONTEXT_SUBSTRATE_PROJECT_ROOT`가 실제 project root인지 확인
- `src/agent_context_substrate`가 존재하는지 확인
- gateway 재시작 필요 여부 확인

### 9.4 언어 lint 실패

증상:

```text
Missing language
Unsupported language
```

대응:

1. report에서 page path 확인
2. frontmatter에 `lang: ko` 또는 `lang: en` 추가
3. 다시 `lint-wiki` 실행

### 9.5 broken wikilink

대응:

- link target page를 생성하거나
- wikilink를 실제 page title/stem에 맞게 수정하거나
- legacy/generated page link라면 active page에서 제거하고 archive로 이동

### 9.6 WSL + 한글 Windows 경로 문제

권장 패턴:

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest -q
```

`terminal(workdir=...)`에 `/mnt/<drive>/Users/<windows-user>/...`를 넣는 방식은 피합니다.

## 10. 보존 / 정리 기준

보존 가치 높음:

- `data/exports/context_packets/*.json`
- `data/exports/recovery/*.json`
- `data/index/session_ledger.json`
- 실제 Obsidian curated pages

정리 가능:

- 오래된 temp wiki smoke directory
- 중복 lint report
- `data/exports/tmp-*-wiki/`

단, 디버깅 중이면 관련 lint report와 packet JSON은 함께 보존하세요.

## 11. 운영자용 최소 체크리스트

- [ ] 원하는 `session_id`를 읽었는가
- [ ] `promotion_mode`가 의도대로인가 (`packet-only` 권장)
- [ ] raw export와 packet artifact가 생성됐는가
- [ ] recovery JSON이 생성됐는가
- [ ] ledger가 completed 상태인가
- [ ] real wiki lint가 깨끗한가
- [ ] active page에 `lang`이 있는가
- [ ] generated/session-id/numeric page가 active graph에 없는가
