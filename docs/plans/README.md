# Design Plan Archive

These files preserve implementation plans and the reasoning available when each plan was written. They are historical records, not the current runtime contract.

Use these documents for current behavior:

- [`../PIPELINE.md`](../PIPELINE.md): architecture and data flow
- [`../OPERATIONS.md`](../OPERATIONS.md): operational contract and recovery
- [`../USER_GUIDE.en.md`](../USER_GUIDE.en.md): end-user behavior
- [`../../spec.md`](../../spec.md): evolutionary design record with supersession notes

## Plans

| Date | Plan | Current relationship |
| --- | --- | --- |
| 2026-04-23 | [Hermes agent integration](./2026-04-23-hermes-agent-integration-plan.md) | Historical source-adapter and folder-routing design; current wiki placement defaults to emergent root. |
| 2026-04-27 | [Distribution hardening](./2026-04-27-distribution-hardening-final-plan.md) | Historical packaging/release plan; current setup and release docs are canonical. |
| 2026-05-12 | [Maintenance refactoring](./2026-05-12-maintenance-refactoring-plan.md) | Historical refactoring proposal; typed finalize/runtime/transaction boundaries now supersede parts of it. |

When a plan conflicts with current code or canonical docs, treat the plan as superseded rather than editing history to look prescient.
