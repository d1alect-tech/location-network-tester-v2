# ADR-0005: Root legacy analysis projections

## Status

Accepted for the LNT v2 redesign; implementation is deferred to later todos.

## Context

Existing CLI, UI, and external consumers read `metrics.json`, `spectrum.csv`, and `spectrum_input_referred.csv` from the session root. Moving canonical artifacts must not silently break those readers.

## Decision

Root analysis files remain compatibility projections owned by the analysis projection subsystem. They project one explicitly selected artifact from `analyses/<artifact-key>/`; they are never the canonical identity or provenance record. Their current names and formats remain available while compatibility is supported.

Projection publication stages every projected file in `.partial-<unique>` paths and renames only complete files. A projection selector is updated last using the same atomic rule. Readers ignore partial files. If no selected compatible artifact exists, projections may be absent; consumers must not fabricate analysis from raw data during a read.

## Consequences

- Legacy consumers continue to work during migration.
- Root files may change when the selected artifact changes, while canonical artifacts remain immutable.
- Consumers needing reproducibility must resolve the selected artifact and its `recipe_sha256`.
- Projection retirement requires a separate compatibility decision.
