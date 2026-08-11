"""Строгий разбор необязательного synthetic_truth из manifest.json."""

import math
from collections.abc import Mapping
from typing import Final

from lnt.errors import InputError
from lnt.types import SyntheticTruth

TRUTH_FIELDS: Final = frozenset(
    field.name for field in SyntheticTruth.__dataclass_fields__.values()
)


def parse_synthetic_truth(value: Mapping[str, object] | None) -> SyntheticTruth | None:
    """Преобразует уже проверенный optional JSON-object в SyntheticTruth."""
    if value is None:
        return None
    unknown = sorted(set(value) - TRUTH_FIELDS)
    if unknown:
        names = ", ".join(repr(name) for name in unknown)
        raise InputError(f"manifest: synthetic_truth: неизвестные поля {names}")
    return SyntheticTruth(
        needle_mean_v=_required_float(value, "needle_mean_v"),
        needle_sigma_ratio=_required_float(value, "needle_sigma_ratio"),
        needle_jitter_us=_required_float(value, "needle_jitter_us"),
        ring_f0_hz=_required_float(value, "ring_f0_hz"),
        ring_q=_required_float(value, "ring_q"),
        async_rate_hz=_required_float(value, "async_rate_hz"),
        lf_envelope_cv=_required_float(value, "lf_envelope_cv"),
    )


def _required_float(value: Mapping[str, object], key: str) -> float:
    if key not in value:
        raise InputError(f"manifest: отсутствует поле {key!r}")
    raw = value[key]
    if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw):
        raise InputError(f"manifest: поле {key!r} должно быть конечным числом")
    return float(raw)
