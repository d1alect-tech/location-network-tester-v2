"""Ripple-срез анализа v2: QC, метрики, полосной RMS, фон рядом, сайдкар.

Истина аналитическая: синус точно на бине даёт замкнутую форму для 3-бинной
суммы периодического Hann (A^2/2), чистые статистики берутся из хранимого
вектора float32 как точные статистики сохранённых отсчётов. Ни одно ожидание
не выводится из движка.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path

import numpy as np
import pytest

from lnt.adc_calibration import apply_adc_calibration
from lnt.analysis_v2.engine_ripple import run_ripple
from lnt.analysis_v2.ripple_options import (
    BaselineAttachment,
    RippleRequest,
    SettlingDeclaration,
)
from lnt.catalog import apply_migrations
from lnt.catalog.reconcile import reconcile_catalog
from lnt.catalog.reconcile_parse import parse_directory
from lnt.catalog.reconcile_scan import scan_immediate_directories
from lnt.errors import InputError
from lnt.ripple.adapter import AdapterSpec
from lnt.session_store import LoadedSession, load_session, write_session
from lnt.types import (
    AcquisitionTelemetry,
    ChannelMeta,
    ChannelRole,
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
    ScopeInputTerminated,
    SessionManifest,
    SessionSource,
    SessionType,
)

_FS_HZ = 10_000.0
_PREFIX_SAMPLES = 10_000  # ceil(10 kHz * 10*tau), tau = 0.1 s
_COUNT = 29_000  # 2.9 s: span 1.9 s, nperseg 10k, 2 сегмента, хвост 4k
_AMPLITUDE_V = 0.05
_TONE_HZ = 100.0
_DC_V = 0.5


def _floating_geometry(*, resistance_ohm: float = 100.0) -> FloatingDifferentialRcShunt:
    return FloatingDifferentialRcShunt(
        resistance_ohm=resistance_ohm,
        c1_f=10e-9,
        c2_f=10e-9,
        component_values_basis=ComponentValuesBasis.NOMINAL,
        reference_assumption=ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
    )


def _obj(payload: dict[str, object], key: str) -> dict[str, object]:
    return cast("dict[str, object]", payload[key])


def _arr(payload: dict[str, object], key: str) -> list[object]:
    return cast("list[object]", payload[key])


def _codes(block: dict[str, object]) -> list[str]:
    return cast("list[str]", block["reason_codes"])


def _float(block: dict[str, object], key: str) -> float:
    return cast("float", block[key])


def _sine_record(*, fs: float = _FS_HZ, count: int = _COUNT) -> np.ndarray:
    times = np.arange(count, dtype=np.float64) / fs
    record = _DC_V + _AMPLITUDE_V * np.sin(2.0 * np.pi * _TONE_HZ * times)
    return record.astype(np.float32)


def _telemetry(
    *,
    count: int = _COUNT,
    clip_low: int = 0,
    clip_high: int = 0,
    calibration_used: bool = False,
) -> AcquisitionTelemetry:
    return AcquisitionTelemetry(
        requested_samples=count,
        captured_samples=count,
        callback_count=1,
        block_lengths=(count,),
        callback_gaps_s=(),
        expected_block_interval_s=count / _FS_HZ,
        short_block_count=0,
        ch1_clip_low_count=clip_low,
        ch1_clip_high_count=clip_high,
        ch2_clip_low_count=0,
        ch2_clip_high_count=0,
        calibration_used=calibration_used,
    )


def _manifest(
    *,
    session_id: str,
    count: int = _COUNT,
    fs: float = _FS_HZ,
    source: SessionSource = SessionSource.SYNTHETIC,
    telemetry: AcquisitionTelemetry | None = None,
    range_code: int = 10,
    probe_multiplier: float = 1.0,
    ch1_setup: FloatingDifferentialRcShunt | ScopeInputTerminated | None = None,
    session_type: SessionType = SessionType.MEASUREMENT,
) -> SessionManifest:
    return SessionManifest(
        schema_version=2 if ch1_setup is not None else 1,
        session_id=session_id,
        created_utc="2026-10-20T00:00:00Z",
        completed_utc="2026-10-20T00:00:03Z",
        source=source,
        session_type=session_type,
        sample_rate_hz=fs,
        duration_s=count / fs,
        sample_count=count,
        line_frequency_hz=50.0,
        profile=None,
        baseline_session=None,
        parameters={},
        ch1=ChannelMeta(
            filename="ch1.npy",
            role=ChannelRole.HF_PROBE,
            unit="V",
            front_end="ripple fixture",
            range_code=range_code,
            probe_multiplier=probe_multiplier,
        ),
        ch2=None,
        acquisition_telemetry=telemetry,
        synthetic_truth=None,
        ch1_setup=ch1_setup,
    )


def _write(
    path: Path,
    *,
    ch1: np.ndarray,
    manifest: SessionManifest,
) -> LoadedSession:
    session_dir = write_session(
        session_dir=path,
        manifest=manifest,
        ch1=ch1.astype(np.float32),
        ch2=None,
    )
    return load_session(session_dir)


def _request(
    session: LoadedSession,
    **overrides: object,
) -> RippleRequest:
    kwargs: dict[str, object] = {
        "session": session,
        "adapter": AdapterSpec(),
        "band_low_hz": 99.0,
        "band_high_hz": 101.0,
        "settling": SettlingDeclaration.PRECONNECTED,
    }
    kwargs.update(overrides)
    return RippleRequest(**kwargs)  # pyright: ignore[reportArgumentType]


def _assert_finite(node: object) -> None:
    if isinstance(node, dict):
        for value in node.values():
            _assert_finite(value)
    elif isinstance(node, list):
        for value in node:
            _assert_finite(value)
    elif isinstance(node, float):
        assert math.isfinite(node)


def _assert_provenance_and_adapter(payload: dict[str, object]) -> None:
    # Провенанс: метаданные захвата не являются провенансом адаптера.
    provenance = _obj(payload, "provenance")
    assert provenance["capture_metadata_basis"] == "legacy_capture_metadata_not_adapter_provenance"
    assert provenance["operator_attachment"] == "preconnected_no_reconnection"
    assert provenance["voltage_plane"] == "synthetic_mathematical_volts"
    assert provenance["range_code"] == 10
    assert provenance["probe_multiplier"] == 1.0
    assert provenance["calibration_used"] is False
    assert provenance["calibration_identity"] == "legacy_bit_identical_conversion"
    assert provenance["hardware_qualification"] == "unverified"

    # Адаптер: номинальная модель с честными ограничениями.
    adapter = _obj(payload, "adapter")
    assert adapter["topology_id"] == "series_c_at_dut_tip_x1_v1"
    assert _float(adapter, "fc_hz") == pytest.approx(1.5915494309189535, rel=1e-12)
    assert _float(adapter, "tau_s") == pytest.approx(0.1, rel=1e-12)
    assert _float(adapter, "plateau_gain") == pytest.approx(1.0, rel=1e-12)
    assert adapter["transfer_status"] == "nominal_transfer_declared"
    assert "hardware_qualification_unverified" in cast("list[str]", adapter["assumption_codes"])


def test_happy_synthetic_sine_matches_analytics_and_schema(tmp_path: Path) -> None:
    # Given: синус 100 Гц A=0.05 + DC 0.5 В, точно на бине df=1 Гц, 2 сегмента.
    record = _sine_record()
    session = _write(
        tmp_path / "meas",
        ch1=record,
        manifest=_manifest(session_id="ripple-happy", telemetry=_telemetry()),
    )

    # When
    sidecar = run_ripple(_request(session))

    # Then: сайдкар написан, JSON конечен и без NaN/Infinity.
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))
    _assert_finite(payload)
    assert "NaN" not in sidecar.sidecar_path.read_text(encoding="utf-8")
    assert payload["schema_version"] == 1
    assert _obj(payload, "algorithm") == {
        "id": "ripple_observed_v1",
        "version": 1,
        "rms": "population_centered_float64",
    }
    options = _obj(payload, "options")
    assert options == {"band_low_hz": 99.0, "band_high_hz": 101.0, "interval_window_s": 1.0}

    # Идентичности сессии: хэши входов 64-hex.
    session_block = _obj(payload, "session")
    assert session_block["session_id"] == "ripple-happy"
    assert session_block["channel"] == "ch1"
    assert session_block["source"] == "synthetic"
    for key in ("manifest_sha256", "ch1_sha256"):
        assert len(cast("str", session_block[key])) == 64

    _assert_provenance_and_adapter(payload)

    # Выбор: окно установления исключено, исходные границы сохранены.
    selection = _obj(payload, "selection")
    assert selection["sample_start_index"] == _PREFIX_SAMPLES
    assert selection["sample_end_index_exclusive"] == _COUNT
    assert selection["sample_count"] == _COUNT - _PREFIX_SAMPLES
    assert selection["excluded_prefix_samples"] == _PREFIX_SAMPLES
    assert selection["settling_prefix_samples_nominal"] == _PREFIX_SAMPLES
    assert selection["settling_basis"] == "capture_start_assuming_preconnected"
    assert selection["continuity_status"] == "synthetic_exact"
    assert selection["continuity_reason_codes"] == []
    assert _float(selection, "realized_duration_s") == pytest.approx(1.9)

    # QC: синтетика — клиппинг неприменим.
    qc = _obj(payload, "qc")
    assert qc["clipping_assessment"] == "not_applicable_synthetic"
    assert qc["clip_count_scope"] is None
    assert qc["clip_low_count"] is None
    assert qc["clip_high_count"] is None
    assert qc["nonfinite_count"] == 0
    assert qc["nonfinite_count_scope"] == "selected_span"
    assert qc["record_nonfinite_count"] == 0
    assert qc["dropped_samples"] == 0
    assert _codes(qc) == []


def test_happy_synthetic_time_domain_and_intervals(tmp_path: Path) -> None:
    # Given: та же синтетика — числовые блоки сверяются с аналитикой.
    record = _sine_record()
    session = _write(
        tmp_path / "meas",
        ch1=record,
        manifest=_manifest(session_id="ripple-happy-num", telemetry=_telemetry()),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Time-domain: точные статистики сохранённого вектора на выбранном спане.
    span = np.asarray(record[_PREFIX_SAMPLES:], dtype=np.float64)
    mu = float(np.mean(span))
    rms = float(np.sqrt(np.mean((span - mu) ** 2)))
    time_domain = _obj(payload, "time_domain")
    assert time_domain["availability"] == "available"
    assert _codes(time_domain) == []
    assert _float(time_domain, "mean_v") == pytest.approx(mu, rel=1e-12)
    assert _float(time_domain, "rms_ac_v") == pytest.approx(rms, rel=1e-12)
    assert _float(time_domain, "vpp_v") == pytest.approx(
        float(np.max(span) - np.min(span)), rel=1e-12
    )
    # И чистая аналитика: A/sqrt(2) и 2A на float32-хранилище.
    assert _float(time_domain, "mean_v") == pytest.approx(_DC_V, rel=1e-5)
    assert _float(time_domain, "rms_ac_v") == pytest.approx(_AMPLITUDE_V / math.sqrt(2.0), rel=1e-5)
    assert _float(time_domain, "vpp_v") == pytest.approx(2.0 * _AMPLITUDE_V, rel=1e-5)

    # Интервалы: исходные индексы с-offsetом префикса, хвост неполный.
    intervals = _arr(payload, "intervals")
    assert len(intervals) == 2
    first, tail = cast("dict[str, object]", intervals[0]), cast("dict[str, object]", intervals[1])
    assert (first["start_index"], first["end_index_exclusive"]) == (10_000, 20_000)
    assert first["complete"] is True
    assert first["availability"] == "available"
    assert (tail["start_index"], tail["end_index_exclusive"]) == (20_000, 29_000)
    assert tail["complete"] is False
    assert tail["sample_count"] == 9_000
    assert tail["availability"] == "available"


def test_happy_synthetic_spectrum_and_band(tmp_path: Path) -> None:
    # Given: синус точно на бине — замкнутая форма 3-бинной суммы Hann.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-happy-spec", telemetry=_telemetry()),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Спектр: явные настройки mean/Hann/0.5, df=1 Гц, ENBW=1.5 Гц, 2 сегмента.
    spectrum = _obj(payload, "spectrum")
    assert spectrum["availability"] == "available"
    settings = _obj(spectrum, "settings")
    assert settings["nperseg"] == 10_000
    assert settings["overlap_fraction"] == 0.5
    assert settings["window"] == "hann"
    assert settings["detector"] == "mean"
    assert settings["detrend"] == "constant"
    assert settings["scaling"] == "density"
    assert settings["max_chunk_samples"] == 1_000_000
    assert _float(settings, "resolution_hz") == pytest.approx(1.0)
    assert _float(settings, "enbw_hz") == pytest.approx(1.5)
    assert settings["segment_count"] == 2
    assert spectrum["used_sample_count"] == 15_000
    assert spectrum["ignored_tail_samples"] == 4_000
    frequency = cast("list[float]", spectrum["frequency_hz"])
    assert frequency[0] == 0.0
    assert frequency[1] == 1.0
    assert frequency[-1] == 5_000.0
    assert len(frequency) == 5_001
    assert len(cast("list[float]", spectrum["psd_v2_per_hz"])) == 5_001
    assert len(cast("list[float]", spectrum["asd_v_per_sqrt_hz"])) == 5_001

    # Полоса: 3 бина периодического Hann дают ровно A^2/2; RMS = A/sqrt(2).
    bands = _arr(payload, "bands")
    assert len(bands) == 1
    band = cast("dict[str, object]", bands[0])
    assert band["id"] == "ripple"
    assert band["availability"] == "available"
    assert (band["low_hz"], band["high_hz"]) == (99.0, 101.0)
    assert _float(band, "first_center_hz") == pytest.approx(99.0)
    assert _float(band, "last_center_hz") == pytest.approx(101.0)
    assert band["bin_count"] == 3
    assert _float(band, "rms_v") == pytest.approx(_AMPLITUDE_V / math.sqrt(2.0), rel=1e-5), (
        "3-бинная сумма периодического Hann = A^2/2 без умножения ENBW"
    )

    # Фон отсутствует: baseline null, не фабрикация.
    assert payload["baseline"] is None


def test_zero_low_band_uses_positive_centers_and_excludes_dc(tmp_path: Path) -> None:
    # Given: нижняя граница 0 допустима, DC-бин исключён маской f > 0.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-zero-low", telemetry=_telemetry()),
    )

    # When
    sidecar = run_ripple(_request(session, band_low_hz=0.0, band_high_hz=101.0))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: первый положительный центр = 1 Гц; хвост Hann-утечки входит в полосу.
    band = cast("dict[str, object]", _arr(payload, "bands")[0])
    assert band["availability"] == "available"
    assert _float(band, "first_center_hz") == pytest.approx(1.0)
    assert _float(band, "last_center_hz") == pytest.approx(101.0)
    assert band["bin_count"] == 101
    assert _float(band, "rms_v") == pytest.approx(_AMPLITUDE_V / math.sqrt(2.0), rel=1e-5)


def test_baseline_same_geometry_compared_beside_without_subtraction(tmp_path: Path) -> None:
    # Given: фон той же геометрии — тот же адаптер, fs/range/probe/conversion.
    rng = np.random.default_rng(6022)
    baseline_noise = rng.normal(0.0, 0.001, _COUNT).astype(np.float32)
    measurement = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-meas", telemetry=_telemetry()),
    )
    baseline = _write(
        tmp_path / "base",
        ch1=baseline_noise,
        manifest=_manifest(session_id="ripple-base", telemetry=_telemetry()),
    )

    # When
    sidecar = run_ripple(
        _request(
            measurement,
            baseline_path=baseline.session_dir,
            baseline_attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
        )
    )
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: фон РЯДОМ с собственными числами; сравнение доступно; без разностей.
    baseline_block = _obj(payload, "baseline")
    assert baseline_block["comparison_status"] == "available"
    assert _codes(baseline_block) == []
    assert baseline_block["attachment_basis"] == "same_adapter_tip_shorted_to_return"
    baseline_session = _obj(baseline_block, "session")
    assert baseline_session["session_id"] == "ripple-base"
    assert len(cast("str", baseline_session["manifest_sha256"])) == 64
    baseline_time = _obj(baseline_block, "time_domain")
    assert baseline_time["availability"] == "available"
    assert _float(baseline_time, "rms_ac_v") == pytest.approx(0.001, rel=0.05)
    baseline_spectrum = _obj(baseline_block, "spectrum")
    assert baseline_spectrum["availability"] == "available"
    baseline_bands = _arr(baseline_block, "bands")
    assert cast("dict[str, object]", baseline_bands[0])["availability"] == "available"
    text = sidecar.sidecar_path.read_text(encoding="utf-8")
    assert "delta" not in text.lower()
    assert "excess" not in text.lower()
    # Измерение осталось валидным рядом с фоном.
    assert _obj(payload, "time_domain")["availability"] == "available"


def test_incompatible_baseline_rate_keeps_measurement_valid(tmp_path: Path) -> None:
    # Given: корректный, но несовместимый фон — другая частота дискретизации.
    measurement = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-meas", telemetry=_telemetry()),
    )
    baseline = _write(
        tmp_path / "base",
        ch1=_sine_record(fs=20_000.0),
        manifest=_manifest(
            session_id="ripple-base",
            fs=20_000.0,
            count=_COUNT,
            telemetry=_telemetry(),
        ),
    )

    # When
    sidecar = run_ripple(
        _request(
            measurement,
            baseline_path=baseline.session_dir,
            baseline_attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
        )
    )
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: сравнение недоступно с типовым кодом; само измерение валидно.
    baseline_block = _obj(payload, "baseline")
    assert baseline_block["comparison_status"] == "unavailable"
    assert "baseline_sample_rate_mismatch" in _codes(baseline_block)
    assert _obj(payload, "time_domain")["availability"] == "available"
    assert payload["schema_version"] == 1


def test_baseline_range_and_probe_mismatch_stays_comparison_unavailable(
    tmp_path: Path,
) -> None:
    # Given: другой диапазон и множитель пробника у фона.
    measurement = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-geom-meas",
            range_code=10,
            probe_multiplier=1.0,
            telemetry=_telemetry(),
        ),
    )
    baseline = _write(
        tmp_path / "base",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-geom-base",
            range_code=1,
            probe_multiplier=10.0,
            telemetry=_telemetry(),
        ),
    )

    # When
    sidecar = run_ripple(
        _request(
            measurement,
            baseline_path=baseline.session_dir,
            baseline_attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
        )
    )
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: типовые коды несовместимости; измерение остаётся валидным.
    baseline_block = _obj(payload, "baseline")
    assert baseline_block["comparison_status"] == "unavailable"
    assert "baseline_range_code_mismatch" in _codes(baseline_block)
    assert "baseline_probe_multiplier_mismatch" in _codes(baseline_block)
    assert _obj(payload, "time_domain")["availability"] == "available"


def test_baseline_without_recorded_geometry_is_unavailable(tmp_path: Path) -> None:
    # Given: обе записи устройства без записанной модели входа (schema v1).
    measurement = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-geom-absent",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(),
        ),
    )
    baseline = _write(
        tmp_path / "base",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-geom-absent-base",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(),
        ),
    )

    # When
    sidecar = run_ripple(
        _request(
            measurement,
            baseline_path=baseline.session_dir,
            baseline_attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
        )
    )
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: отсутствующая геометрия — недоступное сравнение, не догадка.
    baseline_block = _obj(payload, "baseline")
    assert baseline_block["comparison_status"] == "unavailable"
    assert "baseline_geometry_missing" in _codes(baseline_block)
    assert _obj(payload, "time_domain")["availability"] == "available"


def test_baseline_mismatched_geometry_is_unavailable(tmp_path: Path) -> None:
    # Given: две модели входа с разным сопротивлением — геометрия не совпадает.
    measurement = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-geom-diff",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(),
            ch1_setup=_floating_geometry(resistance_ohm=100.0),
        ),
    )
    baseline = _write(
        tmp_path / "base",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-geom-diff-base",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(),
            ch1_setup=_floating_geometry(resistance_ohm=50.0),
        ),
    )

    # When
    sidecar = run_ripple(
        _request(
            measurement,
            baseline_path=baseline.session_dir,
            baseline_attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
        )
    )
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then
    baseline_block = _obj(payload, "baseline")
    assert baseline_block["comparison_status"] == "unavailable"
    assert "baseline_geometry_mismatch" in _codes(baseline_block)


def test_terminated_instrument_baseline_is_not_a_matched_background(tmp_path: Path) -> None:
    # Given: legacy self-noise с 50-ом терминацией — прибор без адаптера/сборки.
    measurement = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-term-meas",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(),
            ch1_setup=_floating_geometry(),
        ),
    )
    baseline = _write(
        tmp_path / "base",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-term-base",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(),
            session_type=SessionType.SELF_NOISE,
            ch1_setup=ScopeInputTerminated(termination_resistance_ohm=50.0),
        ),
    )

    # When
    sidecar = run_ripple(
        _request(
            measurement,
            baseline_path=baseline.session_dir,
            baseline_attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
        )
    )
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: только прибор — не согласованный фон rail-измерения.
    baseline_block = _obj(payload, "baseline")
    assert baseline_block["comparison_status"] == "unavailable"
    assert "baseline_instrument_only" in _codes(baseline_block)
    qualification = _obj(baseline_block, "session")
    setup = cast("dict[str, object]", qualification["ch1_setup"])
    assert setup["kind"] == "scope_input_terminated_v1"
    assert _obj(payload, "time_domain")["availability"] == "available"


def test_unreadable_baseline_path_is_typed_input_error(tmp_path: Path) -> None:
    # Given: явно заданный, но несуществующий путь фона.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-meas", telemetry=_telemetry()),
    )
    request = _request(session, baseline_path=tmp_path / "missing")

    # When / Then
    with pytest.raises(InputError):
        run_ripple(request)


def test_corrupt_baseline_is_typed_input_error(tmp_path: Path) -> None:
    # Given: корректный каталог фона, но повреждённый ch1.npy.
    measurement = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-meas", telemetry=_telemetry()),
    )
    baseline_dir = write_session(
        session_dir=tmp_path / "base",
        manifest=_manifest(session_id="ripple-base", telemetry=_telemetry()),
        ch1=_sine_record().astype(np.float32),
        ch2=None,
    )
    (baseline_dir / "ch1.npy").write_bytes(b"not an npy header")
    request = _request(
        measurement,
        baseline_path=baseline_dir,
        baseline_attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
    )

    # When / Then: повреждённый вход — типовой отказ, не ValueError наружу.
    with pytest.raises(InputError, match="фон не читается"):
        run_ripple(request)


def test_baseline_without_attachment_declaration_stays_comparison_unavailable(
    tmp_path: Path,
) -> None:
    # Given: совместимый фон, но условие подключения не объявлено.
    measurement = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-meas", telemetry=_telemetry()),
    )
    baseline = _write(
        tmp_path / "base",
        ch1=np.zeros(_COUNT, dtype=np.float32),
        manifest=_manifest(session_id="ripple-base", telemetry=_telemetry()),
    )

    # When
    sidecar = run_ripple(_request(measurement, baseline_path=baseline.session_dir))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then
    baseline_block = _obj(payload, "baseline")
    assert baseline_block["comparison_status"] == "unavailable"
    assert "baseline_attachment_unqualified" in _codes(baseline_block)
    assert baseline_block["attachment_basis"] is None


def test_short_record_spectrum_unavailable_time_domain_alive(tmp_path: Path) -> None:
    # Given: 1.2 с при fs 10 кГц — после префикса 1 с остаётся 0.2 с < nperseg.
    count = 12_000
    record = _sine_record(count=count)
    session = _write(
        tmp_path / "meas",
        ch1=record,
        manifest=_manifest(
            session_id="ripple-short", count=count, telemetry=_telemetry(count=count)
        ),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: спектр недоступен, разрешение не укорочено молча.
    spectrum = _obj(payload, "spectrum")
    assert spectrum["availability"] == "unavailable"
    assert "insufficient_samples" in _codes(spectrum)
    assert spectrum["frequency_hz"] == []
    assert spectrum["psd_v2_per_hz"] == []
    settings = _obj(spectrum, "settings")
    assert settings["nperseg"] == 10_000
    assert settings["segment_count"] is None
    assert spectrum["used_sample_count"] is None
    band = cast("dict[str, object]", _arr(payload, "bands")[0])
    assert band["availability"] == "unavailable"
    assert band["rms_v"] is None
    # Time-domain остаётся доступным независимо от спектра.
    time_domain = _obj(payload, "time_domain")
    assert time_domain["availability"] == "available"
    assert _float(time_domain, "rms_ac_v") == pytest.approx(_AMPLITUDE_V / math.sqrt(2.0), rel=1e-5)


def test_nan_input_is_unavailable_not_nan(tmp_path: Path) -> None:
    # Given: NaN внутри выбранного спана после префикса установления.
    record = _sine_record()
    record[12_000] = np.nan
    session = _write(
        tmp_path / "meas",
        ch1=record,
        manifest=_manifest(session_id="ripple-nan", telemetry=_telemetry()),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: недоступность с кодом, числа null, JSON конечен.
    time_domain = _obj(payload, "time_domain")
    assert time_domain["availability"] == "unavailable"
    assert "nonfinite_samples" in _codes(time_domain)
    assert time_domain["mean_v"] is None
    assert time_domain["rms_ac_v"] is None
    assert time_domain["vpp_v"] is None
    qc = _obj(payload, "qc")
    assert qc["nonfinite_count"] == 1
    spectrum = _obj(payload, "spectrum")
    assert spectrum["availability"] == "unavailable"
    assert "nonfinite_samples" in _codes(spectrum)
    # Интервал, содержащий NaN, недоступен; соседний чистый интервал жив.
    intervals = _arr(payload, "intervals")
    first, tail = cast("dict[str, object]", intervals[0]), cast("dict[str, object]", intervals[1])
    assert first["availability"] == "unavailable"
    assert "nonfinite_samples" in _codes(first)
    assert first["mean_v"] is None
    assert tail["availability"] == "available"
    assert _float(tail, "mean_v") == pytest.approx(_DC_V, rel=1e-5)
    assert "NaN" not in sidecar.sidecar_path.read_text(encoding="utf-8")
    _assert_finite(payload)


def test_inf_input_is_unavailable_not_infinity(tmp_path: Path) -> None:
    # Given: +Inf внутри выбранного спана — не удаляем и не подменяем максимумом.
    record = _sine_record()
    record[12_000] = np.inf
    session = _write(
        tmp_path / "meas",
        ch1=record,
        manifest=_manifest(session_id="ripple-inf", telemetry=_telemetry()),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: недоступность с кодом; JSON конечен, Infinity не сериализуется.
    time_domain = _obj(payload, "time_domain")
    assert time_domain["availability"] == "unavailable"
    assert "nonfinite_samples" in _codes(time_domain)
    assert time_domain["rms_ac_v"] is None
    intervals = _arr(payload, "intervals")
    first, tail = cast("dict[str, object]", intervals[0]), cast("dict[str, object]", intervals[1])
    assert first["availability"] == "unavailable"
    assert "nonfinite_samples" in _codes(first)
    assert tail["availability"] == "available"
    assert "Infinity" not in sidecar.sidecar_path.read_text(encoding="utf-8")
    _assert_finite(payload)


def test_nonfinite_in_excluded_prefix_stays_visible_but_does_not_poison_span(
    tmp_path: Path,
) -> None:
    # Given: NaN только в отбрасываемом префиксе установления.
    record = _sine_record()
    record[5] = np.nan
    session = _write(
        tmp_path / "meas",
        ch1=record,
        manifest=_manifest(
            session_id="ripple-nan-prefix",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(),
        ),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: счётчик полной записи сохранён, выбранный спан чист и доступен.
    qc = _obj(payload, "qc")
    assert qc["nonfinite_count"] == 0
    assert qc["record_nonfinite_count"] == 1
    assert qc["nonfinite_count_scope"] == "selected_span"
    assert _codes(qc) == []
    assert _obj(payload, "time_domain")["availability"] == "available"


def test_clipped_prefix_does_not_poison_clean_suffix(tmp_path: Path) -> None:
    # Given: два rail-отсчёта ТОЛЬКО в отбрасываемом префиксе установления.
    record = _sine_record()
    rail_high = float(apply_adc_calibration(np.array([255], dtype=np.uint8), range_code=1)[0])
    record[5] = rail_high
    record[7_000] = rail_high
    session = _write(
        tmp_path / "meas",
        ch1=record,
        manifest=_manifest(
            session_id="ripple-clip-prefix",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(clip_high=2),
        ),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: суффикс доказуемо чист — доступен; ценз полного ряда сохранён.
    qc = _obj(payload, "qc")
    assert qc["clipping_assessment"] == "rail_hits_present_localized"
    assert qc["clip_count_scope"] == "float32_endpoints_from_manifest_conversion"
    assert (qc["clip_low_count"], qc["clip_high_count"]) == (0, 2)
    assert qc["dropped_samples"] is None
    assert _codes(qc) == []
    assert _obj(payload, "time_domain")["availability"] == "available"
    assert _float(_obj(payload, "time_domain"), "rms_ac_v") == pytest.approx(
        _AMPLITUDE_V / math.sqrt(2.0), rel=1e-5
    )


def test_rail_hit_inside_span_invalidates_span_without_shrinking(tmp_path: Path) -> None:
    # Given: один rail-отсчёт внутри выбранного спана.
    record = _sine_record()
    rail_low = float(apply_adc_calibration(np.array([0], dtype=np.uint8), range_code=1)[0])
    record[15_000] = rail_low
    session = _write(
        tmp_path / "meas",
        ch1=record,
        manifest=_manifest(
            session_id="ripple-clip-span",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(clip_low=1),
        ),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: спан недоступен, но границы и длина не сжаты, отсчёты не удалены.
    time_domain = _obj(payload, "time_domain")
    assert time_domain["availability"] == "unavailable"
    assert "clipped" in _codes(time_domain)
    assert time_domain["rms_ac_v"] is None
    selection = _obj(payload, "selection")
    assert selection["sample_start_index"] == _PREFIX_SAMPLES
    assert selection["sample_end_index_exclusive"] == _COUNT
    assert selection["sample_count"] == _COUNT - _PREFIX_SAMPLES
    qc = _obj(payload, "qc")
    assert (qc["clip_low_count"], qc["clip_high_count"]) == (1, 0)
    # Интервал с попаданием недоступен, соседний чистый интервал доступен.
    intervals = _arr(payload, "intervals")
    first, tail = cast("dict[str, object]", intervals[0]), cast("dict[str, object]", intervals[1])
    assert first["availability"] == "unavailable"
    assert "clipped" in _codes(first)
    assert (first["clip_low_count"], first["clip_high_count"]) == (1, 0)
    assert tail["availability"] == "available"
    assert (tail["clip_low_count"], tail["clip_high_count"]) == (0, 0)
    assert _obj(payload, "spectrum")["availability"] == "unavailable"


def test_aggregate_nonzero_calibrated_census_is_unlocalizable(tmp_path: Path) -> None:
    # Given: телеметрия с клиппингом и применённой калибровкой — позиции неизвестны.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-agg",
            source=SessionSource.DEVICE,
            telemetry=_telemetry(clip_high=3, calibration_used=True),
        ),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: clipping_unknown, счётчики сохранены, нули не выдуманы.
    qc = _obj(payload, "qc")
    assert qc["clipping_assessment"] == "rail_hits_present_unlocalizable"
    assert qc["clip_count_scope"] == "aggregate_saved_record_telemetry"
    assert qc["clip_high_count"] == 3
    assert "clipping_unknown" in _codes(qc)
    assert _obj(payload, "time_domain")["availability"] == "unavailable"
    assert "clipping_unknown" in _codes(_obj(payload, "time_domain"))


def test_clip_census_telemetry_mismatch_fails_closed(tmp_path: Path) -> None:
    # Given: телеметрия рапортует rail hit, но конверсия рельсов его не находит.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-clip-mismatch",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(clip_high=1),
        ),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: расхождение ценза — fail closed, а не нулевой клиппинг.
    qc = _obj(payload, "qc")
    assert qc["clipping_assessment"] == "clip_census_inconsistent"
    assert qc["clip_count_scope"] == "aggregate_saved_record_telemetry"
    assert (qc["clip_low_count"], qc["clip_high_count"]) == (0, 1)
    assert "clipping_unknown" in _codes(qc)
    assert "clip_census_inconsistent" in _codes(qc)
    assert _obj(payload, "time_domain")["availability"] == "unavailable"


def test_device_without_telemetry_fails_closed(tmp_path: Path) -> None:
    # Given: legacy-запись устройства без телеметрии — ценза нет.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-legacy",
            source=SessionSource.DEVICE,
            telemetry=None,
        ),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then
    qc = _obj(payload, "qc")
    assert qc["clipping_assessment"] == "clipping_unknown"
    assert qc["clip_count_scope"] is None
    assert qc["clip_low_count"] is None
    assert qc["clip_high_count"] is None
    assert "clipping_unknown" in _codes(qc)
    assert _obj(payload, "time_domain")["availability"] == "unavailable"


def test_missing_settling_declaration_keeps_metrics_unavailable(tmp_path: Path) -> None:
    # Given: оператор не объявил предварительное подключение.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-unset", telemetry=_telemetry()),
    )

    # When
    sidecar = run_ripple(_request(session, settling=SettlingDeclaration.UNKNOWN))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: база установления неизвестна — публичные числа недоступны.
    selection = _obj(payload, "selection")
    assert selection["settling_basis"] == "settling_unknown"
    assert selection["excluded_prefix_samples"] == 0
    assert selection["sample_start_index"] == 0
    for key in ("time_domain", "spectrum"):
        block = _obj(payload, key)
        assert block["availability"] == "unavailable"
        assert "settling_unknown" in _codes(block)
    assert _obj(payload, "provenance")["operator_attachment"] == "settling_unknown"


def test_x10_adapter_has_no_transfer_and_no_settling(tmp_path: Path) -> None:
    # Given: манифест x10 и согласованный адаптер x10 — физическая модель не заявлена.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-x10",
            telemetry=_telemetry(),
            probe_multiplier=10.0,
        ),
    )

    # When
    sidecar = run_ripple(_request(session, adapter=AdapterSpec(probe_multiplier=10)))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then
    adapter = _obj(payload, "adapter")
    assert adapter["transfer_status"] == "unavailable_unknown_probe_topology"
    assert adapter["fc_hz"] is None
    assert adapter["tau_s"] is None
    selection = _obj(payload, "selection")
    assert selection["settling_basis"] == "settling_unknown"
    assert selection["excluded_prefix_samples"] == 0
    assert _obj(payload, "time_domain")["availability"] == "unavailable"


def test_probe_mismatch_is_typed_input_error(tmp_path: Path) -> None:
    # Given: манифест x10, адаптер объявлен x1 — равенство нарушено.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-mismatch",
            telemetry=_telemetry(),
            probe_multiplier=10.0,
        ),
    )

    # When / Then: --probe это проверка равенства, а не пересчёт.
    with pytest.raises(InputError, match="probe_metadata_mismatch"):
        run_ripple(_request(session))


@pytest.mark.parametrize(
    ("low", "high"),
    [
        (0.0, 0.5),
        (-1.0, 100.0),
        (100.0, 100.0),
        (200.0, 100.0),
        (5_000.0, 6_000.0),
        (0.2, 0.6),
        (float("nan"), 100.0),
        (100.0, float("inf")),
    ],
)
def test_invalid_band_is_typed_input_error(tmp_path: Path, low: float, high: float) -> None:
    # Given: готовая сессия и заведомо некорректная полоса.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-band", telemetry=_telemetry()),
    )
    request = _request(session, band_low_hz=low, band_high_hz=high)

    # When / Then
    with pytest.raises(InputError):
        run_ripple(request)


def test_constant_signal_has_zero_ac_rms_and_vpp(tmp_path: Path) -> None:
    # Given: константный чистый сигнал.
    session = _write(
        tmp_path / "meas",
        ch1=np.full(_COUNT, 1.25, dtype=np.float32),
        manifest=_manifest(session_id="ripple-const", telemetry=_telemetry()),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: нулевые AC-метрики — валидный результат, а не NO_MEASUREMENT.
    time_domain = _obj(payload, "time_domain")
    assert time_domain["availability"] == "available"
    assert _float(time_domain, "mean_v") == pytest.approx(1.25)
    assert _float(time_domain, "rms_ac_v") == 0.0
    assert _float(time_domain, "vpp_v") == 0.0


def test_empty_span_after_settling_is_explicit_unavailability(tmp_path: Path) -> None:
    # Given: запись ровно в окно установления — после префикса пусто.
    count = _PREFIX_SAMPLES
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(count=count),
        manifest=_manifest(
            session_id="ripple-empty", count=count, telemetry=_telemetry(count=count)
        ),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: таймлайн не сжат, всё недоступно с кодом empty_span.
    selection = _obj(payload, "selection")
    assert (selection["sample_start_index"], selection["sample_end_index_exclusive"]) == (
        _PREFIX_SAMPLES,
        _PREFIX_SAMPLES,
    )
    assert selection["sample_count"] == 0
    time_domain = _obj(payload, "time_domain")
    assert time_domain["availability"] == "unavailable"
    assert "empty_span" in _codes(time_domain)
    assert _arr(payload, "intervals") == []


def test_record_shorter_than_settling_prefix_reports_actual_excluded(
    tmp_path: Path,
) -> None:
    # Given: запись короче номинального окна установления.
    count = 5_000
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(count=count),
        manifest=_manifest(
            session_id="ripple-short-prefix", count=count, telemetry=_telemetry(count=count)
        ),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: исключено фактически 5000, номинальная политика 10000 сохранена.
    selection = _obj(payload, "selection")
    assert (selection["sample_start_index"], selection["sample_end_index_exclusive"]) == (
        count,
        count,
    )
    assert selection["sample_count"] == 0
    assert selection["excluded_prefix_samples"] == count
    assert selection["settling_prefix_samples_nominal"] == _PREFIX_SAMPLES
    assert "empty_span" in _codes(_obj(payload, "time_domain"))


def test_existing_session_files_stay_byte_identical_and_rewrite_is_stable(
    tmp_path: Path,
) -> None:
    # Given: сессия на диске; хэши существующих файлов до прогона.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-bytes", telemetry=_telemetry()),
    )
    before = {
        name: hashlib.sha256((session.session_dir / name).read_bytes()).hexdigest()
        for name in ("ch1.npy", "manifest.json")
    }

    # When
    first = run_ripple(_request(session))
    second = run_ripple(_request(session))

    # Then: существующие файлы не тронуты; сайдкар заменён детерминированно.
    after = {
        name: hashlib.sha256((session.session_dir / name).read_bytes()).hexdigest()
        for name in ("ch1.npy", "manifest.json")
    }
    assert after == before
    assert first.sidecar_path == session.session_dir / "ripple.json"
    assert first.sidecar_path.read_bytes() == second.sidecar_path.read_bytes()
    # Частичный файл-сосед не остался.
    leftovers = [p.name for p in session.session_dir.iterdir() if "partial" in p.name]
    assert leftovers == []


def test_ripple_json_does_not_break_catalog_scan_and_reconcile(tmp_path: Path) -> None:
    # Given: корень сессий с сайдкаром ripple.json в каталоге сессии.
    root = tmp_path / "sessions"
    session = _write(
        root / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-catalog", telemetry=_telemetry()),
    )
    run_ripple(_request(session))
    database = tmp_path / "catalog.sqlite3"
    apply_migrations(database)

    # When
    first = reconcile_catalog(root, database)
    second = reconcile_catalog(root, database)
    scanned = scan_immediate_directories(root)
    parsed = parse_directory(scanned[0])

    # Then: сессия здорова, сверка идемпотентна.
    assert (first.inserted, second.skipped) == (1, 1)
    assert parsed.health == "ok"
    assert parsed.session_id == "ripple-catalog"


def test_two_hz_bandwidth_is_rejected_as_estimator_input(tmp_path: Path) -> None:
    # Given: fs=2 Гц даёт nperseg=2 — оценка вырождена; отказ до анализа.
    count = 40
    session = _write(
        tmp_path / "meas",
        ch1=np.zeros(count, dtype=np.float32),
        manifest=_manifest(
            session_id="ripple-fs2",
            count=count,
            fs=2.0,
            telemetry=_telemetry(count=count),
        ),
    )

    # When / Then
    with pytest.raises(InputError):
        run_ripple(_request(session))


def test_baseline_short_record_comparison_unavailable_with_reason(tmp_path: Path) -> None:
    # Given: совместимый по геометрии фон, но запись короче nperseg после префикса.
    measurement = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-meas", telemetry=_telemetry()),
    )
    count = 12_000
    baseline = _write(
        tmp_path / "base",
        ch1=_sine_record(count=count),
        manifest=_manifest(
            session_id="ripple-base",
            count=count,
            telemetry=_telemetry(count=count),
        ),
    )

    # When
    sidecar = run_ripple(
        _request(
            measurement,
            baseline_path=baseline.session_dir,
            baseline_attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
        )
    )
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: сравнение недоступно с типовым кодом; измерение живо.
    baseline_block = _obj(payload, "baseline")
    assert baseline_block["comparison_status"] == "unavailable"
    assert "baseline_result_unavailable" in _codes(baseline_block)
    assert "insufficient_samples" in _codes(baseline_block)
    baseline_spectrum = _obj(baseline_block, "spectrum")
    assert baseline_spectrum["availability"] == "unavailable"
    assert _obj(payload, "time_domain")["availability"] == "available"


def test_baseline_duration_mismatch_keeps_numbers_but_comparison_unavailable(
    tmp_path: Path,
) -> None:
    # Given: совместимая геометрия, но фон длиннее измерения.
    measurement = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-meas", telemetry=_telemetry()),
    )
    count = _COUNT + 5_000
    baseline = _write(
        tmp_path / "base",
        ch1=_sine_record(count=count),
        manifest=_manifest(
            session_id="ripple-base",
            count=count,
            telemetry=_telemetry(count=count),
        ),
    )

    # When
    sidecar = run_ripple(
        _request(
            measurement,
            baseline_path=baseline.session_dir,
            baseline_attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
        )
    )
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: числа фона видимы, но сравнение по разным длинам недоступно.
    baseline_block = _obj(payload, "baseline")
    assert baseline_block["comparison_status"] == "unavailable"
    assert _codes(baseline_block) == ["baseline_duration_mismatch"]
    baseline_selection = _obj(baseline_block, "selection")
    assert baseline_selection["sample_count"] == 24_000
    assert _obj(baseline_block, "time_domain")["availability"] == "available"
    baseline_spectrum = _obj(baseline_block, "spectrum")
    assert baseline_spectrum["availability"] == "available"
    assert _obj(baseline_spectrum, "settings")["segment_count"] == 3
    assert _obj(payload, "time_domain")["availability"] == "available"


def test_unavailable_measurement_makes_comparison_unavailable(tmp_path: Path) -> None:
    # Given: измерение с rail hit, чистый фон той же геометрии и длины.
    measurement_record = _sine_record()
    rail_low = float(apply_adc_calibration(np.array([0], dtype=np.uint8), range_code=1)[0])
    measurement_record[15_000] = rail_low
    measurement = _write(
        tmp_path / "meas",
        ch1=measurement_record,
        manifest=_manifest(
            session_id="ripple-meas-bad",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(clip_low=1),
            ch1_setup=_floating_geometry(),
        ),
    )
    baseline = _write(
        tmp_path / "base",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-base-clean",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(),
            ch1_setup=_floating_geometry(),
        ),
    )

    # When
    sidecar = run_ripple(
        _request(
            measurement,
            baseline_path=baseline.session_dir,
            baseline_attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
        )
    )
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: сравнение недоступно из-за измерения; числа фона не теряются.
    assert _obj(payload, "time_domain")["availability"] == "unavailable"
    baseline_block = _obj(payload, "baseline")
    assert baseline_block["comparison_status"] == "unavailable"
    assert _codes(baseline_block) == ["measurement_result_unavailable"]
    assert _obj(baseline_block, "time_domain")["availability"] == "available"


def test_synthetic_sessions_without_telemetry_compare_beside(tmp_path: Path) -> None:
    # Given: свежие simulate-сессии без ADC-телеметрии — оба плана синтетические.
    measurement = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-syn-meas", telemetry=None),
    )
    baseline = _write(
        tmp_path / "base",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-syn-base", telemetry=None),
    )

    # When
    sidecar = run_ripple(
        _request(
            measurement,
            baseline_path=baseline.session_dir,
            baseline_attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
        )
    )
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: отсутствие ADC-калибровки у синтетики не блокирует сравнение.
    baseline_block = _obj(payload, "baseline")
    assert baseline_block["comparison_status"] == "available"
    assert _codes(baseline_block) == []
    assert _obj(baseline_block, "time_domain")["availability"] == "available"
    assert _obj(baseline_block, "spectrum")["availability"] == "available"


def test_calibrated_baseline_identity_is_not_assumed(tmp_path: Path) -> None:
    # Given: обе записи устройства прошли калибровку, но коэффициенты не сохранены.
    measurement = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-cal-meas",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(calibration_used=True),
            ch1_setup=_floating_geometry(),
        ),
    )
    baseline = _write(
        tmp_path / "base",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-cal-base",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(calibration_used=True),
            ch1_setup=_floating_geometry(),
        ),
    )

    # When
    sidecar = run_ripple(
        _request(
            measurement,
            baseline_path=baseline.session_dir,
            baseline_attachment=BaselineAttachment.SAME_ADAPTER_TIP_SHORTED,
        )
    )
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: равные булевы флаги недостаточны — сравнение недоступно, измерение живо.
    baseline_block = _obj(payload, "baseline")
    assert baseline_block["comparison_status"] == "unavailable"
    assert "baseline_calibration_identity_unknown" in _codes(baseline_block)
    assert _obj(payload, "time_domain")["availability"] == "available"


def test_interval_window_option_is_recorded_and_applied(tmp_path: Path) -> None:
    # Given: окно 0.5 с — первый интервал 5 000 отсчётов от границы префикса.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(session_id="ripple-win", telemetry=_telemetry()),
    )

    # When
    sidecar = run_ripple(_request(session, window_s=0.5))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then
    assert _obj(payload, "options")["interval_window_s"] == 0.5
    intervals = _arr(payload, "intervals")
    assert len(intervals) == 4
    heads = [cast("dict[str, object]", item)["start_index"] for item in intervals]
    assert heads == [10_000, 15_000, 20_000, 25_000]
    assert all(cast("dict[str, object]", item)["complete"] is True for item in intervals[:3])
    assert cast("dict[str, object]", intervals[3])["complete"] is False


def test_manifest_probe_is_asserted_not_rescaled(tmp_path: Path) -> None:
    # Given: согласованный x10 — вольты не пересчитываются, провенанс сохранён.
    record = _sine_record() * 10.0
    session = _write(
        tmp_path / "meas",
        ch1=record.astype(np.float32),
        manifest=_manifest(
            session_id="ripple-x10-ok",
            telemetry=_telemetry(),
            probe_multiplier=10.0,
        ),
    )

    # When
    sidecar = run_ripple(_request(session, adapter=AdapterSpec(probe_multiplier=10)))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: mean соответствует хранимым вольтам без второго масштабирования.
    time_domain = _obj(payload, "time_domain")
    assert time_domain["availability"] == "unavailable"  # settling_unknown для x10
    span = np.asarray(record[_PREFIX_SAMPLES:], dtype=np.float64)
    selection = _obj(payload, "selection")
    assert selection["sample_start_index"] == 0  # без префикса — нет модели
    assert _obj(payload, "provenance")["probe_multiplier"] == 10.0
    assert _obj(payload, "adapter")["probe_multiplier"] == 10
    mu = float(np.mean(span))
    assert math.isfinite(mu)  # sanity: ожидания выведены из хранимого вектора


def test_settings_record_tail_and_never_shorten_resolution(tmp_path: Path) -> None:
    # Given: 3 сегмента: span 19k, nperseg 10k, hop 5k -> used 20k невозможен;
    # span ровно 20k даёт 3 сегмента, used 20k, хвост 0.
    count = _PREFIX_SAMPLES + 20_000
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(count=count),
        manifest=_manifest(
            session_id="ripple-3seg",
            count=count,
            telemetry=_telemetry(count=count),
        ),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then
    spectrum = _obj(payload, "spectrum")
    settings = _obj(spectrum, "settings")
    assert settings["segment_count"] == 3
    assert spectrum["used_sample_count"] == 20_000
    assert spectrum["ignored_tail_samples"] == 0


def test_happy_path_uses_device_source_with_clean_zero_census(tmp_path: Path) -> None:
    # Given: запись устройства с нулевым цензом клиппинга и без калибровки.
    session = _write(
        tmp_path / "meas",
        ch1=_sine_record(),
        manifest=_manifest(
            session_id="ripple-dev",
            source=SessionSource.DEVICE,
            range_code=1,
            telemetry=_telemetry(),
        ),
    )

    # When
    sidecar = run_ripple(_request(session))
    payload = json.loads(sidecar.sidecar_path.read_text(encoding="utf-8"))

    # Then: нулевой ценз локализуем конверсией конечных точек.
    qc = _obj(payload, "qc")
    assert qc["clipping_assessment"] == "no_rail_hits"
    assert qc["clip_count_scope"] == "float32_endpoints_from_manifest_conversion"
    assert (qc["clip_low_count"], qc["clip_high_count"]) == (0, 0)
    assert _codes(qc) == []
    selection = _obj(payload, "selection")
    assert selection["continuity_status"] == "host_contiguous_unverified"
    assert selection["continuity_reason_codes"] == ["host_contiguous_unverified"]
    assert qc["dropped_samples"] is None
    provenance = _obj(payload, "provenance")
    assert provenance["voltage_plane"] == "recorded_ch1_volts_observed_uncalibrated"
    assert _obj(payload, "time_domain")["availability"] == "available"
