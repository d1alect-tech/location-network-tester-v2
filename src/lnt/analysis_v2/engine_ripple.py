"""Ripple-срез анализа v2: оркестрация QC, метрик и полосного RMS.

Граница v1/v2 (AGENTS.md): движок v2 только оркестрирует готовые науки v1 —
метрики ``lnt.ripple.metrics`` (todo 1), модель адаптера ``lnt.ripple.adapter``
(todo 2), Welch ``lnt.psd.engine.compute_welch`` с mean-детектором. Математика
не дублируется; результат пишется производным сайдкаром ``ripple.json``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .ripple_baseline import (
    REASON_BASELINE_RESULT,
    REASON_DURATION,
    REASON_MEASUREMENT_RESULT,
    baseline_identity_reasons,
    baseline_payload_block,
    load_baseline_session,
)
from .ripple_blocks import SessionBlocks, session_blocks
from .ripple_measurements import band_unavailable, spectrum_unavailable, unavailable_scalars
from .ripple_options import RippleOptions, RippleRequest, validated_options
from .ripple_qc import SpanQc, span_qc
from .ripple_result import (
    adapter_block,
    algorithm_block,
    options_block,
    provenance_block,
    qc_block,
    selection_block,
    session_block,
)
from .ripple_write import session_input_hashes, write_ripple_sidecar

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True, kw_only=True)
class RippleSidecar:
    """Опубликованный сайдкар: путь и нормализованный payload v1."""

    session_dir: Path
    sidecar_path: Path
    payload: dict[str, object]


def run_ripple(request: RippleRequest) -> RippleSidecar:
    """Считает ripple-срез и атомарно публикует ``ripple.json`` в сессию."""
    options = validated_options(request)
    qc = span_qc(session=request.session, adapter=request.adapter, settling=request.settling)
    blocks = session_blocks(request.session, options, qc)
    baseline = _baseline_payload(request, options, qc, blocks)
    payload = _payload(request, options, qc, blocks, baseline)
    sidecar_path = write_ripple_sidecar(request.session.session_dir, payload)
    return RippleSidecar(
        session_dir=request.session.session_dir,
        sidecar_path=sidecar_path,
        payload=payload,
    )


def _baseline_payload(
    request: RippleRequest,
    options: RippleOptions,
    measurement_qc: SpanQc,
    measurement_blocks: SessionBlocks,
) -> dict[str, object] | None:
    """Фон рядом: квалификация сравнения, не коррекция измерения."""
    if request.baseline_path is None:
        return None
    baseline_session = load_baseline_session(request.baseline_path)
    attachment = request.baseline_attachment
    band = options.welch.bands[0]
    reasons = baseline_identity_reasons(
        measurement=request.session.manifest,
        baseline=baseline_session.manifest,
        attachment=attachment,
    )
    hashes = session_input_hashes(baseline_session)
    if reasons:
        # Несовместимая геометрия: числа фона не публикуются как согласованные —
        # сравнение недоступно, измерение остаётся валидным.
        return baseline_payload_block(
            manifest=baseline_session.manifest,
            hashes=hashes,
            attachment=attachment,
            comparison_status="unavailable",
            reason_codes=reasons,
            selection=None,
            time_domain=unavailable_scalars(reasons),
            spectrum=spectrum_unavailable(settings={}, reason_codes=reasons),
            bands=[
                band_unavailable(
                    band_id=band.name,
                    low_hz=band.low_hz,
                    high_hz=band.high_hz,
                    reason_codes=reasons,
                ),
            ],
        )
    qc = span_qc(
        session=baseline_session,
        adapter=request.adapter,
        settling=request.settling,
    )
    blocks = session_blocks(baseline_session, options, qc)
    comparison_reasons = _comparison_reasons(
        measurement_blocks=measurement_blocks,
        baseline_blocks=blocks,
        baseline_qc=qc,
        measurement_qc=measurement_qc,
    )
    return baseline_payload_block(
        manifest=baseline_session.manifest,
        hashes=hashes,
        attachment=attachment,
        comparison_status="unavailable" if comparison_reasons else "available",
        reason_codes=comparison_reasons,
        selection=selection_block(qc=qc, sample_rate_hz=baseline_session.manifest.sample_rate_hz),
        time_domain=blocks.time_domain,
        spectrum=blocks.spectrum,
        bands=blocks.bands,
    )


def _comparison_reasons(
    *,
    measurement_blocks: SessionBlocks,
    baseline_blocks: SessionBlocks,
    baseline_qc: SpanQc,
    measurement_qc: SpanQc,
) -> tuple[str, ...]:
    """Почему фон нельзя ставить рядом как эквивалент измерения."""
    reasons: list[str] = []
    if not measurement_blocks.all_available:
        reasons.append(REASON_MEASUREMENT_RESULT)
    if not baseline_blocks.all_available:
        reasons.append(REASON_BASELINE_RESULT)
        reasons.extend(baseline_blocks.unavailable_reasons)
    if reasons:
        return tuple(dict.fromkeys(reasons))
    if baseline_qc.span_count != measurement_qc.span_count:
        # Vpp/полосы по разным длительностям не эквивалентны; числа фона
        # остаются видимыми, но сравнение честно помечено недоступным.
        return (REASON_DURATION,)
    return ()


def _payload(
    request: RippleRequest,
    options: RippleOptions,
    qc: SpanQc,
    blocks: SessionBlocks,
    baseline: dict[str, object] | None,
) -> dict[str, object]:
    manifest = request.session.manifest
    band = options.welch.bands[0]
    return {
        "schema_version": 1,
        "algorithm": algorithm_block(),
        "options": options_block(
            band_low_hz=band.low_hz,
            band_high_hz=band.high_hz,
            interval_window_s=options.interval_window_s,
        ),
        "session": session_block(manifest=manifest, hashes=session_input_hashes(request.session)),
        "provenance": provenance_block(manifest=manifest, settling=request.settling.value),
        "adapter": adapter_block(request.adapter),
        "selection": selection_block(qc=qc, sample_rate_hz=manifest.sample_rate_hz),
        "qc": qc_block(qc),
        "time_domain": blocks.time_domain,
        "intervals": blocks.intervals,
        "spectrum": blocks.spectrum,
        "bands": blocks.bands,
        "baseline": baseline,
    }
