# Agent Context Substrate Improvement Spec

> **For Hermes:** Use `subagent-driven-development` if implementing this spec task-by-task.

**Status:** Partially implemented alpha; MVP scope locked
**Scope:** Summarization quality, knowledge atoms, promotion queue, wiki patching, and semantic lint
**Default posture:** Keep Obsidian human-facing. Keep generated machine artifacts outside the wiki by default.
**Alpha decision:** Implement recovery and LLM-input safety gaps; keep wiki growth automation intentionally review-first and MVP-sized.

## 1. Goal

Improve `agent-context-substrate` from a session recovery substrate into a stronger evidence-based knowledge substrate.

The project should keep its current strengths:

```text
raw session
  -> MicroSummary / UnitSummary
  -> ContextPacket
  -> RecoveryBrief
  -> Ledger
  -> request-time retrieval
```

But add the missing bridge into a living LLM Wiki:

```text
ContextPacket
  -> EvidenceBundle
  -> structured summaries
  -> claim / decision / entity atoms
  -> promotion candidates
  -> wiki patch proposals
  -> reviewed wiki updates
```

## 2. Core Diagnosis

The current architecture is strong for:

- session recovery;
- provenance-preserving artifacts;
- packet-only default behavior;
- request-time retrieval from wiki, packets, summaries, and optional raw messages;
- keeping generated artifacts in `data/exports/` and ledger data in `data/index/session_ledger.json`.

The current weak points are:

- `MicroSummary` is heuristic and mostly string-extraction based;
- one summary string is doing too many jobs: recovery, knowledge, and retrieval;
- legacy full promotion can look like “put session summaries into page templates”;
- there is no explicit claim/decision atom layer;
- there is no promotion queue or patch review path before writing to the wiki;
- lint is mostly structural, not yet semantic.

## 3. Design Principles

1. **Packets are not pages.**
   A `ContextPacket` is raw material for future wiki updates, not a durable wiki page.

2. **Pages must earn existence.**
   Not every session summary should become an Obsidian page.

3. **Heuristic is the spine; LLM is the brain.**
   Heuristics collect grounded evidence. LLMs interpret meaning and structure it.

4. **Every claim needs evidence.**
   Decisions, claims, and action items must cite `message_id`, `micro_id`, packet, or source refs.

5. **Wiki writes should be patches, not rewrites.**
   Default behavior should propose small, reviewable patches.

6. **Human wiki and machine substrate stay separate.**
   Machine artifacts live under `data/`. Obsidian receives curated, reviewed knowledge.

7. **LLM features are opt-in.**
   Default summarization remains heuristic for privacy, cost, speed, offline use, and reproducibility.

## 3.1 Product Philosophy and Quality Metrics

The alpha should optimize for usefulness, trust, and reviewability rather than automation volume.

1. **Recovery brief quality is the core metric.**
   The most important product question is: can the next session immediately continue real work? A recovery brief is high quality when it captures the last concrete state, key decisions, active files, unresolved blockers, and the next safe action without replaying raw transcript.

2. **Search trust matters before search sophistication.**
   Lexical retrieval is sufficient for the alpha, but larger substrates will need better precision, recency, and source-aware ranking. Retrieval results should make it clear why a hit appeared, how recent it is, and which artifact or wiki source supports it.

3. **Promotion queue friction must stay low.**
   The review-first philosophy is correct only if users can quickly triage proposed wiki updates. If patch proposals become noisy or hard to compare, backlog will grow and the wiki will stop improving. Queue/listing UX, grouping, evidence display, and status transitions are therefore product-quality concerns, not just CLI polish.

4. **Automation should reduce review load, not bypass it.**
   The substrate should help decide what deserves wiki life. It should not become an automatic page factory or broad wiki editor before review, rollback, and conflict handling are mature.

## 4. Non-goals

This spec does **not** require:

- replacing the current heuristic summarizer immediately;
- making LLM summarization the default;
- writing generated packets directly into Obsidian;
- redesigning the existing Obsidian folder structure;
- adding provider SDKs as core dependencies;
- rewriting existing wiki pages wholesale;
- implementing every possible wiki patch operation in the alpha;
- treating native Windows or non-Hermes agent compatibility as a blocker for the current Hermes-focused alpha.

## 4.1 Alpha MVP Scope

The alpha scope is intentionally split into **Implemented**, **MVP to implement**, and **Future** work.

| Area | Alpha decision | Rationale |
| --- | --- | --- |
| `search_knowledge(mode="recovery")` | **MVP to implement** | Recovery is part of the core promise. Search should surface recovery briefs and packet recovery fields directly. |
| LLM input safety flags | **MVP to implement** | `agent-llm`, `hybrid`, and `custom-command` modes need a visible input boundary before broader use. |
| Wiki patch operations | **MVP subset only** | More operations would turn the project into an automatic wiki editor before review, rollback, and conflict UX are mature. |
| Semantic lint | **Structural MVP now, semantic heuristics later** | Deep duplicate/stale/contradiction checks require ontology, similarity, and freshness policy to avoid noisy warnings. |
| Native Windows / non-Hermes portability | **Future before expansion** | The current release remains Hermes-focused; see `docs/AGENT_PORTABILITY_NOTES.md` before claiming broader support. |

## 5. Target Architecture

```text
Hermes state.db / raw sources
        ↓
Raw Export
        ↓
Segmenter
        ↓
Heuristic Evidence Extractor
        ↓
EvidenceBundle
        ↓
Structured Summarizer
        ├── heuristic mode
        ├── agent-llm mode
        ├── hybrid mode
        └── custom-command mode
        ↓
Summary Lint / Repair / Fallback
        ↓
MicroSummaryV2
        ↓
UnitSummaryV2
        ↓
ContextPacket
        ↓
Atom Extractor
        ├── claims.jsonl
        ├── decisions.jsonl
        ├── entities.jsonl
        ├── concepts.jsonl
        └── questions.jsonl
        ↓
Promotion Queue
        ↓
Wiki Patch Planner
        ↓
Review / Dry-run / Apply
        ↓
Obsidian Wiki
        ↓
Semantic Lint + Graph Retrieval
```

## 5.1 Code Design Direction

The current implementation is acceptable for the Hermes-focused alpha, but the following design pressures should guide the next refactors.

1. **Keep shrinking `cli.py`.**
   Moving handlers into `commands/` is the right direction, but the CLI still knows too much about orchestration, file I/O, rendering, listing, and lint glue. Prefer thin CLI handlers that validate arguments and delegate to service modules.

2. **Split retrieval responsibilities before retrieval grows further.**
   `retrieval.py` currently combines lexical search, hit encoding, source expansion, graph search, and artifact parsing. As ranking, recency, source weighting, and recovery mode mature, this file is likely to become the first maintenance bottleneck. Future structure should separate source loaders, scoring/ranking, hit encoding/decoding, expansion, and graph traversal.

3. **Move model invariants closer to construction.**
   `models.py` has clear dataclass serialization, but many important invariants are enforced later by lint. Examples include `UnitSummary.micro_ids` matching actual `MicroSummary` objects and evidence refs matching known message ids. Lint should remain as a safety net, but constructors/builders should prevent invalid substrate artifacts when the required context is available.

4. **Make agent/session boundaries explicit.**
   Even in Hermes-only mode, `session_store.py` and raw bundle dictionary shapes leak across multiple layers. A future multi-agent substrate should introduce explicit boundaries such as `AgentAdapter`, `SessionBundle`, or similar typed interfaces so Hermes state.db details stay inside the Hermes adapter.

5. **Treat heuristic summarization as a pipeline, not one growing helper file.**
   `summarizer.py` is practical for alpha, but regex/helper accumulation will become hard to tune once recovery quality becomes the core metric. When quality work begins, split heuristic extraction into strategy objects or staged extractors such as request/outcome extraction, artifact extraction, question extraction, and recovery-summary composition.

## 6. Data Model Requirements

### 6.1 `SummaryMetadata`

Add metadata to every generated summary artifact.

```python
@dataclass(frozen=True)
class SummaryMetadata:
    mode: str                 # heuristic | agent-llm | hybrid | custom-command
    schema_version: str       # e.g. micro_summary_v2
    prompt_version: str | None
    model: str | None
    input_hash: str
    created_at: str
    confidence: float | None = None
```

Acceptance criteria:

- Every v2 summary has metadata.
- `input_hash` changes when source messages or prompt/schema/model changes.
- Existing v1 artifacts remain readable.

### 6.2 `MicroEvidenceBundle`

Create a bounded input object for summarization.

```python
@dataclass(frozen=True)
class EvidenceMessage:
    message_id: int
    role: str
    content: str

@dataclass(frozen=True)
class MicroEvidenceBundle:
    session_id: str
    micro_id: str
    message_ids: list[int]
    user_messages: list[EvidenceMessage]
    assistant_messages: list[EvidenceMessage]
    heuristic_request: str | None
    heuristic_outcome: str | None
    heuristic_key_points: list[str]
    files: list[str]
    code_blocks: list[str]
    urls: list[str]
    headings: list[str]
    explicit_questions: list[str]
```

Acceptance criteria:

- Evidence bundle is exported as JSON for debugging.
- Evidence bundle preserves message ids.
- Redaction can run before Agent LLM or custom-command use.

Suggested path:

```text
data/exports/evidence/<session_id>/<micro_id>.json
```

### 6.3 `MicroSummaryV2`

Separate summary purposes.

```python
@dataclass(frozen=True)
class MicroSummaryV2:
    micro_id: str
    session_id: str
    message_ids: list[int]

    recovery_summary: str
    knowledge_summary: str
    retrieval_summary: str

    user_intent: str | None
    assistant_outcome: str | None

    decisions: list[EvidenceBackedText]
    claims: list[EvidenceBackedText]
    action_items: list[EvidenceBackedText]
    open_questions: list[str]

    files: list[str]
    entities: list[str]
    concepts: list[str]

    metadata: SummaryMetadata
    provenance: RawSessionReference
```

Where:

```python
@dataclass(frozen=True)
class EvidenceBackedText:
    text: str
    evidence_message_ids: list[int]
    confidence: float
```

Acceptance criteria:

- Existing `MicroSummary` can be converted into `MicroSummaryV2` using heuristic fields.
- `recovery_summary`, `knowledge_summary`, and `retrieval_summary` are not empty.
- Decisions and claims cite real message ids.

### 6.4 `UnitSummaryV2`

Use units as meaning-level summaries, not just combined micro summaries.

```python
@dataclass(frozen=True)
class UnitSummaryV2:
    unit_id: str
    session_id: str
    title: str
    goal: str
    state: str                 # proposed | in_progress | completed | blocked | design_proposed

    decisions: list[EvidenceBackedText]
    progress: list[str]
    next_actions: list[str]
    open_questions: list[str]
    risk_notes: list[str]
    wiki_candidates: list[str]

    micro_ids: list[str]
    related_pages: list[str]
    metadata: SummaryMetadata
    provenance: RawSessionReference | None
```

Acceptance criteria:

- Unit summary distinguishes completed work from proposed work.
- Unit summary identifies next actions separately from open questions.
- Unit summary can feed `RecoveryBrief` without raw transcript replay.

### 6.5 Knowledge Atoms

Add atom records as the bridge between packets and wiki updates.

```python
@dataclass(frozen=True)
class ClaimAtom:
    atom_id: str
    text: str
    type: str                  # fact | design_claim | decision_rationale | constraint
    subjects: list[str]
    source_refs: list[str]
    confidence: float
    status: str                # active | superseded | contradicted | deprecated
    first_seen: str
    last_seen: str
    supports: list[str]
    contradicts: list[str]
    supersedes: list[str]
```

Initial atom files:

```text
data/atoms/claims.jsonl
data/atoms/decisions.jsonl
data/atoms/entities.jsonl
data/atoms/concepts.jsonl
data/atoms/questions.jsonl
```

Acceptance criteria:

- Every atom has source refs.
- Atoms are append-friendly JSONL.
- Atom extraction can run without modifying Obsidian.

### 6.6 Promotion Candidate

Promotion is a decision, not a format conversion.

```json
{
  "candidate_id": "cand_2026_0507_001",
  "packet_id": "20260507_...",
  "kind": "concept_update",
  "target_page": "01 지식/LLM Wiki.md",
  "reason": "The session clarified the difference between session recovery substrate and living wiki maintenance.",
  "evidence": ["packet:20260507_...#unit-1", "claim:claim_001"],
  "proposed_action": "update_existing",
  "confidence": 0.82,
  "status": "pending"
}
```

Suggested paths:

```text
data/promotions/<packet_id>.json
data/promotions/<packet_id>.md
```

Acceptance criteria:

- Proposing promotions does not write to Obsidian.
- Candidates contain evidence and confidence.
- Candidates support statuses: `pending`, `accepted`, `rejected`, `applied`, `superseded`.

### 6.7 Wiki Patch Proposal

All wiki updates should be reviewable patches.

```json
{
  "patch_id": "patch_042",
  "target": "01 지식/LLM Wiki.md",
  "operation": "insert_claim_block",
  "rationale": "New evidence clarifies LLM Wiki vs hierarchical RAG.",
  "evidence": ["claim_101", "claim_102"],
  "risk": "low",
  "diff": {
    "before": "...",
    "after": "..."
  },
  "status": "proposed"
}
```

Supported alpha operations:

```text
create_page
insert_claim_block
append_managed_section / append_section
```

Operations already useful in experiments but not part of the alpha guarantee:

```text
add_link
mark_stale
```

Future operations:

```text
replace_section
add_alias
mark_deprecated
merge_pages
split_page
```

Acceptance criteria:

- Default is dry-run.
- Patch proposal shows target file, rationale, evidence, and diff.
- Applying a patch updates only the intended section or managed block.

## 7. Wiki Editing Policy

### 7.1 Managed blocks

Prefer managed blocks over full-page rewrites.

```md
<!-- acs:auto:claims:start -->
- ...
<!-- acs:auto:claims:end -->
```

Rules:

- The patcher may update managed blocks.
- The patcher should avoid touching human-written prose unless operation explicitly targets a section.
- Canonical pages require patch proposal before apply.

### 7.2 Page lifecycle

Add page maturity metadata when useful.

```yaml
status: seed        # seed | stub | working | canonical | stale | deprecated
maturity: 0.2
review_needed: true
```

Rules:

- `seed` and `stub` pages may be created more freely.
- `canonical` pages should only receive explicit patch proposals.
- `stale` pages should be compared against recent evidence.
- `deprecated` pages remain searchable but should be lower priority.

## 8. Summarizer Backend Requirements

### 8.1 Backend interface

```python
class SummarizerBackend(Protocol):
    name: str

    def summarize_micro(
        self,
        evidence: MicroEvidenceBundle,
        schema_version: str,
    ) -> MicroSummaryV2:
        ...

    def summarize_unit(
        self,
        micro_summaries: list[MicroSummaryV2],
        schema_version: str,
    ) -> UnitSummaryV2:
        ...
```

Initial backends:

```text
HeuristicSummarizerBackend
AgentLLMSummarizerBackend
HybridSummarizerBackend
CustomCommandSummarizerBackend
```

Backend roles:

```text
HeuristicSummarizerBackend
  = default, offline, deterministic evidence-to-summary conversion

AgentLLMSummarizerBackend
  = delegates summarization to the host AI Agent's existing LLM routing layer
    and reuses the Agent's configured provider/model/keys/routing policy

HybridSummarizerBackend
  = heuristic evidence spine + Agent LLM semantic interpretation

CustomCommandSummarizerBackend
  = external process escape hatch for non-Hermes integrations or experiments
```

Direct provider SDK backends are not preferred as core dependencies:

```text
OpenAIBackend
AnthropicBackend
GeminiBackend
OllamaBackend
OpenRouterBackend
```

These may exist later as optional plugins, but the preferred packaged path is `AgentLLMSummarizerBackend` because Agent Context Substrate is Hermes-oriented and should not duplicate provider configuration, API keys, cost policy, or routing logic.

### 8.2 Default behavior

Default remains:

```text
--summary-mode heuristic
```

LLM/hybrid behavior is opt-in:

```bash
agent-context-substrate build-context-packet \
  --session-id '<SESSION_ID>' \
  --packet-id '<PACKET_ID>' \
  --summary-mode agent-llm \
  --project-root '<PROJECT_ROOT>'
```

```bash
agent-context-substrate build-context-packet \
  --session-id '<SESSION_ID>' \
  --packet-id '<PACKET_ID>' \
  --summary-mode hybrid \
  --project-root '<PROJECT_ROOT>'
```

`agent-llm` means “use the current AI Agent's LLM routing layer”; it should not require separate provider-specific environment variables inside Agent Context Substrate.

### 8.3 Agent LLM router backend

The preferred LLM implementation is `AgentLLMSummarizerBackend`, not direct provider SDK integration.

Rationale:

```text
Agent already knows provider/model/API-key/routing/cost policy
→ substrate should reuse that instead of duplicating it
```

Expected flow:

```text
MicroEvidenceBundle JSON
  -> AgentLLMSummarizerBackend
  -> host AI Agent LLM router
  -> strict JSON MicroSummaryV2 / UnitSummaryV2
  -> summary-lint
  -> accepted or heuristic fallback
```

Acceptance criteria:

- `agent-llm` is opt-in and never the default.
- The backend reuses the host Agent's configured model/provider/routing layer.
- No provider SDK becomes a required runtime dependency of this package.
- The backend returns strict JSON matching `MicroSummaryV2` / `UnitSummaryV2`.
- Invalid JSON, failed lint, or router failure falls back to heuristic mode.
- Provider names, API keys, tokens, and connection strings are not persisted in summary artifacts.

### 8.4 Hybrid summarizer

`hybrid` should mean:

```text
Heuristic = evidence collector / spine
Agent LLM = semantic interpreter / brain
```

This mode should first build bounded, redacted evidence with deterministic heuristics, then ask the Agent LLM router to produce structured semantic fields. It should never send unbounded raw transcripts by default.

### 8.5 Custom command backend

Support external summarizers without adding core SDK dependencies.

```bash
agent-context-substrate build-context-packet \
  --summary-mode custom-command \
  --summarizer-command "python scripts/my_summarizer.py"
```

Contract:

- command receives JSON evidence on stdin;
- command returns strict JSON summary on stdout;
- non-zero exit code triggers fallback.

## 9. LLM Safety Requirements

### 9.1 Structured output

LLM output must be strict JSON. No markdown parsing as the primary path.

This applies to both `agent-llm` and `hybrid` modes. The Agent LLM router may choose the provider/model, but the summarizer contract remains provider-agnostic JSON.

Failure flow:

```text
LLM output
  -> JSON parse
  -> failed? repair once
  -> failed again? heuristic fallback
```

### 9.2 Summary lint

Add `summary-lint` checks before accepting LLM output.

Required checks:

```text
evidence_required
evidence_exists
no_new_files
no_new_entities
summary_not_empty
retrieval_keywords_present
unresolved_question_detection
confidence_calibrated
```

Acceptance criteria:

- Invalid evidence ids fail lint.
- Invented files fail lint.
- Empty summaries fail lint.
- Failed lint triggers repair or fallback.

### 9.3 Privacy and redaction

Default config:

```yaml
summarization:
  mode: heuristic
  agent_llm:
    enabled: false
    use_agent_routing: true
    redact_before_llm: true
    allow_raw_code: false
    allow_file_paths: true
    allow_env_values: false
    max_input_chars: 12000
```

The substrate should not require separate provider-specific config such as `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or model names for `agent-llm`; those belong to the host AI Agent's routing/config layer. If any secret-like value appears in evidence or router metadata, it must be redacted before persistence.

CLI options:

```text
--llm-redact on|off
--llm-allow-code-snippets on|off
--llm-max-input-chars <N>
```

Alpha MVP behavior:

- `--llm-redact` defaults to `on` for non-heuristic summary modes.
- `--llm-max-input-chars` bounds evidence sent to host LLM/custom-command adapters.
- `--llm-allow-code-snippets` defaults to `off`; opt in only when code snippets are needed for the summary task.
- Provider-specific privacy policy, complex PII detection, and named redaction profiles are future work.

Required redactions:

```text
API keys / tokens -> <REDACTED_SECRET>
.env values -> <REDACTED_ENV>
email addresses -> <REDACTED_EMAIL>
local absolute paths -> configurable path policy
```

## 10. CLI Requirements

### 10.1 New commands

```bash
agent-context-substrate extract-atoms \
  --packet-id '<PACKET_ID>' \
  --project-root '<PROJECT_ROOT>'
```

```bash
agent-context-substrate propose-promotions \
  --packet-id '<PACKET_ID>' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>'
```

```bash
agent-context-substrate plan-wiki-patches \
  --promotion-file 'data/promotions/<PACKET_ID>.json' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>'
```

```bash
agent-context-substrate apply-wiki-patch \
  --patch-id '<PATCH_ID>' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>' \
  --dry-run
```

```bash
agent-context-substrate build-topic-map \
  --query 'LLM Wiki와 계층형 RAG의 차이' \
  --project-root '<PROJECT_ROOT>' \
  --wiki-root '<WIKI_ROOT>'
```

### 10.2 Existing command extensions

Extend `build-context-packet`:

```text
--summary-mode heuristic|agent-llm|hybrid|custom-command
--summarizer-command <COMMAND>
--summary-cache on|off
--summary-model <MODEL_NAME>          # optional hint only; Agent router may ignore
--summary-budget cheap|balanced|high  # optional routing hint
--llm-redact on|off
--llm-max-input-chars <N>
```

For `agent-llm` and `hybrid`, `--summary-model` and `--summary-budget` should be treated as routing hints passed to the host Agent layer, not as provider-specific substrate configuration.

Extend `lint-wiki`:

```text
--semantic
--include-promotions
--include-atoms
```

### 10.3 Legacy promotion behavior

Mark these as legacy in help text and docs:

```text
promote-packet-query
promote-packet-plan
promote-unit-concept
promote-unit-architecture
run-e2e-pipeline
promotion_mode=full
```

Recommended wording:

```text
Legacy full promotion is for compatibility and experiments. The recommended path is packet-only finalize plus promotion candidates and wiki patch proposals.
```

## 11. Retrieval Requirements

Split retrieval intent into three modes.

Alpha decision:

- `knowledge` and `graph` are already part of the current retrieval surface.
- `recovery` should be implemented as a small MVP mode, not left as documentation only.
- Recovery mode should prioritize `data/exports/recovery/*.json`, then context packet recovery fields such as `macro_context`, `open_questions`, `critical_files`, and recovery-oriented unit/micro summary text.
- Ranking can stay deterministic and simple: recovery brief hits first, packet/summary recovery hits next.

### 11.1 Recovery search

Purpose:

```text
Where did the work stop?
```

Primary sources:

```text
RecoveryBrief
ContextPacket
UnitSummary
critical_files
open_questions
```

### 11.2 Knowledge search

Purpose:

```text
What durable knowledge do we have about this concept?
```

Primary sources:

```text
wiki pages
claims
sources
synthesis pages
```

### 11.3 Graph search

Purpose:

```text
What is connected to this topic?
```

Primary sources:

```text
wikilinks
backlinks
tags
aliases
related_to
contradicts
supersedes
```

Initial implementation may keep the current `wiki_knowledge_search` tool but should add metadata or modes so callers can distinguish recovery, knowledge, and graph results.

## 12. Semantic Lint Requirements

Add semantic checks beyond structural wiki health.

Alpha decision:

- Keep alpha semantic lint mostly structural and evidence-oriented.
- Implement or keep checks such as `claim_without_source`, `patch_without_candidate`, `applied_patch_missing_log`, and `applied_promotion_without_applied_patch`.
- Treat `duplicate_concept`, `stale_claim`, `contradiction_unresolved`, `hub_overload`, and related ontology/freshness checks as future work until similarity, ontology, and freshness policies are explicit enough to avoid noisy warnings.

Initial checks:

```text
claim_without_source
duplicate_concept
orphan_but_important
high_frequency_no_page
stale_claim
contradiction_unresolved
hub_overload
dead_synthesis
promotion_backlog
page_without_question
```

Acceptance criteria:

- Semantic lint can run without modifying files.
- Output includes JSON and Markdown reports.
- Reports include evidence and suggested next action.

## 13. Caching and Reproducibility

Summary cache key:

```text
hash(
  raw_message_ids,
  raw_message_content_hash,
  schema_version,
  prompt_version,
  model_name,
  summarizer_mode
)
```

Suggested path:

```text
data/cache/summaries/<cache_key>.json
```

Acceptance criteria:

- Re-running the same summary with cache enabled reuses the cached result.
- Changing prompt/schema/model/input invalidates the cache.
- Cache metadata is visible in summary artifacts.

## 14. Implementation Phases

### Phase 0: Document current direction — **Implemented**

- Clarify that `packet-only` is the recommended default.
- Mark full promotion as legacy/experimental.
- Add this spec to repository-facing docs.

### Phase 1: Schema foundation without LLM — **Implemented**

- Add `SummaryMetadata`.
- Add `MicroEvidenceBundle`.
- Add `MicroSummaryV2` and `UnitSummaryV2` or compatible extension fields.
- Add heuristic conversion into v2 fields.
- Add tests for backward compatibility.

### Phase 2: Evidence and summary lint — **Mostly implemented; keep improving gates**

- Export evidence bundles.
- Add summary lint report model.
- Validate evidence ids, files, entities, empty summaries, and confidence.
- Add fallback behavior.

### Phase 3: Backend abstraction — **Implemented**

- Add `SummarizerBackend` protocol.
- Move current heuristic logic behind `HeuristicSummarizerBackend`.
- Add `CustomCommandSummarizerBackend` as an escape hatch.
- Add `AgentLLMSummarizerBackend` as the preferred packaged LLM path.
- Add CLI flags for summary mode.

### Phase 4: Agent LLM and hybrid summarization — **MVP to finish**

- Add structured JSON prompt templates.
- Route `agent-llm` requests through the host AI Agent LLM router.
- Treat `--summary-model` / `--summary-budget` as optional router hints.
- Add JSON parse / repair / fallback.
- Add privacy redaction before Agent LLM calls.
- Add MVP CLI controls: `--llm-redact`, `--llm-max-input-chars`, and `--llm-allow-code-snippets`.
- Keep heuristic as default.
- Do not add direct provider SDKs as core dependencies.

### Phase 5: Atoms and promotion queue — **MVP implemented**

- Add atom models and JSONL storage.
- Add `extract-atoms`.
- Add `propose-promotions`.
- Ensure no Obsidian writes happen during proposal.

### Phase 6: Wiki patch planner — **MVP subset locked**

- Add patch proposal model.
- Add managed block support.
- Add dry-run by default.
- Add apply command with explicit confirmation or flag.
- Keep alpha write operations narrow: `create_page`, `insert_claim_block`, and managed append-style updates.
- Leave broad page-editing operations such as `replace_section`, `merge_pages`, and `split_page` for future work.

### Phase 7: Semantic lint and graph retrieval — **Partial; recovery retrieval is next MVP**

- Add structural semantic lint checks first.
- Add retrieval modes or tool metadata.
- Add `search_knowledge(mode="recovery")` as a focused MVP.
- Add topic map builder.
- Leave ontology-heavy lint such as duplicate/stale/contradiction analysis for future work.

## 15. Testing Requirements

Minimum tests:

```text
tests/test_evidence_bundle.py
tests/test_summary_metadata.py
tests/test_micro_summary_v2.py
tests/test_summary_lint.py
tests/test_summarizer_backends.py
tests/test_agent_llm_summarizer_backend.py
tests/test_custom_command_summarizer.py
tests/test_atom_extraction.py
tests/test_promotion_candidates.py
tests/test_wiki_patch_planner.py
tests/test_semantic_lint.py
```

Verification commands:

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest -q
```

For this WSL path, use:

```bash
cd '<PROJECT_ROOT>' && . .venv/bin/activate && python -m pytest -q
```

## 16. Documentation Requirements

Update docs after implementation:

- `README.md`
- `README.ko.md`
- `docs/PIPELINE.md`
- `docs/USER_GUIDE.md`
- `docs/USER_GUIDE.en.md`
- CLI help text

Required documentation points:

- `packet-only` remains default.
- LLM summarization is opt-in.
- Privacy/redaction behavior is explicit.
- Legacy full promotion is not the recommended wiki path.
- Promotion candidates and wiki patches are the recommended path.

## 17. Acceptance Summary

This spec is satisfied when:

- heuristic summarization still works as the default;
- v2 summary artifacts distinguish recovery, knowledge, and retrieval summaries;
- LLM/hybrid summarization can be added without core provider lock-in;
- every LLM-derived decision/claim/action cites evidence;
- summary lint catches common hallucination and grounding errors;
- atoms can be extracted without touching Obsidian;
- promotion candidates can be generated without touching Obsidian;
- wiki patches are proposed before apply;
- semantic lint starts measuring wiki health as a living graph;
- generated machine artifacts remain separate from the human-facing wiki unless explicitly reviewed and applied.

## 18. North Star

```text
Heuristic summarizer records what happened.
LLM summarizer explains what it meant.
Atoms preserve what should survive.
Promotion queue decides what deserves wiki life.
Wiki patches update human knowledge safely.
```

The project should not become an automatic page factory.
It should become the evidence, memory, and promotion substrate beneath a healthy LLM Wiki.
