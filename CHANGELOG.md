# Changelog

All notable changes to Agent Context Substrate are summarized here.

## v0.2.0 - local release candidate

### Added

- Evidence-backed v2 summary artifacts with heuristic, agent-LLM, hybrid, and custom-command summary modes.
- Structured atom layer for claims, decisions, entities, concepts, and questions.
- Promotion candidate queue and review-first wiki patch proposal flow.
- Recovery brief exports now include a `quality_gate` with score/issues for task title, macro context, work state, active context, next-step/open-question, and provenance coverage.
- Semantic lint checks across promotions, patches, claims, concepts, and open questions.
- Topic map graph generation over wiki pages and substrate artifacts.
- Request-time retrieval expansion over promotion candidates, wiki patch proposals, applied patch logs, and topic-map paths.
- Real-wiki dry-run validation workflow documentation.
- Lightweight Ruff lint gate for release checks.

### Changed

- `packet-only` remains the default; legacy full wiki promotion is documented as explicit compatibility behavior.
- `extract-atoms` now exports all structured atom JSONL files, not only claims.
- `lint-promotions` now loads atom JSONL files when available and validates patch/candidate/log integrity (`patch_without_candidate`, `applied_patch_missing_log`).
- `apply-wiki-patch` default apply scope is now locked to alpha-safe operations: `create_page`, `insert_claim_block`, `append_managed_section`, and `append_section`. Experimental `add_link` and `mark_stale` proposals are skipped by default instead of being applied as alpha guarantees.
- Release hygiene now ignores generated atom, promotion, patch, lint, cache, and topic-map artifacts.
- Artifact export IDs are validated before writing reports, packets, topic maps, and raw-session exports.
- Custom-command summarizers run without a shell after `shlex` parsing to reduce command-injection risk.
- `build-context-packet --summary-mode ...` now prints stderr warnings when v2 summaries fall back to heuristic output.
- CLI command execution now delegates remaining command groups into `commands/*` handler modules.
- Artifact, promotion queue, wiki patch, and semantic-lint helper logic now lives in `artifact_pipeline.py` instead of `cli.py`.
- Legacy promotion registration updates now live in `wiki_registration.py` instead of `cli.py`.
- Build-context-packet summary routing, LLM safety option, and V2 export glue now live with the build-context command handler instead of `cli.py`.
- Legacy promotion packet loading and slug default helpers now live with the legacy promotion command handler instead of `cli.py`.
- Retrieval hit-id encoding/decoding now lives in `retrieval_ids.py` as the first retrieval decomposition seam.
- Retrieval JSON/text source loading helpers now live in `retrieval_sources.py`, keeping source IO separate from retrieval scoring and ranking.
- Retrieval tokenization, lexical scoring, snippet creation, and hit ranking now live in `retrieval_scoring.py`.
- Retrieval hit result dataclasses now live in `retrieval_types.py`, keeping public retrieval types separate from the facade.
- Retrieval topic-map search, graph neighbor traversal, and readable path hit helpers now live in `retrieval_graph.py`.
- Context packet construction now rejects unit summaries that reference missing micro summaries before export.
- V2 summary artifact construction now rejects unit summaries that reference missing micro summaries before writing summary/cache artifacts.
- V2 summary artifact construction now runs summary-lint invariants before writing summary/cache artifacts.
- V2 summary artifact IDs are validated before evidence, summary, or cache paths are constructed.
- Context packet export validates packet IDs before creating export directories.
- V2 summary artifact construction rejects source/session ID mismatches before writing evidence or summary artifacts.
- Cached V2 summaries are validated before re-exporting evidence or summary artifacts.
- Malformed V2 summary cache payloads are converted into stable pipeline invariant errors before artifact re-export.
- V2 summary confidence values must be numeric, finite, and in the `0.0..1.0` range before export.
- V2 summary backend outputs must keep micro and unit `session_id` values tied to the source session before export.
- Session boundary typing now provides `SessionBundle` / `SessionMessage` conversion helpers, with evidence and summary builders accepting typed bundles while preserving raw bundle compatibility.
- Raw session extraction now exposes `build_typed_session_bundle(...)`, and packet construction uses the typed session boundary by default while preserving legacy raw JSON exports.
- Naming and session-processing policy helpers now accept typed `SessionBundle` inputs while preserving raw bundle compatibility.

### Verified

- Hardened retrieval expansion and wiki patch planning against forged path traversal inputs.
- Project test suite: `244 passed`.
- Fresh-install smoke: `ok=True`, `retrieval_hit_count=1`, `expanded_content_length=14195`, `lint_issue_count=0`.
- Real Obsidian wiki validation was performed as dry-run only; no wiki writes were applied.

## v0.1.0

- Public alpha release for packet-only session recovery, packaged Hermes Agent integration, install/doctor/fresh-install smoke commands, and read-only retrieval tools.
