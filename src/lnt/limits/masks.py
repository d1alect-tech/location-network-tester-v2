"""Пользовательские limit-маски B4: хранение вне сессии и честные вердикты.

Маски живут в отдельном ``limits.json`` каталога конфигурации пользователя
(или рецепта), никогда — в ``manifest.json`` сессии. Оценка — верхняя
лимит-линия с линейной интерполяцией; вне домена маски и при нехватке
данных вердикт ``unavailable``, никогда не фабрикуется.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

import numpy as np

from lnt.errors import InputError

if TYPE_CHECKING:
    from numpy.typing import NDArray

LIMITS_SCHEMA_VERSION: Final = 1
type MaskVerdict = Literal["pass", "fail", "unavailable"]
_MIN_SPC_SAMPLES: Final = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class LimitPoint:
    """Одна точка верхней лимит-линии (x — частота/время, y — допуск)."""

    x: float
    y: float

    def __post_init__(self) -> None:
        """Проверяет конечность координат точки."""
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise InputError("маски: координаты точки должны быть конечными")


@dataclass(frozen=True, slots=True, kw_only=True)
class LimitMask:
    """Именованная верхняя лимит-линия с строго растущими абсциссами."""

    name: str
    unit: str
    points: tuple[LimitPoint, ...]

    def __post_init__(self) -> None:
        """Проверяет имя, единицу и строгий рост абсцисс."""
        if not self.name or not self.unit:
            raise InputError("маски: имя и единица должны быть непустыми")
        for first, second in pairwise(self.points):
            if not second.x > first.x:
                raise InputError("маски: абсциссы точек должны строго расти")

    def to_dict(self) -> dict[str, object]:
        """Сериализует маску в JSON-безопасное отображение."""
        return {
            "name": self.name,
            "unit": self.unit,
            "points": [{"x": point.x, "y": point.y} for point in self.points],
        }

    @classmethod
    def from_dict(cls, value: object) -> LimitMask:
        """Строго разбирает маску; при сомнениях — InputError, не догадки."""
        if not isinstance(value, dict):
            raise InputError("маски: маска должна быть JSON-object")
        name, unit, raw_points = value.get("name"), value.get("unit"), value.get("points")
        if not isinstance(name, str) or not name:
            raise InputError("маски: поле 'name' должно быть непустой строкой")
        if not isinstance(unit, str) or not unit:
            raise InputError("маски: поле 'unit' должно быть непустой строкой")
        if not isinstance(raw_points, list):
            raise InputError("маски: поле 'points' должно быть массивом")
        points: list[LimitPoint] = []
        for item in raw_points:
            if not isinstance(item, dict):
                raise InputError("маски: точка должна быть JSON-object")
            raw_x, raw_y = item.get("x"), item.get("y")
            if (
                not isinstance(raw_x, int | float)
                or isinstance(raw_x, bool)
                or not isinstance(raw_y, int | float)
                or isinstance(raw_y, bool)
            ):
                raise InputError("маски: координаты точки должны быть числами")
            points.append(LimitPoint(x=float(raw_x), y=float(raw_y)))
        return cls(name=name, unit=unit, points=tuple(points))


def _interpolated_limit(mask: LimitMask, x: float) -> float | None:
    """Линейно интерполирует лимит; вне домена — None (без экстраполяции)."""
    points = mask.points
    if not points:
        return None
    if x < points[0].x or x > points[-1].x:
        return None
    for left, right in pairwise(points):
        if left.x <= x <= right.x:
            span = right.x - left.x
            if span <= 0.0:
                return left.y
            fraction = (x - left.x) / span
            return left.y + fraction * (right.y - left.y)
    return points[-1].y if x == points[-1].x else None


def evaluate_mask(x: float, value: float, mask: LimitMask) -> MaskVerdict:
    """Оценивает значение против верхней лимит-линии маски."""
    if not math.isfinite(x) or not math.isfinite(value):
        return "unavailable"
    limit = _interpolated_limit(mask, x)
    if limit is None or not math.isfinite(limit):
        return "unavailable"
    return "pass" if value <= limit else "fail"


def spc_verdict(value: float, *, center: float, sigma: float, k: float = 3.0) -> MaskVerdict:
    """SPC-вердикт поверх CUSUM: |value-center| против k*sigma."""
    if not math.isfinite(value) or not math.isfinite(center):
        return "unavailable"
    if not math.isfinite(sigma) or sigma <= 0.0:
        return "unavailable"
    if not math.isfinite(k) or k <= 0.0:
        return "unavailable"
    return "pass" if abs(value - center) <= k * sigma else "fail"


def spc_limits(
    values: NDArray[np.floating], *, k: float = 3.0
) -> tuple[float, float, float, float] | None:
    """Считает (center, sigma, ucl, lcl); при нехватке данных — None."""
    if not math.isfinite(k) or k <= 0.0:
        return None
    series = np.asarray(values, dtype=np.float64)
    if series.ndim != 1 or series.size < _MIN_SPC_SAMPLES or not np.all(np.isfinite(series)):
        return None
    center = float(np.mean(series))
    sigma = float(np.std(series))
    if not math.isfinite(center) or not math.isfinite(sigma) or sigma <= 0.0:
        return None
    return (center, sigma, center + k * sigma, center - k * sigma)


def thd_limit_verdict(
    mean_thd: float | None, *, limit: float, cycles_analyzed: int, min_cycles: int = 100
) -> MaskVerdict:
    """THD-вердикт с честным unavailable вместо фабрикации при нехватке данных."""
    if mean_thd is None or not math.isfinite(mean_thd):
        return "unavailable"
    if not math.isfinite(limit) or limit <= 0.0:
        return "unavailable"
    if cycles_analyzed < min_cycles:
        return "unavailable"
    return "pass" if mean_thd <= limit else "fail"


def save_masks(path: Path | str, masks: tuple[LimitMask, ...]) -> Path:
    """Атомарно пишет masks в limits.json каталога конфигурации (не сессии)."""
    target = Path(path)
    payload = {
        "schema_version": LIMITS_SCHEMA_VERSION,
        "masks": [mask.to_dict() for mask in masks],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.partial")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    return target


def load_masks(path: Path | str) -> tuple[LimitMask, ...]:
    """Читает masks из limits.json; отсутствие файла — пустой кортеж."""
    target = Path(path)
    if not target.exists():
        return ()
    try:
        raw: object = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"маски: limits.json не читается: {exc}") from exc
    if not isinstance(raw, dict):
        raise InputError("маски: корень limits.json должен быть JSON-object")
    if raw.get("schema_version") != LIMITS_SCHEMA_VERSION:
        raise InputError("маски: неподдерживаемая версия схемы limits.json")
    items = raw.get("masks")
    if not isinstance(items, list):
        raise InputError("маски: поле 'masks' должно быть массивом")
    return tuple(LimitMask.from_dict(item) for item in items)
