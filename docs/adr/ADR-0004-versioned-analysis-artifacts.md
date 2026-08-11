# ADR-0004: Versioned analysis artifact directories

## Status

Accepted for the LNT v2 redesign; implementation is deferred to later todos.

## Context

Root analysis files are overwritten by reruns and cannot safely identify the code, options, or inputs that produced them. Artifact lookup and recipe identity are different concerns.

## Decision

The analysis subsystem owns `<session>/analyses/<artifact-key>/`. `artifact-key` is a stable filesystem-safe lookup key for one published artifact set. Each directory contains typed metadata, metrics, and applicable tabular outputs. Its metadata stores an immutable `recipe_sha256`: the lowercase SHA-256 digest of the canonical recipe document containing algorithm/version, normalized options, declared inputs, and relevant dependency identities.

`artifact-key` is not the recipe identity and must not be treated as its digest. Reusing an existing key is allowed only when its stored `recipe_sha256` and declared input identities match exactly; otherwise publication fails. Completed artifact directories are immutable.

Publication builds `analyses/<artifact-key>.partial-<unique>/`, closes all files, then renames it to `analyses/<artifact-key>/`. Readers ignore partial directories. The analysis subsystem owns all files below `analyses/`; raw-session and context writers must not modify them.

## Consequences

- Multiple analyses coexist without rewriting raw data.
- Recipe equality is content-addressed independently of human lookup names.
- Canonical recipe serialization becomes a tested compatibility surface.
- Garbage collection must preserve artifacts referenced by projections or experiments.
