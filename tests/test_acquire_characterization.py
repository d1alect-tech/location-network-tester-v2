"""Характеризация чистых помощников ``lnt.acquire`` перед расслоением фасада.

Тесты фиксируют наблюдаемый контракт до переноса кода в листья: коды
протокола драйвера, точный русский текст ошибок входа и снимки метаданных
канала. Отдельная группа охраняет единственность источника истины raw -> В:
масштаб и поправка АЦП живут только в ``lnt.adc_calibration``.
"""

import ast
from dataclasses import asdict
from pathlib import Path

import pytest

from lnt import acquire
from lnt.acquire import DEFAULT_RANGE_V, DEFAULT_SAMPLE_RATE_HZ
from lnt.acquire_setup import (
    _capture_setup,
    _ch1_meta,
    _ch1_probe_multiplier,
    _default_setup,
)
from lnt.acquire_validation import RANGE_CODES, _range_code, _rate_code
from lnt.errors import InputError
from lnt.types import (
    ChannelRole,
    ComponentValuesBasis,
    FloatingDifferentialRcShunt,
    ReferenceAssumption,
    ScopeInputTerminated,
    SessionType,
    TransformerLineProbe,
)

_SRC = Path(__file__).resolve().parents[1] / "src" / "lnt"
_RATE_NOT_FINITE = "частота дискретизации должна быть конечной и положительной"
_RANGE_SUPPORTED = "допустимы 5/1/0.5 В"
_SCALE_NAMES = frozenset({"ADC_CENTER", "VOLTS_SCALE", "_scale_raw"})


def _rc_shunt() -> FloatingDifferentialRcShunt:
    return FloatingDifferentialRcShunt(
        resistance_ohm=100.0,
        c1_f=10e-9,
        c2_f=10e-9,
        component_values_basis=ComponentValuesBasis.NOMINAL,
        reference_assumption=ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
    )


def _line_probe() -> TransformerLineProbe:
    return TransformerLineProbe(
        nominal_primary_v=230.0,
        nominal_secondary_v=6.0,
        probe_multiplier=10.0,
    )


# --- (a) _rate_code: полная таблица поддерживаемых частот и отказов ---------


@pytest.mark.parametrize(
    ("sample_rate_hz", "expected_code"),
    [
        (1_000_000.0, 1),
        (2_000_000.0, 2),
        (4_000_000.0, 4),
        (8_000_000.0, 8),
        (10_000_000.0, 10),
        (15_000_000.0, 15),
    ],
)
def test_rate_code_maps_integer_megahertz(sample_rate_hz: float, expected_code: int) -> None:
    assert _rate_code(sample_rate_hz) == expected_code


def test_default_sample_rate_is_a_supported_rate() -> None:
    assert _rate_code(DEFAULT_SAMPLE_RATE_HZ) == 8


@pytest.mark.parametrize(
    "sample_rate_hz",
    [0.0, -1.0, -8_000_000.0, float("nan"), float("inf"), float("-inf")],
)
def test_rate_code_rejects_non_finite_or_non_positive(sample_rate_hz: float) -> None:
    with pytest.raises(InputError) as excinfo:
        _rate_code(sample_rate_hz)
    assert str(excinfo.value) == _RATE_NOT_FINITE


@pytest.mark.parametrize(
    ("sample_rate_hz", "expected_message"),
    [
        (500_000.0, "частота 500000 Гц: допустимы целые 1..15 МГц (dual)"),
        (8_500_000.0, "частота 8500000 Гц: допустимы целые 1..15 МГц (dual)"),
        (16_000_000.0, "частота 16000000 Гц: допустимы целые 1..15 МГц (dual)"),
        (48_000_000.0, "частота 48000000 Гц: допустимы целые 1..15 МГц (dual)"),
    ],
)
def test_rate_code_rejects_unsupported_rate(sample_rate_hz: float, expected_message: str) -> None:
    with pytest.raises(InputError) as excinfo:
        _rate_code(sample_rate_hz)
    assert str(excinfo.value) == expected_message


# --- (b) _range_code: полная таблица диапазонов и отказов -------------------


def test_range_codes_table_is_the_driver_gain_mapping() -> None:
    assert RANGE_CODES == {5.0: 1, 1.0: 5, 0.5: 10}
    assert list(RANGE_CODES) == [5.0, 1.0, 0.5]


@pytest.mark.parametrize(
    ("range_v", "expected_code"),
    [(5.0, 1), (1.0, 5), (0.5, 10)],
)
def test_range_code_maps_supported_ranges(range_v: float, expected_code: int) -> None:
    assert _range_code(range_v) == expected_code


def test_default_range_is_a_supported_range() -> None:
    assert _range_code(DEFAULT_RANGE_V) == 1


@pytest.mark.parametrize(
    ("range_v", "expected_message"),
    [
        (2.0, f"диапазон 2 В не поддерживается: {_RANGE_SUPPORTED}"),
        (0.1, f"диапазон 0.1 В не поддерживается: {_RANGE_SUPPORTED}"),
        (10.0, f"диапазон 10 В не поддерживается: {_RANGE_SUPPORTED}"),
        (0.0, f"диапазон 0 В не поддерживается: {_RANGE_SUPPORTED}"),
        (-5.0, f"диапазон -5 В не поддерживается: {_RANGE_SUPPORTED}"),
    ],
)
def test_range_code_rejects_unsupported_range(range_v: float, expected_message: str) -> None:
    with pytest.raises(InputError) as excinfo:
        _range_code(range_v)
    assert str(excinfo.value) == expected_message


# --- (c) снимки _default_setup и _ch1_meta ---------------------------------


@pytest.mark.parametrize(
    "session_type",
    [SessionType.MEASUREMENT, SessionType.CM_DM, SessionType.CM_DM_CALIBRATION],
)
def test_default_setup_snapshot_for_rc_shunt_session_types(session_type: SessionType) -> None:
    assert asdict(_default_setup(session_type)) == {
        "resistance_ohm": 100.0,
        "c1_f": 10e-9,
        "c2_f": 10e-9,
        "component_values_basis": ComponentValuesBasis.NOMINAL,
        "reference_assumption": ReferenceAssumption.FLOATING_HOST_UNVERIFIED,
    }


def test_default_setup_snapshot_for_self_noise() -> None:
    assert asdict(_default_setup(SessionType.SELF_NOISE)) == {
        "termination_resistance_ohm": 50.0,
    }


def test_default_setup_snapshot_for_line_quality() -> None:
    assert asdict(_default_setup(SessionType.LINE_QUALITY)) == {
        "nominal_primary_v": 230.0,
        "nominal_secondary_v": 6.0,
        "probe_multiplier": 10.0,
    }


def test_ch1_meta_snapshot_for_rc_shunt() -> None:
    assert asdict(_ch1_meta(_rc_shunt(), range_code=1)) == {
        "filename": "ch1.npy",
        "role": ChannelRole.HF_PROBE,
        "unit": "V",
        "front_end": "x2-probe 2x10nF+100R",
        "range_code": 1,
        "probe_multiplier": 1.0,
    }


def test_ch1_meta_snapshot_for_terminated_input() -> None:
    terminated = ScopeInputTerminated(termination_resistance_ohm=50.0)
    assert asdict(_ch1_meta(terminated, range_code=5)) == {
        "filename": "ch1.npy",
        "role": ChannelRole.HF_PROBE,
        "unit": "V",
        "front_end": "x2-probe 2x10nF+100R",
        "range_code": 5,
        "probe_multiplier": 1.0,
    }


def test_ch1_meta_snapshot_for_line_probe() -> None:
    assert asdict(_ch1_meta(_line_probe(), range_code=10)) == {
        "filename": "ch1.npy",
        "role": ChannelRole.LF_TRANSFORMER,
        "unit": "V",
        "front_end": "transformer 230:6",
        "range_code": 10,
        "probe_multiplier": 10.0,
    }


def test_capture_setup_rejects_setup_of_the_wrong_purpose() -> None:
    with pytest.raises(InputError) as excinfo:
        _capture_setup(session_type=SessionType.MEASUREMENT, setup=_line_probe())
    assert str(excinfo.value) == "ch1_setup не соответствует назначению capture-сессии"


@pytest.mark.parametrize(
    ("setup", "expected_multiplier"),
    [(_rc_shunt(), 1.0), (ScopeInputTerminated(termination_resistance_ohm=50.0), 1.0)],
)
def test_ch1_probe_multiplier_defaults_to_unity(
    setup: FloatingDifferentialRcShunt | ScopeInputTerminated,
    expected_multiplier: float,
) -> None:
    assert _ch1_probe_multiplier(setup) == expected_multiplier


def test_ch1_probe_multiplier_follows_the_line_probe() -> None:
    assert _ch1_probe_multiplier(_line_probe()) == 10.0


# --- (d) охрана: adc_calibration — единственный источник истины raw -> В ----


def _module_level_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_acquire_facade_never_imports_acquire_scale() -> None:
    imported = _imported_modules(_SRC / "acquire.py")
    assert not [module for module in imported if "acquire_scale" in module]


def test_acquire_scale_module_does_not_exist() -> None:
    assert not (_SRC / "acquire_scale.py").exists()


def test_no_acquire_module_imports_acquire_scale() -> None:
    offenders = {
        path.name: sorted(m for m in _imported_modules(path) if "acquire_scale" in m)
        for path in sorted(_SRC.glob("acquire*.py"))
    }
    assert not {name: mods for name, mods in offenders.items() if mods}


def test_no_acquire_module_redefines_raw_to_volts_scale() -> None:
    offenders = {
        path.name: sorted(_module_level_names(path) & _SCALE_NAMES)
        for path in sorted(_SRC.glob("acquire*.py"))
    }
    assert not {name: names for name, names in offenders.items() if names}


def test_adc_calibration_owns_the_raw_to_volts_scale() -> None:
    names = _module_level_names(_SRC / "adc_calibration.py")
    assert {"ADC_CENTER", "VOLTS_SCALE", "apply_adc_calibration"} <= names


def test_acquire_facade_exposes_no_scale_helper() -> None:
    assert not hasattr(acquire, "_scale_raw")


def test_range_table_has_a_single_owner_shared_by_the_facade() -> None:
    """Фасад отдаёт ту же таблицу, а не её копию: один источник истины."""
    assert acquire.RANGE_CODES is RANGE_CODES
