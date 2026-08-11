from __future__ import annotations

import numpy as np

from lnt.spectrum import find_qualified_peaks


def test_corrected_peaks_do_not_bridge_unqualified_gap_and_leave_q_unknown() -> None:
    # Given: two narrow qualified regions whose half-power crossings lie outside each region.
    frequencies_hz = np.arange(7, dtype=np.float64)
    corrected_psd = np.array([0.6, 1.0, 0.6, np.nan, 0.6, 1.0, 0.6])
    qualified = np.array([True, True, True, False, True, True, True])

    # When: corrected peaks are derived from contiguous qualified regions only.
    peaks = find_qualified_peaks(
        frequencies_hz,
        corrected_psd,
        qualified,
        min_prominence_db=1.0,
    )

    # Then: each region produces its own unresolved-Q peak rather than an interpolated bridge.
    assert [peak.frequency_hz for peak in peaks] == [1.0, 5.0]
    assert all(peak.q_factor is None for peak in peaks)


def test_corrected_peaks_exclude_flat_and_too_short_qualified_regions() -> None:
    # Given: flat, single-bin, and two-bin qualified regions without a 6 dB local prominence.
    frequencies_hz = np.arange(8, dtype=np.float64)
    corrected_psd = np.array([0.8, 0.8, 0.8, np.nan, 1.0, np.nan, 0.6, 0.6])
    qualified = np.array([True, True, True, False, True, False, True, True])

    # When: corrected peak extraction applies the production prominence threshold per region.
    peaks = find_qualified_peaks(frequencies_hz, corrected_psd, qualified)

    # Then: no qualified region becomes a peak merely by having a maximum value.
    assert peaks == ()
