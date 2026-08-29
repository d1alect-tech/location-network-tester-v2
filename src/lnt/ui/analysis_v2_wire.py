"""Run analysis v2 after v1 Analyze without failing the job."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from lnt.analysis_v2 import AnalysisOrchestrator, DefaultAnalysisEngine
from lnt.analysis_v2.default_recipe import BUILTIN_MEASUREMENT_RECIPE

if TYPE_CHECKING:
    from pathlib import Path

    from lnt.analysis import AnalysisResult, LineQualityAnalysis
    from lnt.cm_dm.analysis import CmDmAnalysis


class BranchFailureRecord(TypedDict):
    """JSON-shaped isolated branch failure for the job result payload."""

    branch: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class AnalyzeWriteResult:
    """v1 analysis plus isolated v2 branch failures."""

    analysis: AnalysisResult | LineQualityAnalysis | CmDmAnalysis
    branch_failures: tuple[BranchFailureRecord, ...]


def run_v2_after_v1(session_dir: Path) -> tuple[BranchFailureRecord, ...]:
    """Publish v2 artifacts and a default pointer; never raise into the job path."""
    try:
        result = AnalysisOrchestrator(engine=DefaultAnalysisEngine()).run(
            session_dir,
            BUILTIN_MEASUREMENT_RECIPE,
            project_legacy=False,
        )
        _write_default_pointer(
            session_dir,
            BUILTIN_MEASUREMENT_RECIPE.recipe_sha256,
            result.artifact_key,
        )
    except Exception as error:  # noqa: BLE001, BROAD_EXCEPT_OK - Analyze job stays succeeded
        return (
            {
                "branch": "orchestrator",
                "error_type": type(error).__name__,
                "message": str(error),
            },
        )
    return tuple(
        BranchFailureRecord(
            branch=failure.branch,
            error_type=failure.error_type,
            message=failure.message,
        )
        for failure in result.failures
    )


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
