"""Очередь C3: truth-тесты калибровок и единиц (TDD RED→GREEN)."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

import numpy as np
import pytest

if TYPE_CHECKING:
    from pathlib import Path

from lnt.adc_calibration import (
    AdcCalibration,
    apply_adc_calibration,
    try_load_adc_calibration,
)
from lnt.input_reference import correction_for_frequencies
from lnt.swept_response import (
    TransformerDeembed,
    apply_transformer_deembed,
    load_swept_response_csv,
    swept_gain_at,
)
from lnt.types import (
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
)
from lnt.units import (
    DISPLAY_UNITS,
    dbm_per_hz_50r,
    dbuv_per_hz,
    dbv_per_hz,
    shift_level_db,
)


def _rc_model() -> FloatingDifferentialRcShunt:
    return FloatingDifferentialRcShunt(
        resistance_ohm=100.0,
        c1_f=10e-9,
        c2_f=10e-9,
        component_values_basis=ComponentValuesBasis.NOMINAL,
        reference_assumption=ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
    )


def _legacy_volts(raw: np.ndarray, range_code: int) -> np.ndarray:
    """Независимая истина: формула драйвера ((raw − 128) × 5.12/(код × 128))."""
    scale = 5.12 / float(range_code << 7)
    return ((raw.astype(np.float32) - 128.0) * scale).astype(np.float32)


def test_uncalibrated_path_bit_identical() -> None:
    """Без таблицы калибровка — тождество: вольты равны legacy-формуле."""
    raw = np.array([0, 64, 128, 192, 255], dtype=np.uint8)
    identity = AdcCalibration(offset_lsb=0.0, gain=1.0)
    np.testing.assert_array_equal(
        apply_adc_calibration(raw, range_code=1, calibration=identity),
        _legacy_volts(raw, 1),
    )
    np.testing.assert_array_equal(
        apply_adc_calibration(raw, range_code=1, calibration=None),
        _legacy_volts(raw, 1),
    )


def test_adc_calibration_applies_documented_correction() -> None:
    """Поправка: (raw − center − offset) × scale × gain; provenance — флагом."""
    raw = np.array([128, 138], dtype=np.uint8)
    calibration = AdcCalibration(offset_lsb=10.0, gain=1.02)
    corrected = apply_adc_calibration(raw, range_code=1, calibration=calibration)
    scale = 5.12 / float(1 << 7)
    assert corrected[0] == pytest.approx((0.0 - 10.0) * scale * 1.02)
    assert corrected[1] == pytest.approx((10.0 - 10.0) * scale * 1.02)
    assert calibration.is_effective


def test_adc_table_load_round_trip_and_absent_is_none(tmp_path: Path) -> None:
    """Per-device JSON из config dir грузится; отсутствие файла — None (не fabricate)."""
    assert try_load_adc_calibration(tmp_path, device_serial=None) is None
    payload = {"offset_lsb": 2.5, "gain": 0.998, "device_serial": "HNT-001"}
    table = tmp_path / "adc_calibration_hnt-001.json"
    table.write_text(json.dumps(payload), encoding="utf-8")
    loaded = try_load_adc_calibration(tmp_path, device_serial="HNT-001")
    assert loaded is not None
    assert (loaded.offset_lsb, loaded.gain, loaded.device_serial) == (2.5, 0.998, "HNT-001")


def test_nominal_single_pole_default_unchanged() -> None:
    """Дефолт без swept — та же однополюсная формула (бит-идентичность)."""
    model = _rc_model()
    frequencies = np.array([1e3, 1e4, 1e5, 1e6])
    gains = correction_for_frequencies(model, frequencies)
    c_eq = (10e-9 * 10e-9) / (20e-9)
    for frequency, gain in zip(frequencies, gains, strict=True):
        numerator = 2.0 * math.pi * float(frequency) * 100.0 * c_eq
        assert float(gain) == pytest.approx(numerator / math.sqrt(1.0 + numerator**2))


def test_swept_rc_round_trip_zero_db_excess(tmp_path: Path) -> None:
    """Измеренная swept-FR, снятая с номинала: excess после коррекции — 0 дБ."""
    model = _rc_model()
    frequencies = np.logspace(math.log10(3e3), math.log10(3e6), num=32)
    nominal = correction_for_frequencies(model, frequencies)
    csv_path = tmp_path / "swept_fr.csv"
    csv_path.write_text(
        "frequency_hz,gain\n"
        + "\n".join(f"{f:.6f},{g:.12f}" for f, g in zip(frequencies, nominal, strict=True)),
        encoding="utf-8",
    )
    swept = load_swept_response_csv(csv_path)
    overridden = correction_for_frequencies(model, frequencies, swept=swept)
    np.testing.assert_allclose(overridden, nominal, rtol=1e-9)
    # Сквозной round-trip: scope PSD = вход × |H|² → вход восстанавливается ровно.
    input_psd = np.full_like(frequencies, 2.5e-9)
    scope_psd = input_psd * overridden**2
    recovered = scope_psd / swept_gain_at(swept, frequencies) ** 2
    excess_db = 10.0 * np.log10(recovered / input_psd)
    np.testing.assert_allclose(excess_db, np.zeros_like(excess_db), atol=1e-9)


def test_swept_out_of_range_is_nan_never_fabricated(tmp_path: Path) -> None:
    """Вне измеренного диапазона — NaN (unavailable), не экстраполяция."""
    csv_path = tmp_path / "swept_fr.csv"
    csv_path.write_text("frequency_hz,gain\n1000,0.5\n2000,0.7\n", encoding="utf-8")
    swept = load_swept_response_csv(csv_path)
    gains = swept_gain_at(swept, np.array([500.0, 1000.0, 4000.0]))
    assert math.isnan(float(gains[0]))
    assert float(gains[1]) == pytest.approx(0.5)
    assert math.isnan(float(gains[2]))


def test_transformer_deembed_hook_default_off() -> None:
    """Hook де-эмбеддинга 230:6 по умолчанию выключен (бит-идентичность)."""
    psd = np.array([1e-6, 2e-6])
    frequencies = np.array([50.0, 150.0])
    np.testing.assert_array_equal(
        apply_transformer_deembed(psd, frequencies, hook=TransformerDeembed()),
        psd,
    )
    assert not TransformerDeembed().enabled
    on = apply_transformer_deembed(
        psd,
        frequencies,
        hook=TransformerDeembed(enabled=True, primary_v=230.0, secondary_v=6.0),
    )
    np.testing.assert_allclose(on, psd * (230.0 / 6.0) ** 2)


def test_display_unit_conversions() -> None:
    """dBV/dBuV/dBm(50Ω) — display-only; хранимый формат не меняется."""
    psd = 1.0  # 1 В²/Гц — опорный уровень
    assert dbv_per_hz(psd) == pytest.approx(0.0)
    assert dbuv_per_hz(psd) == pytest.approx(120.0)
    assert dbm_per_hz_50r(psd) == pytest.approx(10.0 * math.log10(20.0))
    assert shift_level_db(-30.0, "dbuv") == pytest.approx(90.0)
    assert shift_level_db(-30.0, "dbm_50r") == pytest.approx(-30.0 + 10.0 * math.log10(20.0))
    assert shift_level_db(5.0, "dbv") == pytest.approx(5.0)
    assert set(DISPLAY_UNITS) == {"dbv", "dbuv", "dbm_50r"}
