# Method notes: descriptor families 1-9

Status: implementation contract. This document fixes methods for future code
and tests. It is not evidence that any family is implemented or queued.
Companion to `docs/electrical-signal-characterization-proposals.md` (families 1-9 of
the 18-family list). Grounded in the current stack: numpy/scipy only, no new
dependencies, ADR-0004 versioned artifacts, ADR-0007 unit-suffixed fields,
ADR-0008 reason codes for expected unavailability.
Shared phase, STFT, band, event, clipping, and resource contracts are fixed in the
[shared computation notes](method-notes-shared-computations.md).

Language note: the operator- and science-facing docs are Russian; these algorithm
notes are English because the downstream consumers are versioned code and tests.

## Conventions shared by all nine families

- **Input.** One real series `x[n]`, `n = 0..N-1`, samples in volts, sampling rate
  `fs` Hz. CH1 is the 3 kHz-3 MHz RC front end; CH2 is the 230:6 transformer
  reference. Per-channel planes are never mixed without declaring it.
- **Reference phase.** The only phase datum available is the measured rising zero
  crossing of CH2 (the same convention already used by needle sync windows and
  `line_quality._envelope_stability`). No absolute phase of the CH1 probe/RC tract
  exists: `swept_response.py` stores only `|H(f)|`, not a complex transfer
  function, so no primary-side (line-side) phase claim is permitted. Families 1,
  5 and 6 therefore report *relative* phase and *relative* timing only.
- **Expected unavailability is data, not an exception** (ADR-0008). Each family
  returns `status`/`reason_code`; never `0`, `""` or `NaN` as a stand-in.
- **Determinism.** Fixed seeds, fixed parameters, byte-stable outputs. Recipe and
  parameter set are content-addressed (`recipe_sha256`, ADR-0004).
- **No confidence intervals are invented.** Every tolerance kept in a test is an
  analytic bound. Statistical uncertainty comes only from independent repeats
  (scientific-manual Type A/B), never from a single record.
- **Circular quantities.** Averaging angles is forbidden. Average unit vectors
  `e^{j phi}`, report the resultant length `R in [0,1]` and the mean direction;
  `R` below its declared floor is an explicit reason code.
- **Leakage control.** Line families use IEC synchronous resampling (integer
  number of cycles in the window) so a rectangular DFT window is exact. Non-
  synchronous line detection uses Hann/Blackman and must pass a two-window
  invariance check; a peak that moves with the window is flagged, not reported.
- **Decimation.** No default recipe decimates. Any deliberately decimated derived
  series is a separate versioned method and MUST apply an anti-alias low-pass
  before the integer stride. `scipy.signal.decimate` uses an order-8 Chebyshev
  type-I anti-alias filter and `filtfilt` zero-phase by default [SCIPY-DECIMATE];
  even-order Chebyshev passband ripple attenuates the passband, a known SciPy
  behaviour [SCIPY-9402]. The declared recipe therefore fixes an explicit
  Butterworth `sos` design plus `stride`, and records filter order, cutoff and
  attenuation in the artifact. Downstream functions that assume `fs` must receive
  the decimated rate, never the original.
- **SI field names** follow ADR-0007: `_s`, `_hz`, `_v`; counts are integers,
  ratios are dimensionless. Two suffixes used below extend the ADR-0007 list:
  `_v2_s` (V^2 s) and `_rad` (radians). The consuming schema must define both
  suffixes explicitly.

---

## Family 1 - Phase-aligned cycle shape and relative harmonic phase

**Quantities.** Grid frequency `f1_hz` (Hz); aligned cycle template `x_template_v`
(V) over `theta in [0, 2pi)`; complex Fourier coefficients `c_k_v` (V) for
`k = 1..40`; relative phase `phi_rel_k_rad` (rad, dimensionless); vector-average
resultant `phase_resultant_k` (dimensionless, `0..1`).

**Algorithm.**
1. Per 200 ms window, estimate `f1` by parabolic interpolation on the H1 peak of a
   Hann-windowed FFT, then refine with one Quinn-Fernandes frequency step
   [QUINN91]. Clamp to the plausible grid band; a value outside it is
   `grid_unstable`.
2. Resample exactly 10 cycles (`10 / f1` seconds) to `N0 = round(0.2 * fs)`
   samples by linear interpolation of sample positions. This reproduces the IEC
   61000-4-7 synchronous 10/12-cycle rectangular DFT [IEC-4-7], whose bin spacing
   is `1 / 0.2 s = 5 Hz` with harmonics on integer bins.
3. `X = rfft(resampled)`. One-sided coefficient `c_k = (2/N0) * X[10k]` for
   `k = 1..40` (amplitude in volts).
4. Reference the phase: `phi_rel_k = arg(X[10k]) - k * arg(X[10])`, wrapped to
   `(-pi, pi]`. This cancels any whole-window time shift `t0`, because that shift
   multiplies `X[10k]` by `exp(-j 2 pi (10k) t0 / T)`.
5. Across every complete 200 ms window in the qualified record, vector-average
   `exp(j phi_rel_k)`; report
   `phase_resultant_k` and the circular mean direction. Build the template from
   the vector-averaged complex `c_k`.

**Parameters.** window `0.2 s`; minimum windows `12` (`window_count = 12` in the
frozen recipe); cycles `10`; `Hmax = 40`; `N0 = round(0.2 * fs)`; interpolation
`linear`; plausible grid band
`47.5..52.5 Hz`; phase-resultant floor `Rmin = 0.8`; H1 concentration ratio
floor `0.95` [IEC-4-7].

**Prerequisites and failure conditions.** At least 12 complete 200 ms windows;
`f1` inside the plausible band; H1 above `eps_level`; a CH2 sync reference (single-
channel mode has none). A wrong `f1` reintroduces leakage; the harmonic-group
energy concentration ratio is checked and trips `grid_unstable`.

**Reason codes.** `grid_unstable`, `fundamental_absent`, `window_too_short`,
`phase_unstable` (resultant below floor), `no_sync_reference` (single-channel
mode; `unavailable`, never zero phase).

**Complexity.** `O(W * N0 log N0)` for every complete qualified window, with
bounded accumulators and no full-record window matrix.

**Analytic validation.**
- Positive: a synthetic waveform built from declared amplitudes and phases
  recovers `c_k` within `1 %` (verified `0.33 %` at 16 384 Hz, 10 cycles) and
  `phi_rel_k` within `0.02 rad`; the template matches the analytic shape. A pure
  time shift of the same waveform leaves `phi_rel_k` invariant (verified drift
  `0.0066 rad`, set by the linear-interpolation error of the synchronous
  resampler). The threshold is 0.02 rad, not the 0.01 rad first sketched, so the
  specified linear interpolation passes with margin.
- Control: two waveforms with identical `|c_k|` but conjugate phase spectra must
  yield templates related by time reversal and clearly different `phi_rel_k`;
  equal magnitudes must not collapse to equal shape.
- Limitation: a window whose true content is 9.7 cycles must trip
  `grid_unstable` by the H1 concentration check. Verified: a 10-cycle window
  gives `H1_energy / (H1 +/- 3 bins) = 1.000`, a 9.7-cycle window `0.756`; the
  declared pass threshold is `>= 0.95`.

**Claim boundary.** All phases are relative to the measured fundamental at the
scope/transformer plane. No primary-side phase, no absolute propagation delay.

---

## Family 2 - Amplitude, time-shift and shape separation

**Quantities.** Per event: amplitude scale `a` (dimensionless); time shift
`tau_s` (s); residual fraction `rho` (dimensionless) and squared residual integral
`e_res_v2_s` (V^2 s).

**Algorithm.**
1. Take the family-1 phase-aligned template as `v(t)`.
2. For each delimited event span `y(t)` with a baseline removed, minimise
   `J(tau) = ||y||^2 - <y, v_tau>^2 / ||v_tau||^2` over `tau` on a sub-sample
   grid (FFT cross-correlation for the coarse scan, parabolic refine). For each
   `tau`, `a_hat(tau) = <y, v_tau> / <v_tau, v_tau>` is closed-form.
3. `tau* = argmin J`; `a = a_hat(tau*)`; residual `r = y - a * v_tau*`.
   Report `a`, `tau_s`, `rho = ||r|| / ||y||`, `e_res_v2_s = ||r||^2 * dt`.

**Parameters.** sub-sample `tau` grid step `1 / (64 fs)`; minimum event SNR
`10 dB`; `rho_max = 0.25`; template identity
`f01_phase_cycle:x_template_v`; maximum events `4096`.

**Prerequisites and failure conditions.** The family-1 template; baseline from
the median of the two event-length intervals immediately before and after the
event; events not overlapping. Overlap makes `(a, tau)` non-unique and must be
flagged.

**Reason codes.** `template_unavailable`, `overlapping_events`, `event_truncated`,
`below_snr`, `baseline_unavailable`.

**Complexity.** `O(K * L log L)` for `K` events of length `L` (FFT correlation);
the exhaustive native form is `O(K * L * |tau grid|)`.

**Analytic validation.**
- Positive: events built as `a0 * v(t - tau0)` plus noise recover `a0` and `tau0`
  to within the sub-sample step and `rho` near the noise floor (verified
  integer-grid: `a = 1.7000` for `a0 = 1.7`, `tau = 37` samples for `tau0 = 37`,
  `rho ~ 0`).
- Control: a pure time shift with no gain/shape change must give `a = 1`,
  `rho ~ 0`, `tau =` known shift (verified exact: `a = 1.000000`, `tau = 50`).
  This separates jitter from shape.
- Limitation: two overlapping events must trip `overlapping_events`; a single
  fit must not split the pair into a plausible `a`/`tau` pair.

---

## Family 3 - Interharmonic and subharmonic tracking

**Quantities.** Per track: centre frequency `f_hz` (Hz), amplitude `a_v` (V),
width `df_hz` (Hz, FWHM or -3 dB), lifetime `t_life_s` (s), presence mask and
explicit gaps.

**Algorithm.**
1. Reuse the existing IEC interharmonic groups (`ihg` in
   `harmonics.detector._window_metrics`) plus subharmonic bins below H1
   (`f1/2`, `f1/3`, ...). Bins come from the synchronous 10-cycle DFT, `5 Hz`
   spacing [IEC-4-7].
2. Per window, mark lines above a local median floor plus a declared margin.
   Estimate each line's centre and width from its bin group (energy centroid,
   half-power edges, as `features.spectral._peak_feature` already does).
3. Associate lines across windows with the existing nearest-neighbour tracker
   `features.tracking.track_peak_trajectories` inside a frequency tolerance; do
   not interpolate across gaps, record `peak_not_observed`.
4. Width is resolution-limited: `df >= 1 / T_window`.

**Parameters.** bin spacing `5 Hz` (200 ms window); association tolerance
`2 bins = 10 Hz`; detection margin `6 dB` above the local median of the nearest
`11` non-harmonic bins; minimum lifetime `3 windows = 600 ms`; subharmonic
orders `{2, 3, 4}`; maximum stored tracks `4096`.

**Prerequisites and failure conditions.** At least two windows for a track;
synchronous grid; no two lines closer than one bin.

**Reason codes.** `below_resolution` (lines within one bin), `peak_not_observed`,
`track_too_short`, `leakage_ambiguous`, `grid_unstable`.

**Complexity.** `O(W * B)` detection plus `O(W * K log K)` association; `B` bins,
`K` lines.

**Analytic validation.**
- Positive: a tone at `(h + 0.5) * f1` is tracked at the correct bin with
  lifetime equal to the record.
- Control: a pure harmonic-only signal must yield no sustained interharmonic
  track; spurious single-window detections must not form a track.
- Limitation: an interharmonic within one bin of a harmonic must trip
  `below_resolution`, not be reported as a separate resolved line.

---

## Family 4 - Multicycle periodicity

**Quantities.** Fractional frequency deviation `y` (dimensionless); Allan
deviation `adev` versus averaging time `tau_s` (s) [IEEE-1139]; phase slip
(cycles, dimensionless); carrier-to-mains frequency ratio (dimensionless).

**Algorithm.**
1. Two independent paths. (a) Narrowband carrier: from the family-6 unwrapped
   phase, or from the fitted H1 phase per cycle, form the cycle-frequency series;
   convert to fractional frequency `y_i = (f_{i+1} - f_i) / f0`. (b) Mains:
   cycle durations from CH2 rising zero crossings.
2. Overlapping Allan variance: with `ybar_i^(m)` the mean of `m` consecutive
   `y`, `sigma_y^2(m tau0) = 1/(2 (N - 2m + 1)) * sum_i (ybar_{i+m}^(m) -
   ybar_i^(m))^2`; `ADEV = sqrt`. Report `ADEV` against `tau = m tau0`.
   Plain standard deviation is explicitly not used for a drifting series
   [ALLAN87], [IEEE-1139].
3. Reveal period-N structure by autocorrelation of the cycle-duration series at
   integer lags `1..32` cycles. The result is descriptive only.

**Parameters.** `tau0` = one cycle; averaging factors
`m = {1, 2, 4, 8, 16, 32}` restricted to `m <= floor(N/3)`; minimum `100`
cycles; carrier band from family 6; carrier SNR gate `10 dB`; autocorrelation
lags `1..32` cycles.

**Prerequisites and failure conditions.** At least 100 mains cycles (record
>= 2 s at 50 Hz), per the base rule; consistent `f1`; sufficient carrier SNR for
path (a); at least three independent averaging intervals for a given `tau`.

**Reason codes.** `record_too_short_for_tau` (no extrapolation beyond record),
`carrier_unavailable`, `phase_unwrap_failed`, `not_enough_samples`,
`grid_unstable`.

**Complexity.** `O(N * L)` for `N` cycles and `L` averaging factors; at ~120
cycles this is trivial.

**Analytic validation.**
- Positive: a synthetic frequency-modulated mains/carrier with white FM noise of
  known level recovers the ADEV level and slope.
- Control: a pure stable tone must produce zero ADEV to floating-point tolerance
  and must not show a period-2 band; the method must not invent multicycle
  structure.
- Limitation: `tau` beyond one third of the record returns
  `record_too_short_for_tau`; no interval is fabricated.

---

## Family 5 - Phase-conditioned mean and spread

**Quantities.** Over `M` uniform phase bins `theta_b`: coherent mean `mu_v` (V),
variance `sigma2_v2` (V^2), mean square `ms_v2` (V^2), event probability
`p_event` (dimensionless), support `n_b` (integer).

**Algorithm.**
1. Build phase `theta(t)` from the CH2 rising-zero-crossing reference or the
   fitted `f1`; wrap into `[0, 2pi)`.
2. Accumulate per sample (or per STFT window) into bins: `x`, `x^2`, and the
   binary event indicator from the root event inventory.
3. Per bin report `mu = mean(x)`, `sigma2 = var(x, ddof=1)`, `ms = mean(x^2)`,
   `p_event = mean(indicator)`, `n_b`.
4. For the event-phase distribution report the circular resultant `R` and mean
   direction (unit-vector average), never a linear mean of angles [MARDIA-JUPP].

**Parameters.** `M = 64` uniform bins over the cycle; minimum support
`n_min = 20` per bin; event threshold and dead time from the root `events`
recipe block.

**Prerequisites and failure conditions.** Reliable phase reference; at least
`M * n_min` samples for full support; single-channel mode is `unavailable`.

**Reason codes.** `phase_reference_unavailable`, `insufficient_support`,
`few_cycles`, `bin_empty` (per bin).

**Complexity.** `O(N)` accumulation.

**Analytic validation.**
- Positive: a Gaussian amplitude burst locked to a known phase produces `mu` and
  `sigma2` peaking at that phase and a near-delta `p_event` there.
- Control: drawing an independent uniform carrier phase per realization drives
  the coherent `mu` toward zero in every bin (verified: max `|mu| = 0.038` over
  500 draws) while the mean square stays uniform across bins (verified:
  `ms = 0.500 +/- 0.003`, matching `A^2/2 = 0.5`). Random phase kills the
  coherent mean, not the variance.
- Limitation: too few cycles leave most bins empty and must return
  `insufficient_support`; injected phase jitter must widen the peak, which the
  test measures rather than tolerates away.

---

## Family 6 - AM, FM and phase trajectories

**Quantities.** Envelope `a_v(t)` (V); unwrapped phase `phi_rad(t)` (rad);
instantaneous frequency `f_inst_hz(t)` (Hz); modulation depth and rate.

**Algorithm.**
1. Band-pass the qualified narrowband component (Butterworth `sos`, zero-phase
   `sosfiltfilt`); band and order are recipe-declared.
2. Analytic signal `z = x_a + j * hilbert(x_a)`; `A = |z|`; `phi = unwrap(angle(z))`;
   `f_inst = (1 / 2 pi) * d(phi)/dt` by central difference.
3. Guard the Bedrosian validity: the envelope spectrum must occupy frequencies
   below the carrier band, otherwise the Hilbert envelope/phase split is
   meaningless [BEDROSIAN63]. Guard the Itoh condition: `|phi[n+1] - phi[n]| < pi`
   between adjacent samples, i.e. no phase aliasing [ITOH82].

**Parameters.** band `10000..50000 Hz`; Butterworth order `4`; zero-phase
filtering; constant detrend; minimum SNR `10 dB`; maximum components in band
`1`; envelope-zero floor `0.01` times median envelope; maximum `4096` stored
trajectory samples selected at evenly spaced indices.

**Prerequisites and failure conditions.** One dominant component in band;
narrowband (`df << f0`); no envelope zeros.

**Reason codes.** `multiple_components`, `low_snr`, `envelope_zero`,
`band_invalid`, `phase_aliased`.

**Complexity.** `O(N log N)` Hilbert plus `O(N)` phase/frequency.

**Analytic validation.**
- Positive: AM at depth `d` and rate `fm` recovers `A = 1 + d cos(2 pi fm t)`
  and constant `f_inst` (verified depth error `4e-13` for `d = 0.5`); FM with
  deviation `df` and rate `fm` recovers `f_inst = f0 + df cos(2 pi fm t)` at
  constant `A` (verified `(fmax - fmin)/2` within `0.005 Hz` of `df = 50 Hz`, and
  `max |dphi| = 0.79 rad < pi`, so the Itoh condition holds).
- Control: two tones inside the band must trip `multiple_components`; the method
  must not emit a plausible-looking but meaningless trajectory.
- Limitation: over-modulation (`d > 1`) creates envelope zeros and `f_inst`
  spikes; they must trip `envelope_zero`.

**Claim boundary.** `phi` is the analytic phase of the measured bandpass signal;
it is not the phase of the primary-side voltage.

---

## Family 7 - Comb, sideband and cepstrum

**Quantities.** Component spacing `df_hz` (Hz); sideband symmetry `sym_db` (dB);
cepstral peak quefrency `q_s = q_samples / fs` (s) and amplitude.

**Algorithm.**
1. Window the frame (Hann), compute `|X[k]|`, and take
   `L[k] = log(|X[k]| + floor)`, where `floor` is a declared fraction of
   `max|X|` bounding the log near nulls; then `L -= mean_k L` to remove the
   excitation envelope [BOGERT63]. The window is mandatory: a rectangular frame
   with a deep floor made the dominant cepstral peak jump to the Nyquist end for
   a 33-sample repetition during verification, while a Hann frame with a 20 dB
   floor recovered `q = 33` exactly.
2. Real cepstrum `c[q] = Re(IFFT(L))`; the dominant peak at quefrency `q*` in
   samples gives spacing `df = fs / q*`. In persisted units
   `q_s = q* / fs`, so `df = 1 / q_s`. Restrict the search to `q >= 2` and
   above the frame autocorrelation width. Cross-check the spacing by
   autocorrelation of the magnitude spectrum.
3. Sideband symmetry: for a carrier bin `k0`, `sym_db = 10 log10(P[k0+j] /
   P[k0-j])`; aggregate asymmetry over the declared offsets.
4. Compute with a second window (different family and/or length). A peak that
   moves is `window_dependent` and is not reported.

**Parameters.** FFT length `16384`; window pair Hann and Blackman; log floor
`20 dB` below the spectral maximum; minimum quefrency `2` samples; symmetry
offsets `{1, 2, 3, 4, 5}` bins; window-invariance tolerance `1` bin.

**Prerequisites and failure conditions.** Spacing resolvable by the transform,
i.e. `df` above the bin/frequency resolution; mains harmonics themselves form a
comb at `f1` and must be identified as that comb, not as new modulation; window
sidelobes form a comb and must be excluded by the invariance check [HARRIS78].

**Reason codes.** `window_dependent`, `harmonic_comb_only`,
`no_dominant_quefrency`, `below_resolution`, `log_floor_unstable` (the
dominant quefrency changes under the declared floor).

**Complexity.** `O(N log N)`.

**Analytic validation.**
- Positive: a periodic pulse train with known repetition `T` samples gives a
  cepstral peak at `q = T` and comb spacing `fs / T` (verified at
  `T = 33, 100, 200` samples with a Hann frame and a 20 dB log floor).
- Control: a pure harmonic comb at `f1` is labelled `harmonic_comb_only`; the
  peak must not shift when the window changes.
- Limitation: spacing at or below resolution must trip `below_resolution`; a
  40 dB log floor at `T = 33` jumped the peak to the frame edge during
  verification, so the floor is a declared, tested parameter, not a free knob.

---

## Family 8 - Transient morphology and decay

**Quantities.** Rise time `t_rise_s` (s); peak `v_peak_v` (V); integral
`v2s` (V^2 s); zero crossings `n_zc` (integer); ringing frequency `f_d_hz` (Hz);
decay time constant `tau_d_s` (s); damping ratio `zeta` (dimensionless).

**Algorithm.**
1. Baseline-detrend within the root event bounds plus a guard interval equal to
   one event duration on each side.
2. Initialize `f_d` from the zero-crossing count over the event and `tau_d` from
   the log decrement of successive envelope-peak magnitudes: `delta = ln(a_n /
   a_{n+1})`, `zeta = delta / sqrt(4 pi^2 + delta^2)`, `tau_d = T_d / delta`.
3. Fit `y = A exp(-t / tau_d) sin(2 pi f_d t + phi) + c` with a bounded nonlinear
   least squares (`scipy.optimize.least_squares`, boxed, few parameters) seeded
   from step 2. The primary is closed-form log-decrement plus the fit; the
   More than one resolved mode returns `multimode`; this method does not fit a
   multi-mode fallback.
4. Report the fit residual; a high residual flags a shape the single damped
   sinusoid does not describe.

**Parameters.** guard interval `1` event duration per side; `f_d_hz` bounds
`100..100000`; `tau_d_s` bounds
`1/fs..0.1`; amplitude bound `0..2 * v_peak_v`; phase bounds `-pi..pi`;
maximum `200` function evaluations; SNR gate `10 dB`; `rho_max = 0.25`;
clipping fraction and event bounds from the root `events` recipe block;
maximum fitted events `4096`.

**Prerequisites and failure conditions.** Non-clipped event; adequate SNR;
enough samples for at least a few oscillations; a single dominant mode.

**Reason codes.** `clipped`, `single_exponential_poor`, `below_snr`,
`too_few_samples`, `overlapping_events`, `multimode`.

**Complexity.** `O(K * L * iters)` for `K` events of length `L`.

**Analytic validation.**
- Positive: `A exp(-t/tau) sin(2 pi f t)` with known `tau`, `f` recovers both
  within `1 %` (verified: zero-crossing `f_d = 2000.0 Hz` exact,
  log-decrement `tau = 0.002000 s` against `0.002 s`).
- Control: a single short impulse with no ringing must not produce a fitted
  resonant frequency; `n_zc < 2` or a high residual must trip a reason code.
- Limitation: two superimposed modes drive the residual up and flag
  `single_exponential_poor`; one exponential is not forced onto a real decay
  [PROPOSALS].

---

## Family 9 - Event ordering and waiting times

**Quantities.** Typed event sequence (polarity, dominant band); transition counts
`n_ij` (integer); inter-arrival times `dt_s` (s); polarity run lengths (integer);
within-cluster spread `spread_s` (s).

**Algorithm.**
1. Reuse the existing `events.detector.detect_events` inventory; sort by peak
   time.
2. Build the categorical sequence from `polarity` and `dominant_band`; count
   transitions `n_ij` between consecutive events.
3. Inter-arrival series `dt_k = t_{k+1} - t_k`; group with a declared gap
   threshold for clusters; run lengths of equal polarity.
4. Explicitly report the detector dead time, boundary flags and
   `unqualified_gaps` so that gap intervals are excluded from waiting times and
   are not counted as events.

**Parameters.** cluster gap threshold `0.02 s`; minimum event count `5`;
dead-time handling rule `exclude_intervals`; maximum stored events `4096`.

**Prerequisites and failure conditions.** More than a handful of events; gaps
excluded; cycles inside one record are not independent repeats and this must be
stated in the artifact (no p-values, no CI from cycles alone; independent
estimates require whole independent captures, per the proposals).

**Reason codes.** `insufficient_events`, `dead_time_overlap`,
`single_cycle_record`, `gaps_present`.

**Complexity.** `O(E log E)` sort plus `O(E)` accumulation.

**Analytic validation.**
- Positive: a synthesized sequence with known types and intervals rescales to
  the exact transition counts and `dt` values.
- Control: Poisson random events must produce near-uniform transitions and
  geometric run lengths; the method must not infer deterministic order.
- Limitation: overlapping events inside the detector dead time must reduce
  support and be flagged, not silently counted.

---

## Reference list

- [IEC-4-7] IEC 61000-4-7, harmonics/interharmonics measurement, synchronous
  10/12-cycle rectangular DFT, 200 ms window, 5 Hz resolution, harmonic and
  interharmonic groups/subgroups. Standard text via
  <https://webstore.iec.ch> ; accessible description:
  <https://www.mdpi.com/1996-1073/14/20/6467> and
  <https://www.actionpowertest.com/application-notes/grid-harmonics-measurements-iec-61000-4-7>.
- [HARRIS78] F. J. Harris, "On the use of windows for harmonic analysis with the
  discrete Fourier transform," Proc. IEEE 66(1), 1978.
  <http://www.cs.cmu.edu/afs/cs/user/bhiksha/WWW/courses/dsp/spring2013/WWW/schedule/readings/windows_comparison2_harris.pdf>
- [BEDROSIAN63] E. Bedrosian, "A product theorem for Hilbert transforms,"
  Proc. IEEE 51(5), 1963. <https://ieeexplore.ieee.org/document/1444238>
- [ITOH82] K. Itoh, "Analysis of the phase unwrapping algorithm," Applied
  Optics 21(14), 1982.
  <https://www.semanticscholar.org/paper/Analysis-of-the-phase-unwrapping-algorithm.-Itoh/0612236245850a89c8ba35e3107bad06b9590e4b>
- [BOASHASH92] B. Boashash, "Estimating and interpreting the instantaneous
  frequency of a signal I/II," Proc. IEEE 80(4), 1992.
  <https://ui.adsabs.harvard.edu/abs/1992IEEEP..80..520B>
- [HUASARKAR90] Y. Hua and T. K. Sarkar, "Matrix pencil method for estimating
  parameters of exponentially damped/undamped sinusoids in noise," IEEE Trans.
  ASSP 38(5), 1990.
  <https://www.semanticscholar.org/paper/Matrix-pencil-method-for-estimating-parameters-of-Hua-Sarkar/c5c2351d72fa9914f3266cf271c2cc2c53964e2b>
- [BOGERT63] B. P. Bogert, M. J. R. Healy, J. W. Tukey, "The quefrency alanysis
  of time series for echoes: cepstrum, pseudo-autocovariance, cross-cepstrum and
  saphe cracking," Proc. Symposium on Time Series Analysis, 1963.
  <https://en.wikipedia.org/wiki/Cepstrum>
- [ALLAN87] D. W. Allan, "Time and frequency (time-domain) characterization,
  estimation, and prediction of precision clocks and oscillators," IEEE Trans.
  UFFC 34(6), 1987. <https://tf.nist.gov/general/pdf/868.pdf>
- [IEEE-1139] IEEE Std 1139-2022, definitions of physical quantities for
  fundamental frequency and time metrology - random instabilities.
  <https://antena.fe.uni-lj.si/literatura/Razno/VFtehnika/AndrejLavric/1139-2022.pdf>
- [MARDIA-JUPP] K. V. Mardia and P. E. Jupp, "Directional Statistics," Wiley,
  2000. <https://books.google.it/books?id=PTNiCm4Q-M0C>
- [GARDNER-NAP] W. A. Gardner and A. Napolitano, cyclostationarity theory and
  methods (second-order periodic structure context for families 4-5).
  <https://www.sciencedirect.com/science/article/abs/pii/S0165168405002409>
- [COX-LEWIS] D. R. Cox and P. A. W. Lewis, "The Statistical Analysis of Series
  of Events," Methuen, 1966 (renewal/waiting-time background for family 9).
  <https://link.springer.com/chapter/10.1007/978-3-642-82014-4_6>
- [RIFE74] D. C. Rife and R. R. Boorstyn, "Single-tone parameter estimation from
  discrete-time observations," IEEE Trans. Inf. Theory 20(5), 1974 (baseline for
  single-tone frequency and its high-SNR one-bin resolution).
- [QUINN91] B. G. Quinn and J. M. Fernandes, "A fast efficient technique for the
  estimation of frequency," Biometrika 78(3), 1991.
  <https://researchers.mq.edu.au/en/publications/a-fast-efficient-technique-for-the-estimation-of-frequency>
- [THOMSON82] D. J. Thomson, "Spectrum estimation and harmonic analysis,"
  Proc. IEEE 70(9), 1982 (multitaper option where a single tapered estimate is
  variance-limited).
  <https://en.wikipedia.org/wiki/Multitaper>
- [SCIPY-DECIMATE] scipy.signal.decimate documentation, default order-8
  Chebyshev type-I anti-alias filter, zero-phase by default.
  <https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.decimate.html>
- [SCIPY-CHEBY1] scipy.signal.cheby1 documentation (passband ripple).
  <https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.cheby1.html>
- [SCIPY-9402] SciPy issue 9402, passband attenuation of even-order Chebyshev
  type-I filters in decimate. <https://github.com/scipy/scipy/issues/9402>
- [PROPOSALS] `docs/electrical-signal-characterization-proposals.md`, families
  1-9 and their stated limitations.
