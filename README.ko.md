# Agent Context Substrate

**Hermes와 Codex 세션을 복구 가능한 context, 검색 가능한 artifact, 근거 기반의 살아 있는 Markdown wiki로 바꿉니다.**

[English README](./README.md) | [문서 지도](./docs/README.md) | [사용자 가이드](./docs/USER_GUIDE.md) | [Windows Codex 설치](./docs/WINDOWS_CODEX_APP_SETUP.ko.md)

## 무엇을 하는가

ACS는 로컬 agent session 저장소를 수정하지 않고 읽어서 다음 context 계층을 만듭니다.

- provenance가 있는 raw session export
- compact context packet과 recovery brief
- deterministic fallback을 갖춘 evidence-backed V2 summary
- claim atom과 promotion candidate
- 감사 가능한 wiki patch proposal과 write decision
- knowledge, recovery, graph read-only 검색
- lint, ledger, hook event artifact

현재 packaged adapter는 Hermes Agent와 Windows Codex 앱을 지원합니다. 각 adapter가 typed `SessionBundle`을 만든 뒤에는 공통 pipeline을 사용합니다.

## Codex 기본 동작

새 Codex 설치의 기본값:

```text
summary_mode=auto
wiki_auto_mode=apply-flexible
wiki_write_judge_mode=auto
wiki_auto_min_score=0.85
workspace_scope=all
```

eligible Codex thread가 종료되면 ACS는 다음 흐름을 실행합니다.

```text
Codex rollout
  -> typed SessionBundle
  -> context packet + evidence-backed summary
  -> atoms + promotion candidates
  -> flexible wiki patch proposal
  -> write judge 판단과 candidate 선택
  -> guarded transaction 또는 review artifact
  -> lint + recovery + ledger
```

Judge는 지식이 durable한지 판단하고 적용할 정확한 candidate ID를 선택합니다. 실제 write 단계는 evidence, safe path, operation type, 현재 page hash를 다시 확인합니다. Judge 실패나 낮은 점수는 vault write로 이어지지 않습니다.

## 살아 있는 Wiki 모델

기본 wiki 정책은 `emergent-root`입니다.

- 새 automatic flexible write는 vault root의 `<Title>.md`를 target으로 합니다.
- folder path는 저장 위치일 뿐 의미 taxonomy가 아닙니다.
- 의미는 `type`, optional `category`, `sources`, wikilink, index/MOC가 담당합니다.
- 새로운 category는 write를 차단하지 않습니다.
- category와 type은 enum이 아닌 열린 vocabulary입니다.
- `context packet`처럼 generic한 subject만으로 인공적인 canonical page를 만들지 않습니다.
- 기존 registry-folder vault는 명시적인 compatibility mode로 계속 지원합니다.

`init-wiki`는 LLM이 wiki를 성장시키는 데 필요한 최소 구조만 만듭니다.

```text
LLM Wiki/
  index.md
  log.md
  _system/
    config.yaml
    guides/
      wiki-principles.md
      ontology-seeds.md
    templates/
    styles/
```

## 빠른 시작

요구사항은 Python 3.11+와 Git입니다. runtime dependency는 Python 표준 라이브러리뿐입니다.

```bash
git clone https://github.com/jjuck/agent-context-substrate.git
cd agent-context-substrate
python -m venv .venv
```

Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

Linux, macOS, WSL:

```bash
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

## Windows Codex 설치

권장 설치 명령:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-codex-windows.ps1
```

이 스크립트는 환경 생성, 기본 wiki 초기화, plugin 및 personal marketplace/cache 설치, 가능한 경우 `agent-context-substrate@personal` registry 등록, 진단을 수행합니다.

기본 wiki config에는 사용자명이 들어간 absolute path 대신 `%USERPROFILE%\Documents\LLM Wiki` portable template을 저장합니다. Effective root 우선순위:

1. `AGENT_CONTEXT_SUBSTRATE_WIKI_ROOT`
2. `WIKI_PATH`
3. installed `local_config.json["wiki_root"]`
4. `%USERPROFILE%\Documents\LLM Wiki`

설치 후 Codex를 재시작하고 **Codex app -> Settings -> Hooks**(Codex 앱 -> 설정 -> 훅)에서 `agent-context-substrate` Stop hook을 확인하고 신뢰하세요. CLI/TUI에서는 `/hooks`를 사용할 수 있습니다. Hook trust는 Full Access(전체 권한), approval mode, sandbox 설정과 별개입니다.

검증:

```powershell
.\.venv\Scripts\agent-context-substrate.exe codex-status
.\.venv\Scripts\agent-context-substrate.exe doctor-codex --fail-on-issues
.\.venv\Scripts\agent-context-substrate.exe config-codex paths
```

예상 mode:

```text
hook_support=supported
hook_primary=installed
watcher_fallback=available
```

`project_root`는 ACS artifact root이지 workspace boundary가 아닙니다. 새 설치는 `workspace_scope="all"`을 사용합니다. 명시적인 제한이 필요한 경우에만 `workspace_scope="restricted"`와 `allowed_workspace_roots`를 설정하세요.

Hook 승인, smoke test, 진단, fallback은 [Windows Codex 앱 설치 가이드](./docs/WINDOWS_CODEX_APP_SETUP.ko.md)를 참고하세요.

## Hermes 설치

```bash
agent-context-substrate init-wiki --wiki-root '<WIKI_ROOT>'

agent-context-substrate install-plugin \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

agent-context-substrate install-context-engine \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --overwrite

agent-context-substrate doctor \
  --hermes-home ~/.hermes \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --hermes-agent-root '<HERMES_AGENT_ROOT>' \
  --fail-on-issues
```

Hermes/standalone finalize는 legacy full promotion을 명시하지 않는 한 `packet-only`입니다.

## 자주 쓰는 명령

```bash
# 전체 명령 확인
agent-context-substrate --help

# Codex thread 하나 finalize
agent-context-substrate codex-finalize \
  --thread-id '<THREAD_ID>' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --summary-mode auto \
  --wiki-auto-mode apply-flexible \
  --wiki-write-judge-mode auto

# read-only 검색
agent-context-substrate search-knowledge \
  --query '<QUERY>' \
  --mode knowledge \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>'

# 검색 결과 확장
agent-context-substrate expand-hit \
  --hit-id '<HIT_ID>' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>'

# wiki 검증
WIKI_PATH='<WIKI_ROOT>' agent-context-substrate lint-wiki \
  --project-root '<PROJECT_ROOT>' \
  --report-id manual-check \
  --fail-on-issues
```

수동 `apply-wiki-patch`는 기본 dry-run입니다. 실제 적용 시 `--apply`를 명시해야 하며 judge metadata와 mechanical safety gate는 계속 적용됩니다.

## Artifact

Machine-facing artifact는 `<PROJECT_ROOT>/data` 아래에 둡니다.

```text
data/
  exports/raw/
  exports/context_packets/
  exports/evidence/
  exports/summaries/
  exports/recovery/
  atoms/
  promotions/
  wiki_decisions/
  wiki_patches/
  index/
```

Wiki write는 별도로 resolve된 vault root에 반영됩니다. Non-dry-run에서는 page, index, log, promotion status, applied log를 복구 가능한 transaction으로 함께 처리합니다. `prepared` 상태에서 중단된 transaction은 다음 apply 전에 복구합니다.

## Lint 정책

Blocking issue는 provenance와 graph integrity를 보호합니다. 예: missing provenance, index 미등록, discoverability 부재, broken link, 내부 packet/summary 참조 오류.

언어, 권장 section, thin content, related-link 품질, registry mode의 category warning은 advisory입니다. Emergent-root mode에서는 새 category 자체를 문제로 보지 않습니다.

## 개인정보와 안전

- Hermes `state.db`, Codex SQLite/rollout, `data/exports`에는 private message, tool output, local path가 들어갈 수 있습니다.
- ACS는 원본 session store를 read-only로 읽습니다.
- Codex worker는 read-only sandbox, `approval_policy=never`, fast service tier, low reasoning effort, hooks-disabled로 실행됩니다.
- LLM input은 길이를 제한하며 secret, email, path, code block을 redact할 수 있습니다.
- credential, private export, local generated artifact를 commit하지 마세요.
- release 전에 `git status --short`를 확인하세요.

## 문서

- [문서 지도](./docs/README.md)
- [한국어 사용자 가이드](./docs/USER_GUIDE.md)
- [English User Guide](./docs/USER_GUIDE.en.md)
- [Windows Codex 설치](./docs/WINDOWS_CODEX_APP_SETUP.ko.md)
- [운영 가이드](./docs/OPERATIONS.md)
- [Pipeline과 아키텍처](./docs/PIPELINE.md)
- [Release checklist](./docs/RELEASE_CHECKLIST.md)
- [Changelog](./CHANGELOG.md)

## 상태

ACS는 alpha software이며 현재 release line은 `0.2.0`입니다. Legacy explicit promotion 명령과 기존 folder-based vault는 호환성을 위해 유지하지만, 권장 경로는 typed finalize artifact와 judge-gated emergent wiki growth입니다.
