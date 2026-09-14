# Method notes: shared characterization computations

Status: implementation contract for the W4 preparation layer. It records settled
contracts for future family work. It does not mean W4 or any descriptor family is
complete.

This note is shared by
[`method-notes-families-1-9.md`](method-notes-families-1-9.md) and
[`method-notes-families-10-18.md`](method-notes-families-10-18.md). It follows
ADR-0004, ADR-0007, and ADR-0008. The existing recipe bytes, method versions,
raw-session schemas, and legacy PSD stream remain unchanged.

## Scope and ownership

- Shared computation occurs once inside one later characterization branch. It is
  not legacy cross-branch shared state and does not change existing analyses.
- W4 preparation adds no API or CLI route. Family enablement and artifact
  publication belong to later work.
- Input arrays are immutable saved volts. They are never scaled again. Historical
  absence of calibration coefficients neither invalidates measured quantities
  such as `sum(x^2) / fs` in `V^2 s` nor turns them into input-referred values.
- Full-record methods use the complete qualified record. Complex transforms and
  windowed summaries have no implicit 2.4 s crop.

## Phase and residual

- The full-record phase root is measured CH2 only. Detect fractional rising zero
  crossings and interpolate their sample positions. There is no nominal-frequency
  phase and no CH1 fallback.
- Phase-dependent support ends at missing or unqualified spans. A family reports
  domain unavailability when the qualified phase support is insufficient.
- F01 evaluates every complete 0.2 s window in the qualified record.
  `window_count = 12` is minimum support, not a request to select twelve windows.
- Shared residual input is `float64`, formed from saved volts and the declared
  phase-conditioned mean. Raw arrays remain untouched.

## Complex STFT

- Use SciPy 1.14's periodic Hann, equivalent to
  `get_window("hann", L, fftbins=True)`, and constant detrending.
- For frame start `s`, compute the complex spectrum after detrending and windowing
  as `FFT(frame * window) / sum(window)`. Units are volts. A real input produces
  its one-sided spectrum without doubling non-DC bins.
- `hop = max(1, round(L * (1 - overlap)))`. Frames are anchored to sample zero in
  the native sample grid. Keep only complete frames, with
  `centre_s = (s + L / 2) / fs`; use `boundary=None` and `padded=False` semantics.
- A frame cannot cross a qualified gap. Do not interpolate across gaps, insert
  zeros, or shift frame anchors to recover support.
- The shared complex STFT does not replace or alter the legacy PSD stream.

## Band resolution

- Store requested edges, effective edges, and original band index. Set
  `effective_high_hz = min(requested_high_hz,
  recipe.stft.nyquist_fraction_max * fs)`.
- Membership is left-closed and right-open. The final requested interval includes
  its effective upper edge after clamping.
- Preserve requested gaps. Never stretch neighboring bands to meet, interpolate a
  missing band, or reorder bands after resolution.
- F13's `filter_edge_guard_fraction = 0.01` is frequency-domain band-power QC,
  not temporal padding.

## Bounded local transforms

- The phase transform is a fourth-order 200 Hz Butterworth low-pass in SOS form,
  followed by fractional rising-zero-crossing detection. Its initial per-side halo
  is `H = max(default_sos_padlen, ceil(log(1e-6) / log(max_pole)))`, where
  `max_pole` is the largest pole magnitude. This decay scale initializes the
  convergence check; it is not a universal error guarantee.
- Compare the filtered real transforms from halos `H` and `2H` over the same
  actual core before any Hilbert transform. Accept `2H` only when
  `maxabs(y_2H - y_H) <= max(1e-3 * maxabs(y_2H),
  1e-9 * maxabs(raw_expanded_block))`. On failure, double the halo and replan a
  smaller core only when both expanded reads and the conservative work budget
  fit. The relative tolerance is one tenth of the 1 percent envelope criterion;
  the raw-scale term handles strongly rejected outputs without an implicit
  one-volt floor.
- Each core is at most `recipe.resource_limits.chunk_samples`. For a real
  transform, shrink it as needed so capacity `C - 4H` remains positive; for an
  analytic transform with fixed per-side Hilbert context `A`, use
  `C - 2A - 4H`. Never shrink a scientifically required halo to make a read fit.
  At 5 MHz the 200 Hz phase filter has initial
  `H` about 143644 and fits the default 1048576-sample cap. At 48 MHz initial `H`
  is about 1378983, so phase is unavailable without hidden decimation.
- Every accepted core requires real context on both sides. Record boundaries,
  qualified gaps, and failed convergence produce unsupported spans. Do not create
  observations with reflection, zeros, interpolation, or other synthetic padding.
- F06 applies constant detrending before its local SOS filter and Hilbert
  transform. F13 filters the raw saved volts, takes the Hilbert-envelope magnitude,
  then subtracts the phase-conditioned envelope mean. Both use fixed per-side
  Hilbert context `A = 16384` samples: after real-filter qualification, run
  `hilbert` once on the fixed `core +/- A` window and retain only the core. A
  1 MHz AM qualification recovered the declared envelope with maximum absolute
  error below `9e-5`, against the 1 percent criterion. Local Hilbert results are
  not claimed to equal one full-record Hilbert transform.
- A repeated run with the same fixed recipe is deterministic. Chunk size is hashed
  recipe input; changing it carries no promise of bitwise-invariant output.

## Root events

- The root detector uses the existing centered 4001-sample median/MAD noise
  estimate with step 256 and minimum noise support 2000, then the recipe threshold
  `5 sigma`, minimum linear SNR `10 ** (10 / 20)`, maximum gap 8 samples, and
  minimum run 1 sample.
- Candidate-run merging is part of detection and is independent of dead time.
  Apply nonparalyzable peak-time dead time of
  `ceil(recipe.events.dead_time_s * fs)` samples from the last accepted qualified
  event. A rejected event does not extend the interval.
- Event order is peak time with stable original-index tie breaking. Retain the
  first events in that order up to the cap, but continue scanning to EOF so total,
  rejected, clipped, and unavailable counts describe the full stream.
- Sequence and adjacency consumers replay the uncapped accepted stream. Sampling
  omissions are never joined as neighbors. Persisted examples remain bounded.
- Measured event severity is `sum(x^2) / fs` in `V^2 s`. It is distinct from the
  legacy `excess_v2_s` baseline-excess quantity.
- Unknown clipping blocks only quantities that require proven unclipped support.
  Other event metadata remains available when its own support is qualified.

## Clipping qualification

- Locate hardware clipping only when device telemetry says
  `calibration_used = false` and the positioned nominal rail thresholds can be
  derived from the channel range and probe scale. Compare those thresholds with
  the already-scaled saved volts.
- Clipping location is unknown when calibration provenance is missing, historical,
  or says calibration was used. Aggregate telemetry rail counts describe the
  capture but cannot locate events or spans.
- A source declared synthetic with synthetic truth and a synthetic front end makes
  hardware clipping not applicable. This is a property of the ideal generator,
  not proof that a physical device was observed unclipped.

## Resources, failure, and cancellation

- Honor recipe chunk, work-memory, artifact, trajectory, event, surrogate, and
  stored-cell limits. Preparation retains bounded summaries and memory-map
  references, not N-sample phase arrays or band-envelope matrices. Public
  residual requests are caller contracts: spans larger than
  `min(hard_max_chunk_samples, max_work_bytes // 64)` raise `InputError` before
  any allocation, and oversized slice requests never become `reason_code` data.
- Resource bounds use conservative working-memory estimates, not an exact process
  RSS guarantee. Mutually inconsistent requested budgets are typed input errors.
  With valid budgets, genuinely insufficient mathematical context yields
  unavailable support with a stable `reason_code`.
- Check cancellation during bounded scans and before expensive transforms.
  Supported phase-cycle refusals distinguish retained-cycle exhaustion
  (`phase_cycle_work_budget_too_small`) from unusable SOS context
  (`phase_transform_work_budget_too_small`); only a genuinely missing or invalid
  CH2 reference keeps `phase_reference_unavailable`. Envelope preparation
  preserves transform reasons (`filter_support_too_short`,
  `filter_context_unstable`, `nonfinite_input`, `band_above_nyquist`) and uses
  `mixed_unavailable_support` only for heterogeneous gaps. Checkpoint before
  each unavailable chunk and once after normal exhaustion; cancellation
  propagates by identity on unavailable as well as supported paths.
  Unexpected exceptions also propagate as defects.
- Only expected mathematical or domain unavailability becomes a stable
  `reason_code`. Other input contract violations keep their existing typed error
  behavior; they are not rewritten as scientific unavailability.

## Claim boundary

These computations describe saved measurements at their declared channel planes.
They do not establish calibration, compliance, source identity, coupling,
direction, causation, or primary-side behavior.
