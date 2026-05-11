# Changelog

All notable changes to Agent Context Substrate are summarized here.

## v0.2.0 - local release candidate

### Added

- Evidence-backed v2 summary artifacts with heuristic, agent-LLM, hybrid, and custom-command summary modes.
- Structured atom layer for claims, decisions, entities, concepts, and questions.
- Promotion candidate queue and review-first wiki patch proposal flow.
- Semantic lint checks across promotions, patches, claims, concepts, and open questions.
- Topic map graph generation over wiki pages and substrate artifacts.
- Request-time retrieval expansion over promotion candidates, wiki patch proposals, applied patch logs, and topic-map paths.
- Real-wiki dry-run validation workflow documentation.
- Lightweight Ruff lint gate for release checks.

### Changed

- `packet-only` remains the default; legacy full wiki promotion is documented as explicit compatibility behavior.
- `extract-atoms` now exports all structured atom JSONL files, not only claims.
- `lint-promotions` now loads atom JSONL files when available.
- `apply-wiki-patch` supports additional reviewable operations: `append_section`, `add_link`, and `mark_stale`; `add_link` is idempotent.
- Release hygiene now ignores generated atom, promotion, patch, lint, cache, and topic-map artifacts.
- Artifact export IDs are validated before writing reports, packets, topic maps, and raw-session exports.
- Custom-command summarizers run without a shell after `shlex` parsing to reduce command-injection risk.
- `build-context-packet --summary-mode ...` now prints stderr warnings when v2 summaries fall back to heuristic output.
- CLI command execution now delegates remaining command groups into `commands/*` handler modules.

### Verified

- Hardened retrieval expansion and wiki patch planning against forged path traversal inputs.
- Project test suite: `200 passed`.
- Fresh-install smoke: `ok=True`, `retrieval_hit_count=1`, `expanded_content_length=14195`, `lint_issue_count=0`.
- Real Obsidian wiki validation was performed as dry-run only; no wiki writes were applied.

## v0.1.0

- Public alpha release for packet-only session recovery, packaged Hermes Agent integration, install/doctor/fresh-install smoke commands, and read-only retrieval tools.
