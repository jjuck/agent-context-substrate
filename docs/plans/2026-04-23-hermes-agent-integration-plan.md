# Hermes Agent Integration Plan

> Current status document for integrating `agent-context-substrate` with Hermes Agent. This file is now a living status/roadmap document, not the original pre-implementation plan.

## Goal

`agent-context-substrate`를 standalone CLI에서 끝내지 않고 Hermes Agent의 session boundary, recovery, request-time retrieval 흐름에 붙인다.

최종 목표는 두 가지다.

1. **Session recovery**: reset/new 이후 raw transcript를 다시 읽지 않고 compact recovery brief로 이어가기
2. **Request-time knowledge layer**: 작업 중 필요할 때 agent가 wiki/packet/summary/raw evidence를 스스로 검색하기

## Current architecture

```text
Hermes state.db
  -> agent-context-substrate package
     -> raw export
     -> context packet
     -> lint report
     -> recovery brief
     -> ledger
     -> optional legacy full promotion

Hermes user plugin ~/.hermes/plugins/agent-context-substrate
  -> on_session_finalize hook
  -> /harness, /packet, /wiki-resume, /wiki-lint

Hermes context engine agent_context_substrate
  -> wiki_recovery_context
  -> wiki_knowledge_search
  -> wiki_knowledge_expand
```

## Completed

- [x] Function-oriented integration API: `integration.py`
- [x] Structured `IntegrationResult`
- [x] `run_session_finalize_pipeline(...)`
- [x] `should_process_session(...)`
- [x] JSON ledger: `data/index/session_ledger.json`
- [x] Retry/failure/idempotency handling
- [x] Recovery brief layer: `recovery.py`
- [x] Auto naming/policy helpers: `naming.py`, `policy.py`
- [x] Hermes user plugin: `~/.hermes/plugins/agent-context-substrate/`
- [x] Slash commands: `/harness`, `/packet`, `/wiki-resume`, `/wiki-lint`
- [x] Context engine prototype: `plugins/context_engine/agent_context_substrate/`
- [x] Request-time retrieval API: `retrieval.py`
- [x] `wiki_knowledge_search` / `wiki_knowledge_expand` tools
- [x] Gateway/session-lifecycle smoke with isolated roots
- [x] Active `context.engine: agent_context_substrate` config smoke
- [x] `packet-only` default finalize policy
- [x] qualitative human-facing lint
- [x] retrieval exclusion for `_system/`, `90 보관/`, dot folders
- [x] Obsidian human-facing vault rebuild with `ko/en` language policy

## Current defaults

```text
AGENT_CONTEXT_SUBSTRATE_PROMOTION_MODE=packet-only
AGENT_CONTEXT_SUBSTRATE_ALLOWED_SOURCES=telegram,cli
AGENT_CONTEXT_SUBSTRATE_GATEWAY_POLICY=trigger-only
AGENT_CONTEXT_SUBSTRATE_MIN_MESSAGE_COUNT=3
```

## Promotion policy

`run_session_finalize_pipeline(...)` currently supports:

| Mode | Status | Behavior |
| --- | --- | --- |
| `packet-only` | default | raw/packet/lint/recovery/ledger only |
| `full` | legacy explicit | query/concept/plan/architecture promotion |

Planned but not yet implemented API modes:

- `draft`
- `curated`

These should target human-facing folders such as `01 지식`, `04 프로젝트`, `06 원천 자료`, not legacy `concepts/queries/plans/architectures`.

## Language policy

The human-facing Obsidian vault uses:

```yaml
wiki:
  default_language: ko
  supported_languages: [ko, en]
  filename_language: ko
  template_language: ko
  source_language_preserve: true
```

Active human-facing pages must include:

```yaml
lang: ko # or en
```

Current implementation status:

- [x] Lint detects missing/unsupported `lang`
- [x] Vault templates exist under `_system/templates/ko` and `_system/templates/en`
- [x] Retrieval excludes `_system` templates by default
- [ ] Curated promotion does not yet render language-aware templates automatically

## Remaining implementation priorities

### 1. Curated promotion target model

Add a new model such as:

```python
@dataclass(frozen=True)
class CuratedPromotionTarget:
    category: Literal["knowledge", "idea", "person", "organization", "project", "plan", "source", "decision"]
    language: Literal["ko", "en"] = "ko"
    project: str | None = None
    title: str
    slug: str | None = None
    template: str | None = None
```

Requirements:

- `category="knowledge"` -> `01 지식/`
- `category="project"` -> `04 프로젝트/`
- `category="source"` -> `06 원천 자료/`
- `language` selects `ko/en` template
- frontmatter always includes `lang`
- numeric/session-id/generated pages are rejected

### 2. Language-aware template renderer

Add a module such as `wiki_templates.py`.

Responsibilities:

- read `_system/config.yaml`
- resolve folder mapping
- select `_system/templates/<lang>/<type>.md`
- render frontmatter and body placeholders
- validate supported languages

### 3. Source card ingest workflow

Add a user-facing workflow for:

- external article/repo/docs/video source card in `06 원천 자료`
- processed synthesis in `01 지식`
- project-specific references in `04 프로젝트/<Project>/관련 자료.md`

### 4. Context engine compression compatibility

Already verified:

- config selection
- recovery preload
- retrieval tool registration
- retrieval dispatch

Still needs a dedicated task before forcing compression:

- compatibility with Hermes compression counters/fields
- no duplicate recovery insertion
- safe fallback when recovery is absent

## Verification commands

Harness full suite:

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest -q
```

Hermes targeted suite:

```bash
cd '<HERMES_AGENT_ROOT>' && . venv/bin/activate && python -m pytest tests/plugins/test_agent_context_substrate_plugin.py tests/agent/test_agent_context_substrate_context_engine.py tests/run_agent/test_plugin_context_engine_init.py tests/agent/test_context_engine.py tests/gateway/test_session_boundary_hooks.py tests/cli/test_session_boundary_hooks.py -q
```

Real wiki lint:

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && .venv/bin/agent-context-substrate lint-wiki --project-root '<PROJECT_ROOT>' --report-id real-wiki-smoke
```

Expected real-vault quality after the human-facing rebuild:

```text
missing_provenance=0
orphan_pages=0
missing_from_index=0
broken_wikilinks=0
Human-facing quality issues=0
Internal graph issues=0
```

## Operational caution

Do not casually add `gateway` to `AGENT_CONTEXT_SUBSTRATE_ALLOWED_SOURCES`. Gateway hook platform and raw session source are different concepts. Telegram sessions can be processed through gateway hooks while the raw session source remains `telegram`.

Keep default:

```text
allowed_sources=telegram,cli
gateway_policy=trigger-only
```
