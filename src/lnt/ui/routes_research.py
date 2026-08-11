"""Bounded longitudinal and audited hypothesis routes."""
# ruff: noqa: D103, TC001

from __future__ import annotations

import base64
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from lnt.research import (
    AnalysisRequest,
    HypothesisConflictError,
    HypothesisStatus,
    HypothesisStore,
    MetadataValue,
    Observation,
    analyze_longitudinal,
    hypothesis_status_label,
)
from lnt.ui.dependencies import AppServices, get_services
from lnt.ui.research_models import HypothesisWrite, TrendQuery

router = APIRouter(prefix="/api/v2")
Services = Annotated[AppServices, Depends(get_services)]
PageSize = Annotated[int, Query(ge=1, le=200)]


@router.post("/trends/query")
def query_trends(request: TrendQuery) -> JSONResponse:
    observations = tuple(
        Observation(
            observation_id=item.observation_id,
            timestamp=item.timestamp,
            source_offset=item.source_offset,
            location=item.location,
            condition=item.condition,
            predictor=item.predictor,
            outcome=item.outcome,
            metadata=tuple(
                MetadataValue(key=value.key, value=value.value) for value in item.metadata
            ),
        )
        for item in request.observations
    )
    result = analyze_longitudinal(
        observations,
        AnalysisRequest(
            minimum_n=request.minimum_n,
            max_lag=request.max_lag,
            bootstrap_samples=request.bootstrap_samples,
            seed=request.seed,
        ),
    )
    payload = asdict(result)
    payload["normalized_timestamps"] = [item.isoformat() for item in result.normalized_timestamps]
    payload["metadata"] = {
        "units": request.units,
        "estimator": "descriptive_longitudinal",
        "n": result.data_quality.usable_count,
        "provenance": {"seed": request.seed, "dedupe_policy": result.data_quality.dedupe_policy},
    }
    return JSONResponse(payload)


def _store(services: AppServices) -> HypothesisStore:
    return HypothesisStore(services.root)


@router.post("/hypotheses", status_code=201)
def create_hypothesis(request: HypothesisWrite, services: Services) -> JSONResponse:
    try:
        saved = _store(services).save(
            request.hypothesis, expected_revision=request.expected_revision
        )
    except HypothesisConflictError as error:
        raise HTTPException(
            409, {"code": "hypothesis_revision_conflict", "detail": str(error)}
        ) from error
    return JSONResponse(saved.model_dump(mode="json"), status_code=201)


@router.put("/hypotheses/{hypothesis_id}")
def update_hypothesis(
    hypothesis_id: str, request: HypothesisWrite, services: Services
) -> JSONResponse:
    if request.hypothesis.hypothesis_id != hypothesis_id:
        raise HTTPException(422, "id гипотезы не совпадает")
    try:
        saved = _store(services).save(
            request.hypothesis, expected_revision=request.expected_revision
        )
    except HypothesisConflictError as error:
        raise HTTPException(
            409, {"code": "hypothesis_revision_conflict", "detail": str(error)}
        ) from error
    return JSONResponse(saved.model_dump(mode="json"))


@router.get("/hypotheses/{hypothesis_id}")
def get_hypothesis(hypothesis_id: str, services: Services) -> JSONResponse:
    try:
        hypothesis = _store(services).load(hypothesis_id)
    except KeyError as error:
        raise HTTPException(404, "гипотеза не найдена") from error
    payload = hypothesis.model_dump(mode="json")
    payload["status_label"] = hypothesis_status_label(hypothesis.status)
    return JSONResponse(payload)


@router.get("/hypotheses")
def list_hypotheses(
    services: Services,
    page_size: PageSize = 50,
    cursor: str | None = None,
    status_filter: Annotated[HypothesisStatus | None, Query(alias="status")] = None,
) -> JSONResponse:
    try:
        start = (
            0
            if cursor is None
            else int(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        )
    except ValueError as error:
        raise HTTPException(422, "некорректный cursor") from error
    store = _store(services)
    ids = (
        tuple(sorted(path.name for path in store.root.iterdir() if path.is_dir()))
        if store.root.is_dir()
        else ()
    )
    selected = tuple(
        item
        for item in (store.load(hypothesis_id) for hypothesis_id in ids)
        if status_filter is None or item.status is status_filter
    )
    page = selected[start : start + page_size]
    items = []
    for item in page:
        payload = item.model_dump(mode="json")
        payload["status_label"] = hypothesis_status_label(item.status)
        items.append(payload)
    next_index = start + len(page)
    next_cursor = (
        base64.urlsafe_b64encode(str(next_index).encode()).decode().rstrip("=")
        if next_index < len(selected)
        else None
    )
    return JSONResponse({"items": items, "next_cursor": next_cursor})
