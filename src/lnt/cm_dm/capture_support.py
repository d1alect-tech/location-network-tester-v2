"""T5: подготовка probe-pair параметров манифеста захвата (WARN-семантика).

Отсутствие или непригодность калибровки пары пробников НЕ останавливает
захват: в ``parameters`` пишется только тег ``probe_pair``, а machine-readable
причина доступна в :class:`PreparedProbePairCapture`; анализ позднее отчётит
статус ``unavailable``. Пригодная калибровка публикует ровно четыре
JSON-скаляра: тег, коррекция CH2, отношение усиления и глубина подавления.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from lnt.cm_dm.calibration import (
    ResolvedProbePairCalibration,
    UnavailableProbePairCalibration,
    resolve_probe_pair_calibration,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from lnt.types import SessionManifest

PARAM_PROBE_PAIR: Final = "probe_pair"
PARAM_CORRECTION_FACTOR: Final = "probe_pair_correction_factor"
PARAM_GAIN_RATIO: Final = "probe_pair_gain_ratio"
PARAM_REJECTION_DEPTH_DB: Final = "probe_pair_rejection_depth_db"
PROBE_PAIR_TAG: Final = "cm_dm"


@dataclass(frozen=True, slots=True, kw_only=True)
class PreparedProbePairCapture:
    """Параметры probe-pair для манифеста плюс причина недоступности."""

    available: bool
    reason_code: str | None
    parameters: Mapping[str, str | float]


def prepare_probe_pair_capture(
    sessions_root: Path,
    calibration_ref: str | None,
    measurement_manifest: SessionManifest,
) -> PreparedProbePairCapture:
    """Делегирует резолверу калибровки и собирает JSON-скаляры parameters."""
    resolution = resolve_probe_pair_calibration(
        sessions_root,
        calibration_ref,
        measurement_manifest,
    )
    match resolution:
        case ResolvedProbePairCalibration(
            correction_factor=correction_factor,
            gain_ratio_epsilon=gain_ratio_epsilon,
            rejection_depth_db=rejection_depth_db,
        ):
            return PreparedProbePairCapture(
                available=True,
                reason_code=None,
                parameters={
                    PARAM_PROBE_PAIR: PROBE_PAIR_TAG,
                    PARAM_CORRECTION_FACTOR: correction_factor,
                    PARAM_GAIN_RATIO: gain_ratio_epsilon,
                    PARAM_REJECTION_DEPTH_DB: rejection_depth_db,
                },
            )
        case UnavailableProbePairCalibration(reason_code=reason_code):
            return PreparedProbePairCapture(
                available=False,
                reason_code=reason_code,
                parameters={PARAM_PROBE_PAIR: PROBE_PAIR_TAG},
            )
