"""Характеризация фасада ``lnt._manifest_schema`` перед расслоением (очередь C4).

Refactor-исключение из TDD: перенос хелперов в листья
(``_manifest_primitives`` / ``_manifest_parse`` / ``_manifest_serialize``)
не добавляет поведения, поэтому вместо «красного» теста здесь пиновка
ТЕКУЩЕГО контракта. Набор обязан быть зелёным и ДО, и ПОСЛЕ переноса:
любое расхождение = регрессия механического движения кода.

Пинуется ровно то, что потребляют машины:
1. round-trip каждого замороженного golden-манифеста
   (``manifest_from_mapping`` -> ``manifest_to_mapping``) с побайтовым
   сравнением канонического JSON и порядка ключей;
2. round-trip inline-фикстур (v1 minimal/full, v2 measurement/self_noise/line_quality),
   включая повторный проход через JSON-границу (JSON round-trip idempotency / 2nd boundary);
3. явная фиксация порядка ключей сериализации верхнего уровня;
4. ТОЧНАЯ строка сообщения ``InputError`` для каждого битого входа —
   текст ``_req_*`` / ``_reject_unknown_fields`` / ``_validate_*`` и есть
   контракт границы;
5. проверки сериализации: отклонение schema_v1 c ch1_setup, schema_v2 без ch1_setup,
   несоответствие session_type и ch1_setup, небезопасный session_id;
6. поверхность реэкспорта фасада (имена и значения констант).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Final, cast

import pytest

from lnt import _manifest_schema
from lnt._manifest_schema import manifest_from_mapping, manifest_to_mapping
from lnt.errors import InputError
from lnt.types import SessionType

FIXTURE_ROOT: Final = Path(__file__).parent / "fixtures" / "manifest_frozen"
V1: Final = "schema_v1_synthetic_legacy.json"
V2: Final = "schema_v2_hardware_floating_rc.json"
V2_TRANSFORMER: Final = "schema_v2_hardware_transformer.json"
V3_UNSUPPORTED: Final = "invalid_schema_v3.json"
V2_UNKNOWN_FIELD: Final = "invalid_v2_unknown_field.json"

GOLDEN_MANIFESTS: Final = (V1, V2, V2_TRANSFORMER)

MalformedBuilder = Callable[[], Mapping[str, object]]

_TOP_LEVEL_KEY_ORDER: Final = (
    "schema_version",
    "session_id",
    "created_utc",
    "completed_utc",
    "source",
    "session_type",
    "sample_rate_hz",
    "duration_s",
    "sample_count",
    "line_frequency_hz",
    "profile",
    "baseline_session",
    "parameters",
    "ch1",
    "ch2",
    "acquisition_telemetry",
    "synthetic_truth",
)


def _load(name: str) -> dict[str, object]:
    raw = (FIXTURE_ROOT / name).read_text(encoding="utf-8")
    return cast("dict[str, object]", json.loads(raw))


def _canonical(payload: object) -> str:
    """Каноническая форма JSON: сравнение содержимого побайтово."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _patched(name: str, patch: Mapping[str, object]) -> dict[str, object]:
    mapping = _load(name)
    mapping.update(patch)
    return mapping


def _patched_child(name: str, parent: str, patch: Mapping[str, object]) -> dict[str, object]:
    mapping = _load(name)
    cast("dict[str, object]", mapping[parent]).update(patch)
    return mapping


def _dropped(name: str, key: str) -> dict[str, object]:
    mapping = _load(name)
    del mapping[key]
    return mapping


def _channel(*, filename: str, role: str, front_end: str) -> dict[str, object]:
    return {
        "filename": filename,
        "role": role,
        "unit": "V",
        "front_end": front_end,
        "range_code": 1,
        "probe_multiplier": 1.0,
    }


def _telemetry(**changes: object) -> dict[str, object]:
    telemetry: dict[str, object] = {
        "requested_samples": 19_200_000,
        "captured_samples": 19_199_000,
        "callback_count": 3,
        "block_lengths": [8192, 8192, 4096],
        "callback_gaps_s": [0.001, 0.0015],
        "expected_block_interval_s": 0.001,
        "short_block_count": 1,
        "ch1_clip_low_count": 0,
        "ch1_clip_high_count": 2,
        "ch2_clip_low_count": 0,
        "ch2_clip_high_count": 0,
        "calibration_used": True,
    }
    telemetry.update(changes)
    return telemetry


def _truth() -> dict[str, object]:
    return {
        "needle_mean_v": 0.25,
        "needle_sigma_ratio": 0.1,
        "needle_jitter_us": 3.5,
        "ring_f0_hz": 120000.0,
        "ring_q": 4.0,
        "async_rate_hz": 733.0,
        "lf_envelope_cv": 0.05,
    }


def _v1_inline(**changes: object) -> dict[str, object]:
    mapping: dict[str, object] = {
        "schema_version": 1,
        "session_id": "char-v1",
        "created_utc": "2026-08-04T00:00:00Z",
        "completed_utc": "2026-08-04T00:00:02Z",
        "source": "synthetic",
        "session_type": "measurement",
        "sample_rate_hz": 8_000_000.0,
        "duration_s": 2.4,
        "sample_count": 19_200_000,
        "line_frequency_hz": 50.0,
        "profile": None,
        "baseline_session": None,
        "parameters": {},
        "ch1": _channel(filename="ch1.npy", role="hf_probe", front_end="x2-probe 2x10nF+100R"),
        "ch2": None,
        "acquisition_telemetry": None,
        "synthetic_truth": None,
    }
    mapping.update(changes)
    return mapping


def _v1_full_inline() -> dict[str, object]:
    return _v1_inline(
        session_id="char-v1-002",
        profile="quiet",
        baseline_session="char-baseline",
        parameters={
            "label": "qa",
            "seed": 7,
            "series_index": 2,
            "series_total": 3,
            "series_interval_s": 60.0,
        },
        ch2=_channel(filename="ch2.npy", role="lf_transformer", front_end="transformer 230:6"),
        acquisition_telemetry=_telemetry(),
        synthetic_truth=_truth(),
    )


def _v2_inline(*, session_type: str, setup: dict[str, object]) -> dict[str, object]:
    mapping = _v1_inline(
        schema_version=2,
        session_id=f"char-v2-{session_type}",
        session_type=session_type,
    )
    mapping["ch1_setup"] = setup
    return mapping


def _v2_measurement_inline() -> dict[str, object]:
    return _v2_inline(
        session_type="measurement",
        setup={
            "kind": "floating_differential_rc_shunt_v1",
            "resistance_ohm": 100.0,
            "c1_f": 1e-08,
            "c2_f": 1e-08,
            "component_values_basis": "nominal",
            "reference_assumption": "floating_host_unverified",
        },
    )


def _v2_self_noise_inline() -> dict[str, object]:
    return _v2_inline(
        session_type="self_noise",
        setup={"kind": "scope_input_terminated_v1", "termination_resistance_ohm": 50.0},
    )


def _v2_line_quality_inline() -> dict[str, object]:
    return _v2_inline(
        session_type="line_quality",
        setup={
            "kind": "transformer_line_probe_v1",
            "nominal_primary_v": 230.0,
            "nominal_secondary_v": 6.0,
            "probe_multiplier": 1.0,
        },
    )


_INLINE_ROUND_TRIP_FIXTURES: Final = (
    pytest.param(_v1_inline(), id="v1-minimal"),
    pytest.param(_v1_full_inline(), id="v1-full"),
    pytest.param(_v2_measurement_inline(), id="v2-measurement"),
    pytest.param(_v2_self_noise_inline(), id="v2-self-noise"),
    pytest.param(_v2_line_quality_inline(), id="v2-line-quality"),
)


def _dumps_inline(mapping: Mapping[str, object]) -> str:
    return json.dumps(mapping, ensure_ascii=False, sort_keys=False, separators=(",", ":"))


@pytest.mark.parametrize("name", GOLDEN_MANIFESTS)
def test_golden_manifest_round_trips_to_byte_identical_json(name: str) -> None:
    # Given: замороженный на диске golden-манифест.
    original = _load(name)

    # When: он пересекает типизированную границу в обе стороны.
    serialized = manifest_to_mapping(manifest_from_mapping(original))

    # Then: содержимое и порядок ключей воспроизводятся побайтово.
    assert _canonical(serialized) == _canonical(original)
    assert list(serialized) == list(original)


@pytest.mark.parametrize("name", GOLDEN_MANIFESTS)
def test_golden_manifest_round_trip_is_idempotent_on_second_pass(name: str) -> None:
    # Given: манифест, уже прошедший один round-trip.
    once = manifest_to_mapping(manifest_from_mapping(_load(name)))

    # When: результат снова разбирается и сериализуется.
    twice = manifest_to_mapping(manifest_from_mapping(json.loads(json.dumps(once))))

    # Then: вторая итерация ничего не меняет.
    assert _canonical(twice) == _canonical(once)


@pytest.mark.parametrize("mapping", _INLINE_ROUND_TRIP_FIXTURES)
def test_inline_manifest_round_trips_to_byte_identical_json(mapping: dict[str, object]) -> None:
    # Given: inline-манифест.
    # When: сериализуется через границу.
    serialized = manifest_to_mapping(manifest_from_mapping(deepcopy(mapping)))

    # Then: компактный JSON совпадает побайтово.
    assert _dumps_inline(serialized) == _dumps_inline(mapping)


@pytest.mark.parametrize("mapping", _INLINE_ROUND_TRIP_FIXTURES)
def test_inline_manifest_round_trip_survives_second_json_boundary(
    mapping: dict[str, object],
) -> None:
    # Given: inline-манифест, разобранный в типизированный объект.
    manifest = manifest_from_mapping(deepcopy(mapping))

    # When: объект сериализуется в JSON-строку и восстанавливается через loads.
    restored = manifest_from_mapping(json.loads(json.dumps(manifest_to_mapping(manifest))))

    # Then: восстановленный манифест эквивалентен исходному.
    assert restored == manifest


@pytest.mark.parametrize("name", GOLDEN_MANIFESTS)
def test_serialized_key_order_is_pinned_for_golden_manifests(name: str) -> None:
    # Given: golden-манифест.
    original = _load(name)

    # When: сериализуется в mapping.
    serialized = manifest_to_mapping(manifest_from_mapping(original))

    # Then: порядок ключей строго зафиксирован.
    expected = _TOP_LEVEL_KEY_ORDER
    if "ch1_setup" in original:
        expected = (*_TOP_LEVEL_KEY_ORDER, "ch1_setup")
    assert tuple(serialized) == expected


@pytest.mark.parametrize("mapping", _INLINE_ROUND_TRIP_FIXTURES)
def test_serialized_key_order_is_pinned_for_inline_manifests(mapping: dict[str, object]) -> None:
    # Given: inline-манифест.
    # When: сериализуется в mapping.
    serialized = manifest_to_mapping(manifest_from_mapping(deepcopy(mapping)))

    # Then: порядок ключей строго зафиксирован.
    expected = _TOP_LEVEL_KEY_ORDER
    if "ch1_setup" in mapping:
        expected = (*_TOP_LEVEL_KEY_ORDER, "ch1_setup")
    assert tuple(serialized) == expected


MALFORMED_CASES: Final[tuple[tuple[MalformedBuilder, str, str], ...]] = (
    (
        lambda: _patched(V1, {"schema_version": "1"}),
        "manifest: поле 'schema_version' должно быть целым числом",
        "schema_version_not_int",
    ),
    (
        lambda: _load(V3_UNSUPPORTED),
        "manifest: неподдерживаемая schema_version: 3",
        "schema_version_unsupported",
    ),
    (
        lambda: _patched(V1, {"schema_version": 7}),
        "manifest: неподдерживаемая schema_version: 7",
        "schema_version_unsupported_v7",
    ),
    (
        lambda: _patched(V1, {"unexpected": 1}),
        "manifest: неизвестные поля 'unexpected'",
        "manifest_unknown_field",
    ),
    (
        lambda: _load(V2_UNKNOWN_FIELD),
        "manifest: неизвестные поля 'context'",
        "manifest_unknown_field_v2_frozen",
    ),
    (
        lambda: _dropped(V1, "session_id"),
        "manifest: отсутствует поле 'session_id'",
        "req_missing",
    ),
    (
        lambda: _dropped(V1, "ch2"),
        "manifest: отсутствует поле 'ch2'",
        "req_missing_nullable",
    ),
    (
        lambda: _patched(V1, {"session_id": 1}),
        "manifest: поле 'session_id' должно быть строкой",
        "req_str",
    ),
    (
        lambda: _patched(V1, {"created_utc": 5}),
        "manifest: поле 'created_utc' должно быть строкой",
        "req_str_created_utc",
    ),
    (
        lambda: _patched(V1, {"profile": 1}),
        "manifest: поле 'profile' должно быть строкой или null",
        "opt_str",
    ),
    (
        lambda: _patched(V1, {"sample_count": True}),
        "manifest: поле 'sample_count' должно быть целым числом",
        "req_int_rejects_bool",
    ),
    (
        lambda: _patched(V1, {"duration_s": "x"}),
        "manifest: поле 'duration_s' должно быть числом",
        "req_float",
    ),
    (
        lambda: _patched(V1, {"duration_s": float("inf")}),
        "manifest: поле 'duration_s' должно быть конечным числом",
        "req_float_nonfinite",
    ),
    (
        lambda: _patched(V1, {"duration_s": float("nan")}),
        "manifest: поле 'duration_s' должно быть конечным числом",
        "req_float_nan",
    ),
    (
        lambda: _patched(V1, {"source": "ghost"}),
        "manifest: недопустимое значение поля 'source': 'ghost'",
        "req_enum",
    ),
    (
        lambda: _patched(V1, {"ch1": []}),
        "manifest: поле 'ch1' должно быть JSON-object",
        "req_object",
    ),
    (
        lambda: _patched(V1, {"ch1": 5}),
        "manifest: поле 'ch1' должно быть JSON-object",
        "req_object_ch1_scalar",
    ),
    (
        lambda: _patched(V1, {"parameters": []}),
        "manifest: поле 'parameters' должно быть JSON-object",
        "req_object_parameters",
    ),
    (
        lambda: _patched(V1, {"synthetic_truth": 5}),
        "manifest: поле 'synthetic_truth' должно быть JSON-object",
        "opt_object",
    ),
    (
        lambda: _patched(V2, {"ch1_setup": 5}),
        "manifest: поле 'ch1_setup' должно быть JSON-object",
        "opt_object_ch1_setup",
    ),
    (
        lambda: _patched_child(V2, "acquisition_telemetry", {"extra": 1}),
        "acquisition_telemetry: неизвестные поля 'extra'",
        "telemetry_unknown_field",
    ),
    (
        lambda: _patched_child(V1, "ch1", {"extra": 1}),
        "ch1: неизвестные поля 'extra'",
        "channel_unknown_field",
    ),
    (
        lambda: _patched_child(V1, "ch1", {"role": "bogus"}),
        "manifest: недопустимое значение поля 'role': 'bogus'",
        "channel_bad_role",
    ),
    (
        lambda: _patched_child(V2, "acquisition_telemetry", {"calibration_used": 1}),
        "manifest: поле 'calibration_used' должно быть булевым",
        "req_bool",
    ),
    (
        lambda: _patched_child(V2, "acquisition_telemetry", {"block_lengths": "x"}),
        "manifest: поле 'block_lengths' должно быть списком",
        "req_int_tuple_not_list",
    ),
    (
        lambda: _patched_child(V2, "acquisition_telemetry", {"block_lengths": 8192}),
        "manifest: поле 'block_lengths' должно быть списком",
        "req_int_tuple_scalar",
    ),
    (
        lambda: _patched_child(V2, "acquisition_telemetry", {"block_lengths": [1.5]}),
        "manifest: элементы 'block_lengths' должны быть целыми числами",
        "req_int_tuple_bad_item",
    ),
    (
        lambda: _patched_child(V2, "acquisition_telemetry", {"block_lengths": [1, True]}),
        "manifest: элементы 'block_lengths' должны быть целыми числами",
        "req_int_tuple_bool_item",
    ),
    (
        lambda: _patched_child(V2, "acquisition_telemetry", {"callback_gaps_s": 0}),
        "manifest: поле 'callback_gaps_s' должно быть списком",
        "req_float_tuple_not_list",
    ),
    (
        lambda: _patched_child(V2, "acquisition_telemetry", {"callback_gaps_s": [float("nan")]}),
        "manifest: элементы 'callback_gaps_s' должны быть конечными числами",
        "req_float_tuple_bad_item",
    ),
    (
        lambda: _patched_child(V2, "acquisition_telemetry", {"callback_gaps_s": [float("inf")]}),
        "manifest: элементы 'callback_gaps_s' должны быть конечными числами",
        "req_float_tuple_inf_item",
    ),
    (
        lambda: _dropped(V2, "ch1_setup"),
        "manifest: отсутствует поле 'ch1_setup'",
        "v2_ch1_setup_absent",
    ),
    (
        lambda: _patched(V2, {"ch1_setup": None}),
        "manifest: schema v2 требует ch1_setup",
        "v2_requires_ch1_setup",
    ),
    (
        lambda: _patched(
            V2,
            {
                "session_type": "self_noise",
                "ch1_setup": {
                    "kind": "floating_differential_rc_shunt_v1",
                    "resistance_ohm": 100.0,
                    "c1_f": 1e-08,
                    "c2_f": 1e-08,
                    "component_values_basis": "nominal",
                    "reference_assumption": "floating_host_unverified",
                },
            },
        ),
        "manifest: schema v2 session_type не соответствует ch1_setup",
        "v2_session_setup_pairing_mismatch",
    ),
    (
        lambda: _patched(V1, {"session_id": "bad id"}),
        "manifest: небезопасный session_id",
        "unsafe_session_id",
    ),
    (
        lambda: _patched(V1, {"parameters": {"seed": -1}}),
        "manifest: parameters['seed'] должен быть неотрицательным целым",
        "seed_negative",
    ),
    (
        lambda: _patched(V1, {"parameters": {"label": " x"}}),
        "manifest: parameters['label'] должен быть непустой меткой без отступов",
        "label_padded_left",
    ),
    (
        lambda: _patched(V1, {"parameters": {"label": " qa "}}),
        "manifest: parameters['label'] должен быть непустой меткой без отступов",
        "label_padded_both",
    ),
    (
        lambda: _patched(V1, {"parameters": {"series_index": 1}}),
        "manifest: параметры series_index/series_total/series_interval_s обязательны вместе",
        "series_partial",
    ),
    (
        lambda: _patched(
            V1,
            {"parameters": {"series_index": 0, "series_total": 2, "series_interval_s": 1.0}},
        ),
        "manifest: series_index/series_total: неверный размер или индекс",
        "series_bad_index_zero",
    ),
    (
        lambda: _patched(
            V1,
            {"parameters": {"series_index": 1, "series_total": 1, "series_interval_s": 1.0}},
        ),
        "manifest: series_index/series_total: неверный размер или индекс",
        "series_bad_total_one",
    ),
    (
        lambda: _patched(
            V1,
            {"parameters": {"series_index": 1, "series_total": 2, "series_interval_s": -1.0}},
        ),
        "manifest: series_interval_s должен быть конечным и неотрицательным",
        "series_negative_interval",
    ),
    (
        lambda: _patched(
            V1,
            {"parameters": {"series_index": 1, "series_total": 2, "series_interval_s": 1.0}},
        ),
        "manifest: session_id не соответствует series_index",
        "series_session_id_mismatch",
    ),
    (
        lambda: _patched(V1, {"parameters": {"flag": True}}),
        "manifest: параметры должны быть числами или строками: 'flag'",
        "parameter_bool",
    ),
    (
        lambda: _patched(V1, {"parameters": {"bad": [1]}}),
        "manifest: параметры должны быть числами или строками: 'bad'",
        "parameter_list",
    ),
    (
        lambda: _patched(V1, {"parameters": {"ratio": float("nan")}}),
        "manifest: параметры должны быть конечными числами: 'ratio'",
        "parameter_nan",
    ),
    (
        lambda: _patched(V1, {"parameters": {"bad": float("inf")}}),
        "manifest: параметры должны быть конечными числами: 'bad'",
        "parameter_inf",
    ),
)


@pytest.mark.parametrize(
    ("build", "expected"),
    [pytest.param(build, expected, id=case_id) for build, expected, case_id in MALFORMED_CASES],
)
def test_malformed_manifest_raises_exact_input_error_message(
    build: MalformedBuilder,
    expected: str,
) -> None:
    # Given: манифест с единственным нарушением контракта.
    mapping = build()

    # When: он проходит строгий разбор границы.
    with pytest.raises(InputError) as error:
        manifest_from_mapping(mapping)

    # Then: сообщение совпадает посимвольно — текст и есть контракт.
    assert str(error.value) == expected


def test_serialize_rejects_schema_v1_object_carrying_ch1_setup() -> None:
    # Given: v2-манифест, которому в памяти понизили schema_version.
    downgraded = replace(manifest_from_mapping(_load(V2)), schema_version=1)

    # When: объект сериализуется обратно в mapping.
    with pytest.raises(InputError) as error:
        manifest_to_mapping(downgraded)

    # Then: граница записи отвергает пару v1 + ch1_setup тем же текстом.
    assert str(error.value) == "manifest: schema v1 не допускает ch1_setup"


def test_serialize_rejects_schema_v2_without_ch1_setup() -> None:
    # Given: v2-манифест, у которого убран ch1_setup.
    manifest = manifest_from_mapping(_load(V2))

    # When: объект сериализуется.
    with pytest.raises(InputError) as error:
        manifest_to_mapping(replace(manifest, ch1_setup=None))

    # Then: сериализация отвергает v2 без ch1_setup.
    assert str(error.value) == "manifest: schema v2 требует ch1_setup"


def test_serialize_rejects_contradictory_session_setup_pairing() -> None:
    # Given: v2-манифест с несоответствующим типом сессии.
    manifest = manifest_from_mapping(_load(V2))

    # When: объект сериализуется.
    with pytest.raises(InputError) as error:
        manifest_to_mapping(replace(manifest, session_type=SessionType.SELF_NOISE))

    # Then: сериализация отвергает несовместимую пару session_type и ch1_setup.
    assert str(error.value) == "manifest: schema v2 session_type не соответствует ch1_setup"


def test_serialize_rejects_unsafe_session_id_mutated_in_memory() -> None:
    # Given: валидный v1-манифест с испорченным в памяти session_id.
    mutated = replace(manifest_from_mapping(_load(V1)), session_id="bad id")

    # When: объект сериализуется.
    with pytest.raises(InputError) as error:
        manifest_to_mapping(mutated)

    # Then: та же валидация работает на записи, а не только на чтении.
    assert str(error.value) == "manifest: небезопасный session_id"


PUBLIC_NAMES: Final = (
    "CH1_MANIFEST_FIELDS",
    "CHANNEL_FIELDS",
    "MANIFEST_FIELDS",
    "MIN_SERIES_TOTAL",
    "SERIES_FIELDS",
    "SESSION_ID_PATTERN",
    "TELEMETRY_FIELDS",
    "manifest_from_mapping",
    "manifest_to_mapping",
)
HELPER_NAMES: Final = (
    "_is_valid_label",
    "_opt_object",
    "_opt_str",
    "_parse_channel",
    "_parse_parameters",
    "_parse_telemetry",
    "_reject_unknown_fields",
    "_req",
    "_req_bool",
    "_req_enum",
    "_req_float",
    "_req_float_tuple",
    "_req_int",
    "_req_int_tuple",
    "_req_object",
    "_req_str",
    "_serialize_channel",
    "_serialize_telemetry",
    "_serialize_truth",
    "_validate_manifest",
    "_validate_parameters",
)


@pytest.mark.parametrize("name", [*PUBLIC_NAMES, *HELPER_NAMES])
def test_facade_keeps_every_name_importable(name: str) -> None:
    # Given/When: имя запрашивается у фасада.
    # Then: поверхность модуля не сузилась после расслоения.
    assert hasattr(_manifest_schema, name), f"фасад потерял имя {name!r}"


def test_facade_constants_keep_their_exact_values() -> None:
    # Given/When: константы читаются из фасада.
    # Then: множества полей совпадают со схемой v1/v2 дословно.
    min_series_total = _manifest_schema.MIN_SERIES_TOTAL
    series_fields = _manifest_schema.SERIES_FIELDS
    channel_fields = _manifest_schema.CHANNEL_FIELDS
    telemetry_fields = _manifest_schema.TELEMETRY_FIELDS
    manifest_fields = _manifest_schema.MANIFEST_FIELDS
    ch1_manifest_fields = _manifest_schema.CH1_MANIFEST_FIELDS
    session_id_pattern = _manifest_schema.SESSION_ID_PATTERN

    assert min_series_total == 2
    assert series_fields == frozenset({"series_index", "series_total", "series_interval_s"})
    assert channel_fields == frozenset(
        {"filename", "role", "unit", "front_end", "range_code", "probe_multiplier"},
    )
    assert ch1_manifest_fields == manifest_fields | {"ch1_setup"}
    assert "ch1_setup" not in manifest_fields
    assert "calibration_used" in telemetry_fields
    assert len(telemetry_fields) == 12
    assert session_id_pattern.pattern == r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
