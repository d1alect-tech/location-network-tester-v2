import numpy as np
import pytest
from scipy import signal

from lnt.errors import InputError
from lnt.signals import PROFILES, SyntheticSession, generate

FS = 500_000.0
DURATION = 1.0


def make_session(profile: str, seed: int = 6022) -> SyntheticSession:
    return generate(
        profile=profile,
        duration_s=DURATION,
        sample_rate_hz=FS,
        rng=np.random.default_rng(seed),
    )


def welch_psd(x: np.ndarray, nperseg: int) -> tuple[np.ndarray, np.ndarray]:
    freqs, psd = signal.welch(x.astype(np.float64), fs=FS, nperseg=nperseg)
    return np.asarray(freqs), np.asarray(psd)


class TestProfiles:
    def test_contract_profiles_present(self) -> None:
        assert {"bad", "bad-damped", "quiet"} <= set(PROFILES)

    def test_unknown_profile_rejected(self) -> None:
        with pytest.raises(InputError, match="profile"):
            generate(
                profile="telepathy",
                duration_s=DURATION,
                sample_rate_hz=FS,
                rng=np.random.default_rng(0),
            )

    def test_non_positive_duration_rejected(self) -> None:
        with pytest.raises(InputError, match="отсчёт"):
            generate(
                profile="bad",
                duration_s=0.0,
                sample_rate_hz=FS,
                rng=np.random.default_rng(0),
            )


class TestShapes:
    def test_shapes_dtype_truth(self) -> None:
        ses = make_session("bad")
        n = round(FS * DURATION)
        assert ses.profile == "bad"
        assert ses.truth == PROFILES["bad"]
        assert ses.ch1.shape == (n,)
        assert ses.ch2.shape == (n,)
        assert ses.ch1.dtype == np.float32
        assert ses.ch2.dtype == np.float32
        assert bool(np.isfinite(ses.ch1).all())
        assert bool(np.isfinite(ses.ch2).all())

    def test_deterministic_for_same_seed(self) -> None:
        first = make_session("bad")
        second = make_session("bad")
        np.testing.assert_array_equal(first.ch1, second.ch1)
        np.testing.assert_array_equal(first.ch2, second.ch2)


class TestCh2Mains:
    def test_dominant_frequency_is_line(self) -> None:
        ses = make_session("bad")
        freqs, psd = welch_psd(np.asarray(ses.ch2), nperseg=1 << 17)
        dominant = float(freqs[int(np.argmax(psd))])
        assert abs(dominant - 50.0) < 5.0

    def test_rms_plausible_for_transformer_secondary(self) -> None:
        ses = make_session("bad")
        rms = float(np.sqrt(np.mean(np.square(np.asarray(ses.ch2, dtype=np.float64)))))
        assert 1.0 < rms < 4.0


class TestCh1Needles:
    def test_psd_peak_near_ring_f0(self) -> None:
        ses = make_session("bad")
        freqs, psd = welch_psd(np.asarray(ses.ch1), nperseg=32_768)
        band = (freqs > 5_000.0) & (freqs < 100_000.0)
        peak_freq = float(freqs[band][int(np.argmax(psd[band]))])
        assert abs(peak_freq - ses.truth.ring_f0_hz) < 1_000.0

    def test_ch1_is_impulsive(self) -> None:
        ses = make_session("bad")
        x = np.asarray(ses.ch1, dtype=np.float64)
        x -= x.mean()
        kurtosis = float(np.mean(x**4) / np.mean(x**2) ** 2)
        assert kurtosis > 10.0


class TestDampedProfile:
    def test_damped_peak_lower_by_about_12db(self) -> None:
        bad = make_session("bad")
        damped = make_session("bad-damped")
        freqs, psd_bad = welch_psd(np.asarray(bad.ch1), nperseg=32_768)
        _, psd_damped = welch_psd(np.asarray(damped.ch1), nperseg=32_768)
        band = (freqs > 15_000.0) & (freqs < 30_000.0)
        peak_idx = int(np.argmax(psd_bad[band]))
        delta_db = float(10.0 * np.log10(psd_damped[band][peak_idx] / psd_bad[band][peak_idx]))
        assert -14.0 < delta_db < -10.0
