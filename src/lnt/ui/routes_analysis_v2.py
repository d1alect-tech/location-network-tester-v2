"""Bounded artifact-backed HTTP API for immutable analysis recipes."""

from __future__ import annotations

import csv
import io
import json
import os
import uuid
from dataclasses import replace
from pathlib import Path  # noqa: TC003 - runtime response paths
from typing import Annotated, Final

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from lnt.analysis_store import AnalysisRecipe, ArtifactCorruptError, ArtifactStore
from lnt.analysis_v2 import AnalysisOrchestrator, DefaultAnalysisEngine
from lnt.analysis_v2.jobs import AnalysisJobStore
from lnt.analysis_v2.recipes import RecipeCatalog
from lnt.ui.decimation import min_max_envelope
from lnt.ui.dependencies import AppServices, get_services, require_csrf
from lnt.ui.models_analysis_v2 import (  # noqa: TC001 - FastAPI resolves request models
    AnalysisRunRequest,
    RecipeCloneRequest,
    RecipeCreateRequest,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis-v2"])
Services = Annotated[AppServices, Depends(get_services)]
MAX_POINTS: Final = 50_000
MIN_POINTS: Final = 4
MAX_RANGE: Final = 10_000_000.0


@router.post("/recipes", dependencies=[Depends(require_csrf)], status_code=201)
def create_recipe(request: RecipeCreateRequest, services: Services) -> dict[str, object]:
    """Persist one immutable recipe."""
    recipe = AnalysisRecipe.from_mapping(request.recipe)
    return (
        RecipeCatalog(services.root / ".lnt" / "analysis-recipes")
        .create(request.name, recipe)
        .payload()
    )


@router.get("/recipes")
def list_recipes(services: Services) -> dict[str, object]:
    """List all immutable recipes."""
    return {
        "items": [
            item.payload()
            for item in RecipeCatalog(services.root / ".lnt" / "analysis-recipes").list()
        ]
    }


@router.post("/recipes/{recipe_id}/clone", dependencies=[Depends(require_csrf)], status_code=201)
def clone_recipe(
    recipe_id: str, request: RecipeCloneRequest, services: Services
) -> dict[str, object]:
    """Clone a recipe without changing its source."""
    return (
        RecipeCatalog(services.root / ".lnt" / "analysis-recipes")
        .clone(recipe_id, request.name)
        .payload()
    )


@router.delete("/recipes/{recipe_id}", dependencies=[Depends(require_csrf)])
def reject_recipe_delete(recipe_id: str) -> None:
    """Reject deletion because published artifacts may reference recipes."""
    raise HTTPException(
        status.HTTP_409_CONFLICT, f"рецепт {recipe_id} неизменяем и может быть указан в artifact"
    )


@router.post("/runs", dependencies=[Depends(require_csrf)], status_code=202)
def run_analysis(request: AnalysisRunRequest, services: Services) -> dict[str, str | int | None]:
    """Run through the durable job seam; computation remains cooperative and bounded."""
    jobs = AnalysisJobStore(services.root / ".lnt" / "analysis-jobs")
    job = jobs.create()
    recipe = RecipeCatalog(services.root / ".lnt" / "analysis-recipes").get(request.recipe_id)

    def progress(stage: str, completed: int, total: int) -> None:
        jobs.write(replace(job, stage=stage, completed=completed, total=total))

    try:
        result = AnalysisOrchestrator(engine=DefaultAnalysisEngine()).run(
            services.root / request.session,
            recipe.recipe,
            progress=progress,
            project_legacy=request.make_default,
        )
    except (OSError, ValueError) as error:
        failed = replace(job, status="failed", stage="done", error=str(error))
        jobs.write(failed)
        return failed.payload()
    succeeded = replace(
        job,
        status="succeeded",
        stage="done",
        completed=1,
        total=1,
        artifact_key=result.artifact_key,
    )
    jobs.write(succeeded)
    if request.make_default:
        _write_default_pointer(
            services.root / request.session, recipe.recipe_id, result.artifact_key
        )
    return succeeded.payload()


@router.get("/runs/{job_id}")
def analysis_status(job_id: str, services: Services) -> dict[str, str | int | None]:
    """Return the latest durable analysis job snapshot."""
    try:
        return AnalysisJobStore(services.root / ".lnt" / "analysis-jobs").get(job_id).payload()
    except OSError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "задача анализа не найдена") from error


@router.get("/sessions/{session_name}/artifacts/{artifact_key}/{filename}")
def artifact_file(
    session_name: str, artifact_key: str, filename: str, services: Services
) -> Response:
    """Serve bytes only after manifest integrity verification."""
    artifact = _verified_artifact(services, session_name, artifact_key)
    path = artifact / filename
    if not path.is_file() or path.parent != artifact:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "файл artifact не найден")
    media = "application/json" if filename.endswith(".json") else "application/octet-stream"
    return Response(path.read_bytes(), media_type=media)


@router.get("/sessions/{session_name}/artifacts/{artifact_key}/plot/spectrum")
def spectrum_plot(
    session_name: str,
    artifact_key: str,
    services: Services,
    max_points: Annotated[int, Query()] = 5000,
) -> dict[str, object]:
    """Return a bounded extrema-preserving spectrum payload."""
    return _spectrum_payload(services, session_name, artifact_key, None, None, max_points)


@router.get("/sessions/{session_name}/artifacts/{artifact_key}/plot/spectrum/zoom")
def spectrum_zoom(  # noqa: PLR0913, PLR0917 - FastAPI path/query boundary
    session_name: str,
    artifact_key: str,
    services: Services,
    start: float,
    end: float,
    max_points: Annotated[int, Query()] = 5000,
) -> dict[str, object]:
    """Return range-selected extrema-preserving spectrum points."""
    if end <= start or end - start > MAX_RANGE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "диапазон zoom вне предела")
    return _spectrum_payload(services, session_name, artifact_key, start, end, max_points)


def _verified_artifact(services: AppServices, session_name: str, artifact_key: str) -> Path:
    store = ArtifactStore(services.root / session_name)
    try:
        artifact = store.find(artifact_key)
    except ArtifactCorruptError as error:
        store.invalidate(artifact_key)
        raise HTTPException(
            status.HTTP_409_CONFLICT, "artifact повреждён и помещён в карантин"
        ) from error
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact не найден")
    return artifact


def _spectrum_payload(  # noqa: PLR0913, PLR0917 - shared route boundary
    services: AppServices,
    session_name: str,
    artifact_key: str,
    start: float | None,
    end: float | None,
    max_points: int,
) -> dict[str, object]:
    if not MIN_POINTS <= max_points <= MAX_POINTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "max_points вне предела 4..50000"
        )
    artifact = _verified_artifact(services, session_name, artifact_key)
    rows = tuple(
        csv.DictReader(io.StringIO((artifact / "spectrum.csv").read_text(encoding="utf-8")))
    )
    x = np.asarray([float(row["frequency_hz"]) for row in rows], dtype=np.float64)
    y = np.asarray([float(row["psd_v2_per_hz"]) for row in rows], dtype=np.float64)
    if start is not None and end is not None:
        selected = (x >= start) & (x <= end)
        x, y = x[selected], y[selected]
    series = min_max_envelope(x, y, max_points=max_points)
    return {"x": series.x, "y": series.y, "point_count": series.point_count}


def _write_default_pointer(session_dir: Path, recipe_id: str, artifact_key: str) -> None:
    path = session_dir / ".lnt-default-analysis.json"
    temporary = path.with_name(f".{path.name}.partial-{uuid.uuid4().hex}")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(
                {"recipe_id": recipe_id, "artifact_key": artifact_key}, stream, sort_keys=True
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)  # noqa: PTH105 - explicit atomic seam
    finally:
        temporary.unlink(missing_ok=True)
