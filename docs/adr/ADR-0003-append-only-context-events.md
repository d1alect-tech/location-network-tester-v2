# ADR-0003: Append-only `context.events.jsonl`

## Status

Accepted for the LNT v2 redesign; implementation is deferred to later todos.

## Context

A materialized context snapshot cannot explain who changed a value, when it changed, or which observation it replaced. Rewriting history would weaken auditability.

## Decision

`<session>/context.events.jsonl` is an optional append-only UTF-8 event log owned by the context subsystem. Each newline-terminated JSON object has an explicit event schema version, event ID, session ID, UTC timestamp, event kind, typed payload, and provenance. Events are never edited, reordered, or deleted. Unknown event versions or kinds are typed input failures, not silently skipped.

The log is absent when no event has been recorded. `context.json` is a rebuildable projection of accepted events, while the event log is provenance. Append uses a lock, writes and flushes one complete line, then releases the lock. Creation or compaction uses a sibling `.partial-<unique>` file and rename; torn final lines are reported as input errors.

## Consequences

- Context history is auditable and replayable.
- Writers require cross-process append serialization.
- Snapshot and log consistency can be checked and repaired from events.
- Legacy sessions without either sidecar retain existing behavior.
