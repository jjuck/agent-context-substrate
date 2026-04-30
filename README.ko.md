<div align="center">

# Agent Context Substrate

**Hermes 대화 기록을 다시 찾고, 이어서 작업하고, 필요할 때 검색할 수 있는 개인 지식층으로 바꾸는 도구입니다.**

![Status](https://img.shields.io/badge/status-private%20alpha-orange) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) [![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

[English README](./README.md) · [빠른 시작](#빠른-시작) · [Hermes에 설치](#hermes에-설치) · [검증된 기준선](#검증된-기준선) · [사용자 가이드](./docs/USER_GUIDE.md) · [운영 가이드](./docs/OPERATIONS.md)

</div>

## 한 줄로 말하면

`agent-context-substrate`는 Hermes Agent가 나눈 긴 대화를 그냥 흘려보내지 않고, 나중에 다시 쓸 수 있는 **요약 파일, 복구 브리프, 검색 가능한 지식 자료**로 정리해주는 Python CLI 도구입니다.

현재 packaged adapter는 **Hermes Agent만 지원**합니다. 이름을 `Agent Context Substrate`로 바꾼 이유는 장기적으로 Claude Code, Codex, OpenCode, Gemini 같은 다른 agent adapter도 붙일 수 있는 구조로 확장하기 위해서입니다. 이 프로젝트의 이전 이름은 `hermes-llm-wiki-harness`였습니다.

Hermes는 `~/.hermes/state.db`에 대화 기록을 저장합니다. 이 하네스는 그 기록을 읽어서 다음을 만듭니다.

```text
Hermes 대화 DB
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

- 이전 Hermes 세션을 `context packet`으로 정리할 수 있습니다.
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

## 빠른 사실

| 항목 | 값 |
| --- | --- |
| 상태 | Private alpha; GitHub private repo 동기화 완료; public release checklist는 아직 남음 |
| 실행 환경 | Python 3.11+ |
| 주 인터페이스 | CLI: `agent-context-substrate` |
| 현재 agent 지원 | Hermes Agent only |
| Hermes 연동 | user plugin `agent-context-substrate` + context engine `agent_context_substrate` |
| 장기 확장 방향 | Claude Code, Codex, OpenCode, Gemini 등은 추후 adapter로 추가 가능하나 아직 packaged support는 없음 |
| 기본 산출물 | `data/exports/`, `data/index/session_ledger.json` |
| 기본 promotion mode | `packet-only` |
| Obsidian 역할 | 사람이 읽는 semantic wiki |
| 지원 wiki 언어 | `ko`, `en` |
| 라이선스 | MIT |

## 빠른 시작

```bash
git clone https://github.com/jjuck/agent-context-substrate.git agent-context-substrate
cd agent-context-substrate
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
python -m pytest -q
.venv/bin/agent-context-substrate --help
```

기대 결과:

```text
64 passed
```

그리고 `--help`에 다음 명령들이 보여야 합니다.

```text
init-wiki
install-plugin
install-context-engine
doctor
fresh-install-smoke
extract-session
build-context-packet
lint-wiki
```

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
expanded_content_length=5291
lint_issue_count=0
```

## 검증된 기준선

현재 private baseline은 rename 이후 repo와 package-managed integration 경로에서 검증되었습니다.

| 항목 | 현재 결과 |
| --- | --- |
| 프로젝트 테스트 | `64 passed` |
| Fresh install smoke | `fresh-install-smoke ok=True`, `retrieval_hit_count=1`, `expanded_content_length=5291`, `lint_issue_count=0` |
| 실제 wiki lint | `checked_pages=15`, `missing_provenance=0`, `orphan_pages=0`, `missing_from_index=0`, `broken_wikilinks=0` |
| Live Hermes 연결 | plugin `agent-context-substrate`, context engine `agent_context_substrate`, retrieval tools 로드됨 |
| GitHub sync | `main`이 `jjuck/agent-context-substrate`에 push됨 |

release를 자르거나 installer/runtime 동작을 바꾸면 이 기준선을 다시 갱신하세요.

## 자주 쓰는 명령

| 명령 | 설명 |
| --- | --- |
| `extract-session` | Hermes 세션 하나를 raw JSON으로 export합니다. |
| `build-context-packet` | raw export와 context packet을 생성합니다. |
| `lint-wiki` | Obsidian wiki와 packet artifact graph를 검사합니다. |
| `init-wiki` | human-facing wiki 폴더와 설정을 초기화합니다. |
| `install-plugin` | Hermes user plugin을 packaged asset에서 설치합니다. |
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

노출 도구:

```text
wiki_recovery_context
wiki_knowledge_search
wiki_knowledge_expand
```

검색은 read-only입니다. 검색만으로 Obsidian 문서가 수정되지는 않습니다.

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

## 개인정보와 안전

이 프로젝트는 민감한 로컬 데이터를 다룹니다.

- `~/.hermes/state.db`에는 전체 대화, tool output, 파일 경로, 운영 메모가 들어갈 수 있습니다.
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

- 아직 private alpha입니다. release checklist와 privacy review가 끝날 때까지 repo는 private로 유지하는 것을 권장합니다.
- 새 human-facing folders(`01 지식`, `04 프로젝트` 등)로의 curated promotion은 완전 자동화되지 않았습니다.
- legacy full promotion은 여전히 `queries/`, `concepts/`, `plans/`, `architectures/` 경로를 사용합니다.
- Hermes gateway는 plugin/context-engine 변경 뒤 재시작이 필요할 수 있습니다.
