# Documentation Map

Agent Context Substrate documentation is organized by audience. When documents disagree, use the current CLI help and the canonical documents below in this order.

## Start Here

| Need | Korean | English |
| --- | --- | --- |
| Product overview and quick start | [README.ko.md](../README.ko.md) | [README.md](../README.md) |
| Complete user guide | [USER_GUIDE.md](./USER_GUIDE.md) | [USER_GUIDE.en.md](./USER_GUIDE.en.md) |
| Windows Codex installation | [WINDOWS_CODEX_APP_SETUP.ko.md](./WINDOWS_CODEX_APP_SETUP.ko.md) | [WINDOWS_CODEX_APP_SETUP.md](./WINDOWS_CODEX_APP_SETUP.md) |

## Maintainer References

| Document | Purpose |
| --- | --- |
| [PIPELINE.md](./PIPELINE.md) | Current runtime architecture, domain boundaries, artifacts, write transaction, and extension rules |
| [OPERATIONS.md](./OPERATIONS.md) | Operational checks, lint interpretation, incident response, and cleanup |
| [AGENT_PORTABILITY_NOTES.md](./AGENT_PORTABILITY_NOTES.md) | Adapter portability status, resolved items, and remaining cross-platform risks |
| [RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md) | Release, live-install, privacy, and regression gates |
| [CHANGELOG.md](../CHANGELOG.md) | User-visible changes by release |

## Design History

[`spec.md`](../spec.md) records the product design as it evolved. The [`plans` archive](./plans/README.md) contains historical implementation plans, not current runtime documentation. Current behavior is defined by code, tests, CLI help, and the maintainer references above.

## Current Defaults

- New Codex installs use `summary_mode=auto`, `wiki_auto_mode=apply-flexible`, and `wiki_write_judge_mode=auto`.
- The default wiki placement policy is `emergent-root`: automatic flexible writes create `<Title>.md` at the vault root.
- Folder paths are storage hints. `type`, optional `category`, `sources`, wikilinks, and MOC sections carry meaning.
- The wiki root is resolved at runtime. `%USERPROFILE%\Documents\LLM Wiki` is a portable default template, not an installed absolute-path truth.
- Missing or novel categories do not block writes in emergent mode.
- Blocking lint covers provenance and graph integrity. Language, category, and prose-quality findings are advisory.
- Manual `apply-wiki-patch` is dry-run by default. Automatic Codex writes require an approved write-judge decision and all mechanical safety checks.

## Documentation Maintenance

When changing runtime behavior:

1. Update the relevant canonical reference.
2. Update both language variants when user-facing behavior changes.
3. Update `CHANGELOG.md` for release-visible behavior.
4. Keep historical plans intact except for a status banner or link to the superseding design.
5. Verify commands against `python -m agent_context_substrate.cli --help` and focused subcommand help.
