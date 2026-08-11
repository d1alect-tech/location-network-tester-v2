# ADR-0008: Error taxonomy

## Status

Accepted for the LNT v2 redesign; implementation is deferred to later todos.

## Context

Storage and compatibility failures must remain machine-classifiable. The current CLI maps `InputError` to exit 2, `DeviceNotFoundError` to exit 3, and treats unexpected exceptions as defects.

## Decision

The existing typed hierarchy remains authoritative:

- `InputError`: malformed, unsupported, unsafe, inconsistent, missing, or conflicting persisted/user input, including unknown schema fields and unsupported versions (CLI exit 2).
- `DeviceNotFoundError`: unavailable hardware, driver, firmware, or interrupted device transport (CLI exit 3).
- `AnalysisError`: valid readable input for which the requested analysis is mathematically unavailable.
- Unexpected exceptions: programming defects; they are not converted to compatibility or availability outcomes.

Expected domain unavailability is data, not an exception: results use stable `status` and `reason_code` values. In particular, legacy manifest schema v1 without `ch1_setup` yields input-reference `status="unavailable"` and `reason_code="manifest_schema_v1"`.

New sidecar and artifact parsers raise typed `InputError` for unsupported schema versions, unknown fields, torn JSONL lines, identity mismatch, or ownership conflicts. Error messages may be localized; callers branch on type and stable reason codes, never prose.

## Consequences

- CLI behavior and automation remain predictable.
- Unsupported future data fails closed instead of being partially accepted.
- Normal scientific unavailability remains reportable alongside successful raw analysis.
- Later todos may add typed subclasses only when callers need finer machine handling.
