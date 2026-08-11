# ADR-0006: Experiment storage outside session folders

## Status

Accepted for the LNT v2 redesign; implementation is deferred to later todos.

## Context

Experiments relate multiple sessions and analyses. Nesting an experiment under one session creates false ownership, encourages raw-session mutation, and complicates retention.

## Decision

The experiment subsystem owns `<storage-root>/experiments/<experiment-id>/`, as a sibling of the sessions collection and never inside a session. An experiment references sessions by stable session ID plus resolved storage reference and references analyses by artifact key and immutable `recipe_sha256`. It stores no authoritative copies of raw channels.

Experiment publication uses `<experiment-id>.partial-<unique>/` followed by rename. Published experiment revisions are immutable; changed membership or recipes produce a new revision/ID. Session deletion tooling must detect experiment references rather than cascading silently.

## Consequences

- Multi-session ownership is explicit.
- Sessions stay portable and capture-focused.
- Moving storage requires reference-resolution tooling.
- Retention and deletion require reference integrity checks.
