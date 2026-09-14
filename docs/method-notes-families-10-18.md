# Method notes: descriptor families 10-18

Status: implementation contract. This document fixes methods and recipe fields
for future code and tests. It is not evidence that any family is implemented.

Companion to `docs/electrical-signal-characterization-proposals.md` and
`docs/method-notes-families-1-9.md`. The contract uses NumPy and SciPy 1.14,
adds no dependency, and follows ADR-0004, ADR-0007, and ADR-0008.
Shared phase, STFT, band, event, clipping, and resource contracts are fixed in the
[shared computation notes](method-notes-shared-computations.md).

## Conventions shared by all nine families

- CH1 values describe the scope-input plane. CH2 values describe the
  transformer-secondary plane. No result is corrected to the primary side.
- `V^2 s` is the time integral of squared measured voltage. It is not joules or
  energy because current and impedance are not measured.
- JSON numbers are finite. Missing results use `status` and a stable
  `reason_code`, never zero, an empty string, `NaN`, or infinity.
- A single session supplies descriptive estimates and null diagnostics only.
  Cycles, windows, events, bands, and triads from one recording are not
  independent replicates and never produce population confidence intervals.
- Phase comes from CH2 rising zero crossings. Phase-dependent methods are
  unavailable without a qualified CH2 reference.
- Processing is chunked at `262144` samples, never above `1048576`. Working
  memory is capped at `268435456` bytes and each artifact at `67108864` bytes.
  Stored trajectories and events are capped at `4096`. Surrogate counts are at
  most `199`; all pseudo-random paths use recipe seed `6022`.
- Filters use `scipy.signal.butter(..., output="sos")` and
  `scipy.signal.sosfiltfilt`. Analytic signals use `scipy.signal.hilbert`.
  `scipy.signal.envelope` is not used.
- Benjamini-Hochberg uses the declared family-wide list of finite raw p-values,
  stable ascending sort with original-index tie breaking, and `q = 0.05`.

## Family 10: Fixed threshold, duration, and V2s surface

**Quantities and units.** Per channel, phase bin, threshold, and minimum
duration: occupancy ratio; episode count; duration summary in seconds; total
`v2_s`; episode `v2_s` quantiles; and observed support in samples and cycles.

**Algorithm.** Remove the 64-bin phase mean from the measured series. Estimate
scale as `1.4826 * median(abs(r - median(r)))`. For each fixed threshold
`u = threshold_sigma * scale`, find maximal runs where `abs(r) >= u`. Keep a
run for a duration cell when its duration is at least that cell's minimum.
Occupancy is retained samples divided by qualified samples. Episode
`v2_s = sum(r[n]^2) / fs`; total `v2_s` is the sum over retained episodes.
Runs touching a recording edge or an unqualified gap are marked truncated and
excluded from duration and `v2_s` quantiles, but their occupied samples remain
in occupancy with separate truncated support.

**Fixed recipe parameters.** `threshold_sigma = [3, 5, 8, 12]`;
`minimum_duration_s = [0, 0.00002, 0.0001, 0.001, 0.01]`; `phase_bins = 64`;
MAD scale; quantiles `[0.5, 0.9, 0.99]`; maximum `4096` stored episodes.

**Inputs and support/QC.** A finite channel, sample rate, qualified CH2 phase,
and gap mask. Require at least 20 samples in every phase bin, positive MAD, and
two samples at the shortest nonzero duration. Clipped intervals are excluded.

**Reason codes.** `phase_reference_unavailable`, `insufficient_phase_support`,
`scale_zero`, `duration_below_sample_resolution`, `clipped`, `artifact_limit`.

**Bounds.** Four thresholds by five durations, below the limit of 32 for either
axis. One streaming pass per threshold, `O(4N)` time and `O(chunk_samples)`
memory. Only summaries and at most 4096 episodes are stored.

**Analytic tests.** Positive: rectangular pulses with known amplitude and width
give exact occupancy, duration, count, and `V^2 s = A^2 T` on the sample grid.
No effect: phase-independent Gaussian noise gives no systematic phase-cell
difference beyond deterministic sample variation. Limitation: a one-sample
pulse requested at a two-sample minimum is absent from that duration cell, and
a boundary pulse is marked truncated.

**Claim boundary.** The surface describes threshold exceedance at one measured
channel plane. It does not measure energy, damage, source identity, or utility.

## Family 11: Fixed phase-band-mode conditional distributions

**Quantities and units.** Conditional empirical CDF points and quantiles for
absolute peak voltage, event duration in seconds, dominant frequency in hertz,
and event `v2_s`, plus positive/negative polarity counts and integer support for
every phase, band, and F15 mode cell. Event polarity is a reported categorical
quantity, not an interpretable mode.

**Algorithm.** Execute F15 before F11 and use F15's standardization and four
canonical medoids. Assign each event once by peak phase, dominant-frequency
band, and the F15 label of the nonoverlapping 20 ms window containing the event
peak. For a window not retained in the bounded F15 fit, calculate its declared
seven-feature standardized vector and assign the nearest F15 medoid; distance
ties choose the lowest canonical medoid label. Phase bins are left-closed,
right-open. Frequency intervals are also left-closed, right-open except the
last, which includes its upper edge. Sort finite values with stable sample-index
tie breaking. Store the fixed quantiles and a 129-point empirical CDF on the
pooled family-wide value grid from minimum to maximum, plus polarity counts.
Empty and undersupported cells remain explicit.

**Fixed recipe parameters.** `phase_bins = 16`; bands
`[3000,10000)`, `[10000,50000)`, `[50000,200000] Hz`; mode source
`f15_interpretable_modes`; mode rule
`event_peak_window_nearest_canonical_medoid`; mode count `4`; distance-tie rule
`lowest_canonical_mode_label`; quantiles `[0.1,0.25,0.5,0.75,0.9,0.99]`;
linear quantile method; CDF points `129`; minimum support `20`; maximum events
`4096`.

**Inputs and support/QC.** Qualified phase; event peak time, polarity, dominant
frequency, duration, and `v2_s`; and a successful F15 result containing its
feature standardization, canonical medoids, and 20 ms window definition. An
event with an unavailable quantity is excluded only from that quantity and
counted in `n_missing`. An event whose peak-containing window lacks all seven
F15 features is excluded from every F11 cell and counted in `n_mode_missing`.

**Reason codes.** `phase_reference_unavailable`, `insufficient_support`,
`bin_empty`, `dominant_band_unavailable`, `mode_unavailable`,
`mode_assignment_unavailable`, `event_limit`, `gaps_present`.

**Bounds.** One hundred ninety-two cells: 16 phase bins by three bands by four
F15 modes. Sorting costs `O(E log E)` and stored output is bounded by 192 cells
times four continuous quantities times 129 CDF points, plus polarity counts.

**Analytic tests.** Positive: events placed in windows nearest each of four
known F15 medoids recover the corresponding canonical mode cells, exact
support, median, empirical CDF, and polarity counts. No effect: identical value
and polarity multisets copied into all F15 mode strata produce identical
summaries. Limitation: an unavailable F15 result makes F11 unavailable with
`mode_unavailable`; 19 events in a cell return `insufficient_support`, not
extrapolated quantiles.

**Claim boundary.** Differences are conditional descriptions of this session.
An F15 mode is a deterministic grouping of declared measured features, while
polarity remains an event attribute. Neither is a physical source or operating
state. The distributions are not population effects or evidence that phase,
band, mode, or polarity caused an event.

## Family 12: Antoni spectral kurtosis on bounded multiscale STFTs

**Quantities and units.** Spectral kurtosis `SK` and adjusted p-value per scale
and frequency bin, maximum `SK`, selected band in hertz, window support, and
surrogate support. `SK` and p-values are dimensionless.

**Algorithm.** Detrend each channel by its 64-bin phase mean. At each declared
STFT size, use a periodic Hann window and 50 percent overlap. For complex STFT
coefficient `X_m(f)`, calculate Antoni's estimator
`SK(f) = M/(M-1) * ((M+1) * sum|X|^4 / (sum|X|^2)^2 - 2)`. Exclude DC and bins
outside 3 kHz to `min(200 kHz, 0.45 fs)`. Generate each null series by keeping
FFT magnitudes and replacing positive-frequency phases with seeded independent
uniform phases, preserving conjugate symmetry. For each surrogate, record the
maximum `SK` over every searched scale and bin. A candidate raw p-value is
`(1 + count(max_surrogate >= SK_candidate)) / 200`. Apply BH once to all
candidate p-values. The selected band is the contiguous significant run around
the maximum; no undeclared scale or frequency search is allowed.

**Fixed recipe parameters.** STFT segment sizes `[256,1024,4096,16384]`, clipped
to available support; Hann window; overlap `0.5`; detrend `constant`; frequency
band `3000..200000 Hz` with upper Nyquist clamp; phase bins `64`; surrogates
`199`; seed `6022`; `q = 0.05`; minimum STFT frames `32`; maximum stored
significant bins `4096`.

**Inputs and support/QC.** Finite channel, sample rate, qualified phase, and at
least 32 complete frames at a scale. Reject clipped data and zero second moment.

**Reason codes.** `phase_reference_unavailable`, `scale_unsupported`,
`insufficient_frames`, `zero_power`, `no_significant_bin`, `clipped`,
`artifact_limit`.

**Bounds.** Four scales and 199 surrogates. FFT work is
`O((199 + 1) * 4N log Lmax)` and memory is bounded by chunks plus one STFT
scale. Only significant bins up to the cap and scale summaries are stored.

**Analytic tests.** Positive: periodically injected band-limited impulses yield
positive significant SK in the injected band. No effect: stationary Gaussian
noise produces no significant bin for the fixed seeded realization. Limitation:
a record with 31 frames returns `insufficient_frames`; a maximum found only by
an undeclared segment size is not searched.

**Claim boundary.** Significance is a within-session phase-randomized null
diagnostic corrected for the declared maximum search. It is not a confidence
interval, source identification, or proof of nonlinearity.

## Family 13: Phase-residual band-envelope coactivity

**Quantities and units.** Pairwise zero-lag envelope correlation, coincidence
probability and lift, lag of maximum normalized cross-correlation in seconds,
and a lag matrix. Correlation, probability, and lift are dimensionless.

**Algorithm.** Filter the measured channel into nonoverlapping Butterworth
bands, use `hilbert` magnitude as each envelope, then subtract each envelope's
64-bin phase mean. Define activity as residual envelope above `5 * MAD` for its
band. Coincidence is the fraction of qualified samples where both bands are
active. Lift is coincidence divided by the product of marginal activity
fractions. Compute normalized FFT cross-correlation of residual envelopes only
at declared lags, and select the largest absolute correlation with the smallest
absolute lag then negative-before-positive tie breaking. A 1 percent guard band
at each filter edge is excluded from band-power QC.

**Fixed recipe parameters.** Bands `[3000,10000]`, `[10000,50000]`, and
`[50000,200000] Hz`, each upper edge clamped below `0.45 fs`; Butterworth order
4; zero-phase filtering; phase bins `64`; activity threshold `5 MAD`; lag grid
`[-0.02,0.02] s` at sample spacing, capped at 2049 lags; minimum active samples
`20` per band.

**Inputs and support/QC.** Finite channel, sample rate, qualified phase, valid
nonoverlapping bands below Nyquist, and positive envelope MAD. Filter padding
and unqualified gaps are removed from support.

**Reason codes.** `phase_reference_unavailable`, `band_above_nyquist`,
`filter_support_too_short`, `filter_context_unstable`, `nonfinite_input`,
`mixed_unavailable_support`, `scale_zero`, `insufficient_activity`,
`lag_support_too_short`, `leakage_ambiguous`.

**Bounds.** Three bands, three unique pairs, and at most 2049 lags. Filtering
and Hilbert transforms cost `O(BN log N)`; FFT correlation costs
`O(B^2 N log N)`. Output is a fixed 3 by 3 matrix plus summaries.

**Analytic tests.** Positive: two nonoverlapping AM bands with a known 2 ms
envelope delay recover that lag within one sample and lift above one. No effect:
independent seeded envelopes produce lift near one and no stable preferred lag.
Limitation: overlapping requested bands are rejected, and phase-locked but
otherwise independent envelopes become uncorrelated after phase-mean removal.

**Claim boundary.** Coactivity and lag describe association within one measured
channel. They don't establish coupling, direction, source, or causality.

## Family 14: Bidirectional cross-channel event association

**Quantities and units.** CH1 mean waveform and event probability around CH2
events, CH2 mean waveform and event probability around CH1 events, nearest-event
lag distributions in seconds, supports, and null baseline probabilities.

**Algorithm.** Use the fixed event inventories for both synchronous channels.
For each qualified trigger in one channel, extract the other channel in the
declared window after subtracting its 64-bin phase mean. Average samplewise and
calculate the probability that a target-channel event occupies each relative
time bin. Repeat with trigger and target reversed. Match each trigger only to
the nearest target event within the lag window; ties choose the earlier target.
Estimate the no-association baseline by shifting target event times by each of
the 32 fixed whole-cycle offsets modulo qualified complete cycles. Report the
observed curve and baseline range without a population confidence interval.

**Fixed recipe parameters.** Trigger window `-0.02..0.02 s`; `401` relative-time
bins; nearest-event lag `-0.02..0.02 s`; phase bins `64`; cycle shifts
`[1,2,...,32]`; minimum triggers `20`; maximum triggers per direction `4096`.

**Inputs and support/QC.** Synchronously sampled CH1 and CH2, qualified CH2
phase, both event inventories, and complete windows. CH1 remains scope-input;
CH2 remains transformer-secondary. Boundary and gap-crossing triggers are
excluded and counted.

**Reason codes.** `channel_missing`, `channels_not_synchronous`,
`phase_reference_unavailable`, `insufficient_triggers`, `window_truncated`,
`gaps_present`, `event_limit`.

**Bounds.** Two directions, 401 bins, 32 shifts, and 4096 triggers. Direct
indexed accumulation is `O(E * 401 + 32E)` with fixed-size output.

**Analytic tests.** Positive: paired CH1 and CH2 events at a known delay recover
the nearest-event lag and peaks in both conditional directions. No effect:
independent uniform-cycle events match the cycle-shift baseline. Limitation:
events near record edges reduce support and never receive padded zeros.

**Claim boundary.** The output is temporal association only. It doesn't show
which channel led physically, primary-side behavior, causality, or utility.

## Family 15: Deterministic fixed-k medoids of declared features

**Quantities and units.** Real medoid references, standardized feature vectors,
window labels, dwell durations in seconds, transition counts and probabilities,
and block-stability adjusted Rand index. Feature units remain in metadata;
standardized coordinates are dimensionless.

**Algorithm.** Split the record into nonoverlapping 20 ms windows. For each
window calculate RMS voltage, crest factor, 3 to 10 kHz band RMS, 10 to 50 kHz
band RMS, 50 to 200 kHz band RMS, event count, and F10 occupancy at 5 MAD.
Standardize each feature by median and MAD over qualified windows. Features with
zero MAD make the family unavailable. Run PAM k-medoids at fixed `k = 4` using
Euclidean distance, BUILD initialization, deterministic lowest-index ties, and
at most 100 SWAP passes. Canonicalize labels by ascending medoid RMS, then
medoid index. Dwell is each contiguous label run. Transition probabilities are
row-normalized counts. Refit independently in eight contiguous blocks and
match block medoids to full medoids by minimum total distance; report adjusted
Rand index on each block's labels against nearest full medoids.

**Fixed recipe parameters.** Window `0.02 s`; no overlap; the seven listed
features; median/MAD scaling; `k = 4`; PAM BUILD plus SWAP; maximum passes `100`;
stability blocks `8`; minimum windows `80`; maximum stored labels `4096`.

**Inputs and support/QC.** A qualified channel, sample rate, root band limits,
event inventory, and F10 result. Every retained window needs all seven finite
features. If more than 4096 windows exist, choose 4096 evenly spaced indices by
`floor(i * W / 4096)` before fitting and report the sampling rule.

**Reason codes.** `insufficient_windows`, `feature_unavailable`,
`feature_scale_zero`, `empty_cluster`, `stability_block_too_short`,
`label_limit`.

**Bounds.** Fixed `k = 4`, seven features, at most 4096 windows, 100 passes, and
eight block fits. Output stores at most 4096 labels, four medoids, dwell
summaries, and a 4 by 4 transition matrix.

**Analytic tests.** Positive: four separated repeated feature clouds recover
medoids from their generating groups, dwell runs, and exact transition counts.
No effect: a single constant feature vector returns `feature_scale_zero` rather
than four invented modes. Limitation: alternating assignments across stability
blocks produce low block stability and must not be called persistent states.

**Claim boundary.** A mode is a deterministic grouping of declared measured
features. Its label doesn't identify a device, source, operating state, causal
mechanism, or useful condition.

## Family 16: FFT autocorrelation, declared-lag recurrence, and Fano factors

**Quantities and units.** Normalized autocorrelation at declared lags,
recurrence rate at declared lag and radius, count mean and variance, and Fano
factor. Lags and windows are in seconds; all other outputs are dimensionless or
integer support.

**Algorithm.** Remove the 64-bin phase mean. Calculate unbiased linear
autocovariance by zero-padding to the next FFT length at least `2N - 1`, inverse
transforming `FFT(r) * conj(FFT(r))`, and dividing lag `k` by `N-k`; normalize
by lag-zero covariance. At each declared lag, recurrence is the fraction of
pairs where `abs(r[n+k]-r[n]) <= radius_sigma * MAD`. For events, partition the
qualified timeline into nonoverlapping count windows aligned to sample zero;
discard a final partial window. Fano is sample variance with `ddof=1` divided by
mean count.

**Fixed recipe parameters.** phase bins `64`; lags
`[0.0001,0.001,0.01,0.02,0.1,0.5] s`; recurrence radii `[0.5,1,2] MAD`; count
windows `[0.02,0.1,0.5,1] s`; minimum pairs `100`; minimum complete count
windows `10`; maximum FFT input `1048576` samples per analyzed segment.

**Inputs and support/QC.** Finite channel, sample rate, qualified phase, positive
MAD, and event peak times. Gaps split segments; pair and count windows never
cross gaps.

**Reason codes.** `phase_reference_unavailable`, `scale_zero`,
`lag_above_support`, `insufficient_pairs`, `insufficient_count_windows`,
`zero_event_rate`, `gaps_present`.

**Bounds.** Six lags, three radii, and four count windows. Segment FFTs cost
`O(N log N)` and direct declared-lag recurrence costs `O(18N)`. Output is fixed.

**Analytic tests.** Positive: an AR(1) series has autocorrelation `rho^k` at the
sample lags within a fixed analytic tolerance; a seeded clustered event process
has Fano above one at its cluster scale. No effect: seeded Poisson counts have
Fano near one and white noise has near-zero nonzero-lag autocorrelation.
Limitation: a requested lag leaving fewer than 100 pairs is unavailable.

**Claim boundary.** These finite-record summaries cover only declared lags and
windows. They don't prove long memory, stationarity, a physical mechanism, or
population behavior.

## Family 17: Declared cyclic spectral coherence

**Quantities and units.** Complex cyclic spectrum, magnitude-squared cyclic
coherence, raw and BH-adjusted p-values, frequency in hertz, cyclic frequency
in hertz, and segment support. Coherence and p-values are dimensionless.

**Algorithm.** Remove the 64-bin phase mean. Form Hann-windowed, 50 percent
overlapped STFT frames. For cyclic frequency `alpha`, map only bins where
`f-alpha/2` and `f+alpha/2` lie exactly on the FFT grid and calculate
`S_alpha(f) = mean(X(f+alpha/2) * conj(X(f-alpha/2)))`. Normalize as
`gamma2 = |S_alpha|^2 / (S0(f+alpha/2) * S0(f-alpha/2))`. Generate 199 nulls by
permuting complete mains cycles with seeded Fisher-Yates permutations, keeping
samples within each cycle intact, then repeat phase-mean removal and estimation.
Raw p-values use `(1 + count(null_gamma2 >= observed)) / 200`; BH covers every
tested alpha-frequency cell once.

**Fixed recipe parameters.** cyclic frequencies `[50,100,150,200] Hz`;
STFT segment samples `4096`; Hann window; overlap `0.5`; phase bins `64`;
analysis band `3000..200000 Hz` with Nyquist clamp; surrogates `199`; seed
`6022`; `q = 0.05`; minimum complete cycles `40`; maximum stored significant
cells `4096`.

**Inputs and support/QC.** Finite channel, sample rate, qualified CH2 phase,
complete cycle boundaries, and at least 32 STFT frames. Frequencies that do not
map to exact symmetric bins are unavailable rather than interpolated.

**Reason codes.** `phase_reference_unavailable`, `insufficient_cycles`,
`insufficient_frames`, `cyclic_frequency_off_grid`, `zero_denominator`,
`no_significant_cell`, `artifact_limit`.

**Bounds.** Four cyclic frequencies, one STFT scale, 199 cycle permutations,
and at most 4096 stored cells. Work is `O(200N log 4096)` with one surrogate in
memory at a time.

**Analytic tests.** Positive: a carrier with known 50 Hz amplitude modulation
has cyclic coherence at `alpha = 50 Hz` and its analytic sideband midpoint.
No effect: stationary seeded Gaussian noise has no BH-significant cell in the
fixed realization. Limitation: fewer than 40 complete cycles returns
`insufficient_cycles`; an off-grid alpha is not rounded.

**Claim boundary.** P-values are cycle-permutation null diagnostics for this
record, not independent-replicate confidence intervals. Cyclic coherence does
not prove source, nonlinearity, causality, or practical utility.

## Family 18: Declared normalized bicoherence triads

**Quantities and units.** Squared normalized bicoherence, biphase in radians,
raw and BH-adjusted p-values, triad frequencies in hertz, and frame support.

**Algorithm.** Remove the 64-bin phase mean and split into Hann-windowed,
50 percent overlapped frames. For each declared on-grid pair `(f1,f2)` with
`f1 <= f2` and `f1+f2` below the analysis upper bound, calculate
`B = sum X_m(f1) X_m(f2) conj(X_m(f1+f2))` and
`b2 = |B|^2 / (sum |X_m(f1)X_m(f2)|^2 * sum |X_m(f1+f2)|^2)`.
Generate two seeded null ensembles of 99 each. The phase-randomized ensemble
keeps the record FFT magnitudes and randomizes phases. The IAAFT ensemble starts
from a seeded permutation and alternates exact rank remapping to the observed
amplitudes with replacement of Fourier magnitudes by observed magnitudes for
100 iterations. IAAFT convergence means relative RMS Fourier-magnitude error
at most `1e-6`; otherwise the surrogate is excluded and
`iaaft_not_converged` is reported. A triad raw p-value uses the larger of the
two add-one p-values, each divided by 100. Apply BH once across all declared
triads. Store biphase only when `b2` is significant and its bispectrum magnitude
is nonzero.

**Fixed recipe parameters.** STFT segment samples `4096`; Hann window; overlap
`0.5`; phase bins `64`; base frequencies `[3000,5000,10000,20000,50000] Hz`;
triads are every valid unordered pair from that list, capped at `4096`; analysis
upper bound `200000 Hz` with Nyquist clamp; phase-randomized surrogates `99`;
IAAFT surrogates `99`; IAAFT iterations `100`; seed `6022`; `q = 0.05`;
IAAFT relative RMS Fourier-magnitude tolerance `1e-6`; minimum frames `32`.

**Inputs and support/QC.** Finite channel, sample rate, qualified phase, exact
FFT-bin triads, nonzero denominator, and at least 32 frames. Frequency pairs are
fixed before data inspection.

**Reason codes.** `phase_reference_unavailable`, `insufficient_frames`,
`triad_off_grid`, `triad_above_nyquist`, `zero_denominator`,
`iaaft_not_converged`, `no_significant_triad`, `artifact_limit`.

**Bounds.** At most 15 triads for the fixed base grid, below the hard cap of
4096, with 198 surrogates and 100 bounded IAAFT iterations. Work is
`O(198 * (N log N + 100N log N))`; one surrogate and its STFT are held at once.

**Analytic tests.** Positive: `x = cos(2pi f1 t) + cos(2pi f2 t) +
0.5 cos(2pi(f1+f2)t + phi)` with locked phases produces significant
bicoherence and biphase `-phi` under the stated Fourier convention. No effect:
independent random phases per frame remove significant bicoherence in the fixed
seeded realization. Limitation: an impulsive amplitude distribution that fools
phase-only surrogates must fail against the conservative IAAFT p-value or remain
explicitly nonsignificant.

**Claim boundary.** Significant bicoherence is a within-session phase-coupling
diagnostic under both declared nulls. It doesn't prove physical nonlinearity,
source identity, causality, primary-side behavior, or practical utility.

## Primary references

- [ANTONI-2006] J. Antoni, "The spectral kurtosis: a useful tool for
  characterising non-stationary signals," Mechanical Systems and Signal
  Processing 20(2), 2006. <https://doi.org/10.1016/j.ymssp.2004.09.001>
- [BENJAMINI-HOCHBERG] Y. Benjamini and Y. Hochberg, "Controlling the false
  discovery rate," Journal of the Royal Statistical Society B 57(1), 1995.
  <https://www.jstor.org/stable/2346101>
- [COHEN-1995] L. Cohen, "Time-Frequency Analysis," Prentice Hall, 1995,
  analytic signals, ambiguity, and bilinear spectral methods.
- [KAUFMAN-ROUSSEEUW] L. Kaufman and P. J. Rousseeuw, "Finding Groups in Data,"
  Wiley, 1990, Partitioning Around Medoids.
- [COX-LEWIS] D. R. Cox and P. A. W. Lewis, "The Statistical Analysis of Series
  of Events," Methuen, 1966.
- [GARDNER-1991] W. A. Gardner, "Exploitation of spectral redundancy in
  cyclostationary signals," IEEE Signal Processing Magazine 8(2), 1991.
  <https://doi.org/10.1109/79.81007>
- [SCHREIBER-SCHMITZ] T. Schreiber and A. Schmitz, "Surrogate time series,"
  Physica D 142, 2000. <https://doi.org/10.1016/S0167-2789(00)00043-9>
- [POLOSKEI-2019] P. Poloskei et al., "Bicoherence analysis of nonstationary and
  nonlinear processes," EPL 126, 2019. <https://arxiv.org/abs/1811.02973>
