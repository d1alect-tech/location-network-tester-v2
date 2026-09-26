"""F18: приведение записи к объявленной частоте анализа целым фактором."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
from scipy import signal

from lnt.characterization.f18_contract import analysis_factor_for

if TYPE_CHECKING:
    from lnt.characterization.phase_model import PhaseCycles

__all__ = ["decimate_to_analysis_rate"]


def decimate_to_analysis_rate(
    samples: np.ndarray, phase: PhaseCycles
) -> tuple[np.ndarray, PhaseCycles, int]:
    """Привести запись и корень фазы к объявленной частоте анализа.

    Частота ЗАХВАТА читается первой и до любой перепривязки: фактор, выведенный из
    уже приведённой ``phase.sample_rate_hz``, молча дал бы 1, а сегмент вышел бы
    в 8 раз короче объявленной длительности — неверный ответ без ошибки. Корень
    перепривязывается ровно так же, как :func:`rebase_phase_cycles`: границы циклов
    делятся на фактор, а ``sample_count`` берётся из ФАКТИЧЕСКОГО размера отсчётов,
    потому что длина после ``scipy.signal.decimate`` равна ceil(n / q), а не n / q.
    """
    original_rate = phase.sample_rate_hz
    factor = analysis_factor_for(original_rate)
    if factor <= 1:
        return samples, phase, 1
    values = signal.decimate(np.asarray(samples), factor, zero_phase=True)
    analysis_rate = original_rate / factor
    rebased = replace(
        phase,
        sample_rate_hz=analysis_rate,
        sample_count=int(values.size),
        cycle_start_samples=np.floor(phase.cycle_start_samples / factor),
        cycle_end_samples=np.floor(phase.cycle_end_samples / factor),
    )
    return values, rebased, factor
