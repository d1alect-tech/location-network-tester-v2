# ADR-0001: Canonical raw sessions

## Status

Accepted for the LNT v2 redesign; implementation is deferred to later todos.

## Context

An LNT session must remain a reproducible capture rather than a container for every derived result. The current reader supports strict manifest schemas 1 and 2, and existing sessions may contain root-level analysis projections.

## Decision

The session directory is the canonical owner of immutable capture inputs:

```text
<session>/
  manifest.json
  ch1.npy
  ch2.npy                 # optional, exactly as declared by manifest.json
  context.json            # optional; ADR-0002
  context.events.jsonl    # optional; ADR-0003
  analyses/               # derived artifacts; ADR-0004
  metrics.json            # legacy projection; ADR-0005
  spectrum.csv            # legacy projection; ADR-0005
  spectrum_input_referred.csv  # legacy projection; ADR-0005
```

`manifest.json` remains strict schema v1 or v2. No manifest v3 is introduced. New context, analysis identity, or experiment metadata must not be hidden in the free-form `parameters` map. A schema-v1 session has no `ch1_setup`; input-reference correction therefore remains `status="unavailable"` with `reason_code="manifest_schema_v1"`.

Every multi-file owner writes to a sibling `<target>.partial-<unique>` path, flushes and closes all files, then renames into place. Readers ignore `.partial-*`. A failed writer removes its partial path when possible and never exposes a half-written canonical owner. This extends the atomic rule already used by session writes.

## Consequences

- Raw capture identity and compatibility stay stable across analysis changes.
- Optional sidecars may be absent without changing legacy behavior.
- Derived and compatibility files are clearly non-canonical.
- In-place mutation of raw files is forbidden; replacement requires a new session.
