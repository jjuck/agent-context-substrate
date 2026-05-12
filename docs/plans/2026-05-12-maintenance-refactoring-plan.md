# Agent Context Substrate Maintenance Refactoring Plan

> **For Hermes:** Treat this as a maintenance/refactoring track, separate from feature/spec execution. Use `subagent-driven-development` only after choosing one narrow slice.

**Goal:** Reduce long-term maintenance risk in `agent-context-substrate` without expanding alpha product scope.

**Architecture:** Keep feature work driven by `spec.md`; keep this plan focused on code boundaries, invariants, safety gates, and regression control. Refactor one seam at a time behind existing tests so behavior remains stable.

**Tech Stack:** Python 3.11+, argparse CLI, dataclasses, pytest, ruff, existing substrate artifacts under `data/`, Hermes-focused packaged integration.

---

## Scope split

### This plan covers

- CLI/service boundary cleanup.
- Retrieval module responsibility split.
- Model and artifact invariant enforcement.
- Agent/session adapter boundaries.
- Heuristic summarization pipeline cleanup.
- Regression gates and safety hardening around refactors.

### This plan does not cover

- New alpha features such as recovery retrieval or LLM input safety flags, except where refactoring directly supports them.
- Broad wiki patch operation expansion.
- Native Windows or non-Hermes portability implementation.
- Documentation-only cleanup, except small references needed to keep plans discoverable.

## Operating rules

1. **No behavior rewrite without a regression test.** Every refactor starts by pinning current behavior.
2. **One seam per PR/commit.** Do not mix CLI extraction, retrieval splitting, and summarizer redesign in one change.
3. **Prefer service modules over larger handlers.** CLI code should parse arguments and delegate.
4. **Keep packet-only defaults stable.** Existing context packet and recovery behavior must remain unchanged unless a feature plan explicitly changes it.
5. **Validate after every slice.** Minimum gate: focused tests, full `pytest`, `ruff check .`, and `git diff --check`.

## Track A — Immediate maintenance stabilization

### A1. Keep the working tree split cleanly

**Objective:** Avoid mixing feature, refactor, safety, and docs changes.

**Actions:**

- Review `git status --short --branch --untracked-files=all` before each slice.
- Group commits in this order when changes overlap:
  1. pipeline/service extraction;
  2. CLI handler extraction;
  3. safety hardening and tests;
  4. docs/spec updates.
- Do not start a new refactor while feature tests are failing.

**Verification:**

```bash
cd '/mnt/c/Users/이주완/Desktop/py/My_Project/agent-context-substrate' && git status --short --branch --untracked-files=all
cd '/mnt/c/Users/이주완/Desktop/py/My_Project/agent-context-substrate' && . .venv/bin/activate && python -m pytest -q
cd '/mnt/c/Users/이주완/Desktop/py/My_Project/agent-context-substrate' && . .venv/bin/activate && ruff check .
cd '/mnt/c/Users/이주완/Desktop/py/My_Project/agent-context-substrate' && git diff --check
```

### A2. Centralize shared safety/path helpers

**Objective:** Keep path traversal, symlink escape, artifact id, and wiki target validation consistent.

**Primary files:**

- `src/agent_context_substrate/safe_paths.py`
- `src/agent_context_substrate/retrieval.py`
- `src/agent_context_substrate/topic_map.py`
- `src/agent_context_substrate/wiki_patches.py`
- `src/agent_context_substrate/assets/context_engine/agent_context_substrate/recovery_loader.py`
- Related tests in `tests/test_safe_paths.py`, `tests/test_retrieval.py`, `tests/test_topic_map.py`, `tests/test_wiki_patches.py`, `tests/test_context_engine_recovery_loader.py`

**Refactor shape:**

- Keep helpers small and explicit:
  - `safe_artifact_stem(...)`
  - `safe_child_path(...)`
  - `is_safe_project_artifact_path(...)`
  - `safe_wiki_target_path(...)`
- Replace local one-off path checks with shared helpers only after targeted tests exist.
- Keep asset-side recovery loader self-contained if importing core package would break packaged integration.

**Done when:**

- Retrieval, topic map, wiki patch, and recovery loader path rules are visibly consistent.
- Forged hit ids and unsafe wiki targets are rejected before reads/writes.

## Track B — CLI and service boundaries

### B1. Finish making `cli.py` thin

**Objective:** Make `cli.py` mostly parser setup plus command dispatch.

**Primary files:**

- `src/agent_context_substrate/cli.py`
- `src/agent_context_substrate/commands/*.py`
- `tests/test_cli.py`
- `tests/test_build_context_packet_command.py`

**Refactor shape:**

- Command handlers should receive dependencies as parameters when tests need injection.
- Keep output text stable unless a feature plan explicitly changes UX.
- Move command-specific rendering and argument validation into command modules only when that does not create circular imports.

**Candidate next slices:**

1. Move remaining artifact/list/render helpers out of `cli.py`.
2. Move command-specific validation closer to each handler.
3. Keep only parser construction, shared callback creation, and dispatch in `cli.py`.

**Done when:**

- `cli.py` no longer owns packet construction, summary artifact export, lint report composition, or wiki patch orchestration logic.

### B2. Keep packet and summary pipelines as service APIs

**Objective:** Preserve the extraction of packet and summary construction behind stable service boundaries.

**Primary files:**

- `src/agent_context_substrate/packet_builder.py`
- `src/agent_context_substrate/summary_pipeline.py`
- `tests/test_packet_builder.py`
- `tests/test_summary_pipeline.py`

**Refactor shape:**

- Keep dataclass option/result objects as the public boundary:
  - `PacketBuildOptions`
  - `PacketBuildResult`
  - `SummaryOptions`
  - `SummaryArtifactResult`
- Avoid passing raw `argparse.Namespace` into service modules.
- Make cache/routing/LLM-safety additions fields on option dataclasses, not ad-hoc CLI conditionals.

**Done when:**

- CLI, e2e pipeline command, and tests all build packets through the same service API.

## Track C — Retrieval decomposition

### C1. Split retrieval into explicit responsibilities

**Objective:** Prevent `retrieval.py` from becoming the central maintenance bottleneck.

**Current pressure:** `retrieval.py` mixes lexical search, source loading, scoring, hit id encoding/decoding, expansion, graph traversal, and recovery-mode behavior.

**Proposed module split:**

```text
src/agent_context_substrate/retrieval.py          # public facade: search_knowledge, expand_hit
src/agent_context_substrate/retrieval_types.py    # RetrievalHit, RetrievalHitDetail, mode/source constants
src/agent_context_substrate/retrieval_ids.py      # hit id encode/decode and validation
src/agent_context_substrate/retrieval_sources.py  # wiki/packet/promotion/patch/recovery loaders
src/agent_context_substrate/retrieval_scoring.py  # lexical scoring, ranking, source weights
src/agent_context_substrate/retrieval_graph.py    # graph neighborhood/path traversal
```

**Incremental order:**

1. Add tests that pin current `search_knowledge(...)` and `expand_hit(...)` behavior for each source type.
2. Extract hit id encode/decode first; this is small and safety-sensitive.
3. Extract source loaders without changing scoring.
4. Extract scoring/ranking after behavior is pinned.
5. Extract graph traversal last.

**Done when:**

- Adding a new source type no longer requires editing one large retrieval file in many unrelated places.
- Forged hit id validation is centralized.

## Track D — Model invariants and artifact construction

### D1. Move invariants closer to builders

**Objective:** Stop invalid artifacts from being created when the builder has enough context to know they are invalid.

**Primary files:**

- `src/agent_context_substrate/models.py`
- `src/agent_context_substrate/evidence.py`
- `src/agent_context_substrate/packet_builder.py`
- `src/agent_context_substrate/summary_pipeline.py`
- `src/agent_context_substrate/summary_lint.py`

**Candidate invariants:**

- `UnitSummary.micro_ids` must reference actual micro summaries.
- Evidence-backed fields must cite known message ids or source refs.
- Summary confidence values must stay in `0.0..1.0`.
- Generated artifact ids must use safe stems before file paths are constructed.

**Refactor shape:**

- Keep lint as the external safety net.
- Add builder-level validation where the builder has full context.
- Prefer stable exception types or lint-like issue objects over raw assertion failures.

**Done when:**

- Common invalid artifact shapes are rejected before export, not only detected afterward by lint.

## Track E — Agent/session boundary cleanup

### E1. Introduce typed session boundaries

**Objective:** Keep Hermes `state.db` details and raw bundle dict shapes from leaking into unrelated modules.

**Candidate future types:**

```python
@dataclass(frozen=True)
class SessionBundle:
    session_id: str
    messages: list[SessionMessage]
    source: str
    metadata: dict[str, object]

class AgentAdapter(Protocol):
    def load_session(self, session_id: str) -> SessionBundle: ...
```

**Incremental order:**

1. Identify all functions that accept raw bundle dictionaries.
2. Add adapter/conversion helpers at the Hermes boundary.
3. Update one pipeline at a time to accept typed bundles.
4. Keep dict serialization at artifact boundaries only.

**Done when:**

- Most core modules do not need to know Hermes database field names.

## Track F — Heuristic summarization pipeline

### F1. Split heuristic extraction into stages

**Objective:** Improve recovery quality without turning `summarizer.py` into a pile of regex helpers.

**Potential stages:**

```text
raw messages
  -> request/outcome extraction
  -> artifact/file/url extraction
  -> decision extraction
  -> open-question extraction
  -> recovery summary composition
  -> retrieval keyword composition
```

**Incremental order:**

1. Pin current heuristic output with focused tests.
2. Extract pure helper functions into named stages.
3. Introduce small strategy objects only if functions become hard to tune.
4. Keep output shape stable until a feature plan changes summary behavior.

**Done when:**

- Recovery summary improvements can be made by editing one stage without breaking file extraction, open questions, or retrieval keywords.

## Priority order

1. **A1 — Working tree and commit split discipline** whenever broad changes already exist.
2. **A2 — Shared safety/path helpers** because they reduce security regressions across modules.
3. **B1/B2 — CLI and service boundary cleanup** because this lowers cost of future feature work.
4. **C1 — Retrieval decomposition** before ranking/recovery search grows further.
5. **D1 — Builder invariants** after service boundaries are stable.
6. **E1/F1 — Session boundary and summarizer pipeline** when recovery quality work becomes the active focus.

## Standard verification checklist

Run after each slice:

```bash
cd '/mnt/c/Users/이주완/Desktop/py/My_Project/agent-context-substrate' && . .venv/bin/activate && python -m pytest -q
cd '/mnt/c/Users/이주완/Desktop/py/My_Project/agent-context-substrate' && . .venv/bin/activate && ruff check .
cd '/mnt/c/Users/이주완/Desktop/py/My_Project/agent-context-substrate' && git diff --check
cd '/mnt/c/Users/이주완/Desktop/py/My_Project/agent-context-substrate' && python3 - <<'PY'
from pathlib import Path
print('asset_pycache_count=', len(list(Path('src/agent_context_substrate/assets').rglob('__pycache__'))))
print('asset_pyc_count=', len(list(Path('src/agent_context_substrate/assets').rglob('*.pyc'))))
PY
```

Expected:

- Full test suite passes.
- Ruff reports `All checks passed!`.
- `git diff --check` has no output.
- Packaged assets contain no `__pycache__` or `.pyc` files.

## First recommended slice

If the current working tree already contains mixed changes, do not start a new architecture refactor yet. First split and verify the existing changes, then choose one narrow maintenance slice.

Recommended first standalone refactor after the tree is clean:

```text
Extract retrieval hit id encode/decode/validation into `retrieval_ids.py`.
```

Reason:

- It is small.
- It improves safety.
- It prepares the larger retrieval decomposition.
- It can be tested without changing retrieval ranking or source behavior.
