# ADR-0002: Optional `context.json` schema 1

## Status

Accepted for the LNT v2 redesign; implementation is deferred to later todos.

## Context

Capture context evolves independently from the strict hardware manifest. Putting context fields in `manifest.json.parameters` would evade strict validation and couple manifest compatibility to metadata growth.

## Decision

`<session>/context.json` is an optional materialized context document owned by the context subsystem. Its top-level `schema_version` is exactly `1`; unknown top-level fields are rejected. It contains the latest accepted values plus provenance for site, environment, operator observations, equipment, and tags. Domain schemas introduced by the implementation todo must use explicit typed fields, stable machine keys, and the conventions in ADR-0007.

Absence means “no structured context recorded,” not an error and not an empty inferred object. Context fields never appear in `manifest.json.parameters`. Writers use `context.json.partial-<unique>` followed by rename; readers ignore partial files.

## Consequences

- Manifest schemas v1/v2 remain unchanged and strict.
- Context can evolve under its own explicit schema migration policy.
- Consumers must distinguish absent context from present-but-empty values.
- `context.events.jsonl` is the provenance source described by ADR-0003.
