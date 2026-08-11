# ADR-0007: Identifier, time, and unit conventions

## Status

Accepted for the LNT v2 redesign; implementation is deferred to later todos.

## Context

Cross-file joins become unreliable when identifiers, timestamps, and units have implicit or inconsistent meanings.

## Decision

- IDs are opaque, case-sensitive ASCII strings. New generated IDs use lowercase UUIDv7 text without braces; existing manifest `session_id` values retain their current validated spelling.
- Filesystem keys (`artifact-key`, experiment IDs) use only lowercase ASCII letters, digits, `-`, `_`, and `.` and are not semantic identities unless explicitly declared.
- SHA-256 identities are 64 lowercase hexadecimal characters over specified canonical UTF-8 bytes.
- Persisted instants use RFC 3339 UTC with a `Z` suffix and explicit fractional precision; monotonic durations are never serialized as wall-clock timestamps.
- Field names carry units: `_s`, `_hz`, `_v`, `_ohm`, `_f`, `_v2_per_hz`, and `_utc`. SI base units are used unless a schema explicitly states otherwise.
- Counts and ordinals are integers; ratios are dimensionless finite numbers. NaN and infinity are forbidden in JSON.

These rules apply to context, events, analyses, recipes, and experiments. They do not rewrite frozen manifest v1/v2 bytes.

## Consequences

- Joins and dimensional review are mechanical.
- User-facing localized values require conversion at presentation boundaries.
- Existing identifiers are preserved rather than normalized destructively.
- Schemas must reject ambiguous unitless numeric fields.
