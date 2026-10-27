# Claude Code 설치

[English](./CLAUDE_CODE_SETUP.md) · [README](../README.ko.md) · [Windows Codex 설치](./WINDOWS_CODEX_APP_SETUP.ko.md)

Claude Code 어댑터는 Codex와 같은 흐름으로 동작합니다. **Stop hook → durable queue → singleton worker → wiki와 검색 artifact** 순서입니다. `claude` CLI와 Claude 데스크톱 앱 Code 탭 모두 `~/.claude`에서 plugin과 hook을 읽으므로 둘 다 지원합니다.

## 동작 방식

1. Claude Code는 매 턴이 끝날 때 plugin의 Stop hook을 실행하고 stdin으로 `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `stop_hook_active`를 넘깁니다.
2. `hooks/claude_stop_finalize.py`는 `stop_hook_active`가 true면 아무것도 하지 않습니다. 그 외에는 transcript fingerprint(경로, mtime, 크기)를 `<PROJECT_ROOT>/data/index/claude_jobs.sqlite3`에 기록하고, 숨김 `claude-worker`를 띄운 뒤 `{"continue": true, "suppressOutput": true}`를 출력합니다. 턴을 절대 막지 않으며, 오류는 `systemMessage` 경고로만 보입니다.
3. worker는 `claude-finalize`를 실행합니다. `~/.claude/projects/<인코딩된 cwd>/<session_id>.jsonl`을 `SessionBundle`로 변환하고(user/assistant 텍스트, tool 호출, tool 결과만 남기고 thinking·meta·sidechain은 버림), 공통 finalize 파이프라인(raw export, context packet, v2 요약, judge 기반 wiki 쓰기, lint, recovery brief)을 돌립니다.
4. 같은 세션의 새 Stop은 대기 중인 이전 job을 대체합니다. worker는 finalize 전후로 fingerprint와 config digest를 다시 확인하고, 일시 오류는 재시도하며, 재시도를 다 쓴 job은 dead-letter로 옮깁니다. Claude와 Codex worker는 `codex_finalize.lock`을 공유하므로 wiki는 한 번에 한 어댑터만 씁니다.

요약은 설정된 LLM backend를 씁니다. `summary_mode=auto`면 `codex_cli_command`에 지정된 Codex CLI를 쓰고, 실패하면 heuristic으로 대체합니다.

## 1. 어댑터 설정 만들기

marketplace 설치는 plugin을 `~/.claude/plugins/cache`로 복사하고 업데이트 때 교체하므로, 설정은 plugin 밖에 둡니다.

```text
~/.claude/agent-context-substrate/local_config.json
```

ACS 체크아웃에서 미리 보기로 확인한 뒤 실제로 씁니다.

```bash
agent-context-substrate setup-claude --project-root .
agent-context-substrate setup-claude --project-root . --yes
```

Codex ACS 설정이 있으면 `setup-claude`가 요약·wiki·worker·workspace 정책을 그대로 복사해서 두 agent가 같은 방식으로 동작합니다. 기본값에서 시작하려면 `--from-codex off`, 다른 vault를 쓰려면 `--wiki-root PATH`를 주세요. `ACS_CLAUDE_CONFIG` 환경변수로 설정 경로를 바꿀 수 있습니다. `setup-claude`는 `~/.claude/settings.json`을 수정하지 않습니다.

## 2. 로컬 marketplace로 plugin 설치

패키지 assets 폴더가 `acs-local`이라는 로컬 marketplace입니다.

```text
<ACS_CHECKOUT>/src/agent_context_substrate/assets/claude_plugin/
  .claude-plugin/marketplace.json
  agent-context-substrate/
    .claude-plugin/plugin.json
    hooks/hooks.json
    hooks/claude_stop_finalize.py
    skills/agent-context-substrate/SKILL.md
```

`claude` 대화형 세션에서:

```text
/plugin marketplace add <ACS_CHECKOUT>/src/agent_context_substrate/assets/claude_plugin
/plugin install agent-context-substrate@acs-local
```

CLI가 없으면(예: 데스크톱 앱만 설치된 경우) `~/.claude/settings.json`에 같은 항목을 직접 추가하고 앱을 재시작하세요.

```json
{
  "extraKnownMarketplaces": {
    "acs-local": {
      "source": {
        "source": "directory",
        "path": "C:/Users/<사용자>/path/to/agent-context-substrate/src/agent_context_substrate/assets/claude_plugin"
      }
    }
  },
  "enabledPlugins": {
    "agent-context-substrate@acs-local": true
  }
}
```

기존 파일을 덮어쓰지 말고 이 키들만 합쳐 넣으세요.

hook 명령은 `python "${CLAUDE_PLUGIN_ROOT}/hooks/claude_stop_finalize.py"`이므로, Claude Code가 hook을 돌리는 셸의 `PATH`에 `python`이 있어야 합니다. 이 스크립트는 부트스트랩 역할만 합니다. 설정의 `python_path_entries`를 `sys.path`에 넣고 editable ACS 패키지를 import하므로, 핵심 Python 코드를 바꿔도 재설치할 필요가 없습니다. 번들된 hook이나 skill 파일을 바꿨다면 `/plugin marketplace update acs-local`을 실행하세요.

## 3. 확인

```bash
agent-context-substrate claude-status
agent-context-substrate claude-jobs list
```

Stop 후 `claude_hook_events.jsonl`에 `enqueued`, 이어서 `finalized`가 찍히고, `claude-status`가 `worker_status=idle`, `queue_pending_count=0`을 보여야 합니다.

dead-letter job 처리:

```bash
agent-context-substrate claude-jobs list --status dead_letter
agent-context-substrate claude-jobs retry --job-id ID
agent-context-substrate claude-worker
```

세션 하나를 직접 finalize:

```bash
agent-context-substrate claude-finalize --session-id SESSION_ID --project-root . --wiki-root "$WIKI_PATH" --summary-mode auto
```

## 파일

| 경로 | 용도 |
| --- | --- |
| `data/index/claude_jobs.sqlite3` | Claude durable job 큐 |
| `data/index/claude_hook_events.jsonl` | hook과 worker 판단 로그 |
| `data/index/claude_worker_status.json` | worker heartbeat |
| `data/exports/raw/claude/<session_id>.json` | redaction된 raw 세션 export |
| `data/exports/context_packets/<session_id>.json` | context packet (provenance `claude-session:<id>#messages=…`) |

## 설정 키

Claude 전용 키입니다. 나머지(`summary_*`, `wiki_*`, `worker_*`, `llm_*`, `workspace_scope`, `allowed_workspace_roots`, `python_path_entries`)는 Codex 설정과 의미가 같습니다.

| 키 | 의미 |
| --- | --- |
| `project_root` | ACS artifact 루트 (`data/`가 여기 생김) |
| `claude_home` | session id로 transcript를 찾을 Claude 설정 폴더 |
| `python_executable` | worker와 `claude-finalize`를 실행할 Python |
| `trigger_strategy` | `hook-enqueue`(기본) 또는 `hook-primary`(hook 안에서 바로 finalize) |
| `claude_hook_event_log_path` | 이벤트 로그 경로 덮어쓰기(선택) |
