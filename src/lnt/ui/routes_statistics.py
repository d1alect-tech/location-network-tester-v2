"""Durable statistics runs and export-ready result retrieval."""
# ruff: noqa: D103, PLC0415, TC001

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from lnt.experiments import Experiment
from lnt.statistics import (
    AbaUnit,
    AnalysisContext,
    ContrastRefusal,
    DescriptiveEffect,
    InferentialEffect,
    PairedUnit,
    QualifiedWithinRunContrast,
    analyze_aba,
    estimate_paired,
)
from lnt.ui.dependencies import AppServices, get_services
from lnt.ui.models import JobStatus
from lnt.ui.research_models import StatisticsRun

router = APIRouter(prefix="/api/v2")
Services = Annotated[AppServices, Depends(get_services)]


def _metadata(
    result: InferentialEffect | DescriptiveEffect | ContrastRefusal | QualifiedWithinRunContrast,
    *,
    units: str,
    experiment: Experiment,
    estimand: str,
    job_id: str,
) -> dict[str, object]:
    metadata = result.metadata
    return {
        "units": units,
        "sampling_unit": metadata.sampling_unit,
        "hierarchy": list(metadata.hierarchy),
        "n": metadata.n,
        "missing_count": metadata.missing_count,
        "exclusions": [asdict(item) for item in metadata.exclusions],
        "estimator": metadata.estimator_name,
        "interval_method": metadata.interval_method,
        "provenance": {
            "experiment_id": experiment.experiment_id,
            "experiment_revision": experiment.revision,
            "estimand": estimand,
            "job_id": job_id,
        },
    }


def _calculate(request: StatisticsRun, experiment: Experiment, job_id: str) -> dict[str, object]:
    known = {
        item.feature_key
        for item in (*experiment.primary_estimands, *experiment.secondary_estimands)
    }
    if request.estimand not in known:
        raise ValueError("estimand не объявлен экспериментом")
    context = AnalysisContext(
        protocol=experiment.protocol,
        hierarchy=(experiment.protocol.site_key, experiment.protocol.subject_key),
        missing_count=0,
    )
    if request.kind == "aba":
        result = analyze_aba(
            tuple(AbaUnit(**item.model_dump()) for item in request.aba_units),
            context,
            seed=request.seed,
        )
        return {
            "result_kind": "refusal" if hasattr(result, "reason_code") else "effect",
            "result": asdict(result),
            "metadata": _metadata(
                result,
                units=request.units,
                experiment=experiment,
                estimand=request.estimand,
                job_id=job_id,
            ),
        }
    estimator = "block_paired" if request.kind == "repeated_blocks" else None
    result = estimate_paired(
        tuple(
            PairedUnit(
                unit_id_a=item.unit_id,
                unit_id_b=item.unit_id,
                value_a=item.value_a,
                value_b=item.value_b,
            )
            for item in request.pairs
        ),
        context,
        seed=request.seed,
        estimator_name=estimator,
    )
    return {
        "result_kind": "effect" if request.kind in {"ab", "repeated_blocks"} else "descriptive",
        "result": asdict(result),
        "metadata": _metadata(
            result,
            units=request.units,
            experiment=experiment,
            estimand=request.estimand,
            job_id=job_id,
        ),
    }


@router.post("/experiments/{experiment_id}/statistics-runs", status_code=202)
def submit_statistics(
    experiment_id: str, request: StatisticsRun, services: Services
) -> JSONResponse:
    from lnt.experiments import ExperimentStore

    try:
        experiment = ExperimentStore(services.root).load(experiment_id)
    except (KeyError, FileNotFoundError) as error:
        raise HTTPException(404, "эксперимент не найден") from error
    research_jobs = services.research_jobs
    if research_jobs is None:
        raise HTTPException(503, "сервис исследовательских задач не установлен")
    snapshot = research_jobs.submit(
        {"kind": "analysis", "experiment_id": experiment_id, **request.model_dump(mode="json")},
        lambda job_id: _calculate(request, experiment, job_id),
    )
    return JSONResponse(snapshot.to_payload(), status_code=202)


@router.get("/statistics-runs/{job_id}/result")
def statistics_result(job_id: str, services: Services) -> JSONResponse:
    research_jobs = services.research_jobs
    if research_jobs is None:
        raise HTTPException(503, "сервис исследовательских задач не установлен")
    try:
        snapshot = research_jobs.get(job_id)
    except KeyError as error:
        raise HTTPException(404, "статистическая задача не найдена") from error
    match snapshot.status:
        case JobStatus.SUCCEEDED:
            return JSONResponse(snapshot.result)
        case JobStatus.FAILED:
            raise HTTPException(
                422,
                {
                    "code": snapshot.error_code,
                    "detail": snapshot.error_message,
                },
            )
        case _:
            return JSONResponse(snapshot.to_payload(), status_code=202)
