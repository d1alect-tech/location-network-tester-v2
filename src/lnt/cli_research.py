"""Bounded trend, comparability, and protocol-confirmation CLI operations."""
# ruff: noqa: T201

from __future__ import annotations

import json
from dataclasses import asdict
from itertools import pairwise
from typing import TYPE_CHECKING

from pydantic import TypeAdapter, ValidationError

from lnt.acquisition_quality import AcquisitionQuality
from lnt.comparability import SessionDescriptor, assess_pair
from lnt.errors import InputError
from lnt.experiments import ExperimentStore
from lnt.experiments.runner import CaptureArtifact, ProtocolRunner
from lnt.experiments.runner_store import ProtocolRunStore
from lnt.research import AnalysisRequest, MetadataValue, Observation, analyze_longitudinal
from lnt.runtime.scheduler import OperationScheduler
from lnt.ui.research_models import TrendQuery

if TYPE_CHECKING:
    from pathlib import Path


def run_trends(path: Path) -> int:
    """Parse the API-equivalent bounded request and print labeled JSON."""
    try:
        request = TrendQuery.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise InputError(f"тренды: не удалось прочитать файл {path}: {error}") from error
    except ValidationError as error:
        raise InputError(f"тренды: некорректные поля: {_validation_fields(error)}") from error
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
        "provenance": {
            "seed": request.seed,
            "dedupe_policy": result.data_quality.dedupe_policy,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def run_check(experiment_id: str, root: Path) -> int:
    """Assess every adjacent experiment member pair from strict descriptors."""
    experiment = ExperimentStore(root).load(experiment_id)
    descriptors = tuple(_descriptor(root / member.storage_ref) for member in experiment.members)
    reports = tuple(assess_pair(left, right) for left, right in pairwise(descriptors))
    blocked = any(not report.comparable for report in reports)
    print(f"сопоставимость: {'заблокирована' if blocked else 'разрешена'}")
    for report in reports:
        for finding in report.findings:
            if finding.level != "ok":
                print(f"{finding.level.value}: {finding.code} ({', '.join(finding.fields)})")
    return 0


def run_confirm(run_id: str, actor: str, root: Path) -> int:
    """Confirm a real intervention with an explicit audit actor."""
    quality = AcquisitionQuality(
        quality_thresholds_version=1,
        channels=(),
        findings=(),
        maximum_callback_gap_s=0.0,
        short_block_count=0,
    )
    runner = ProtocolRunner(
        store=ProtocolRunStore(root.parent / "protocol-runs"),
        scheduler=OperationScheduler(cpu_workers=1, cpu_queue_limit=1),
        preflight=lambda: (),
        capture=lambda order: CaptureArtifact(
            session_id=f"confirmed-{order}",
            storage_ref=f"confirmed-{order}",
            artifact_refs=(),
            quality=quality,
        ),
    )
    try:
        record = runner.confirm(run_id, actor=actor, auto_confirm=False)
    finally:
        runner.close()
    print(f"Запуск {run_id}: {record.status.value}; подтвердил {actor}")
    return 0


def _descriptor(directory: Path) -> SessionDescriptor:
    path = directory / "comparability.json"
    try:
        return TypeAdapter(SessionDescriptor).validate_json(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise InputError(f"сопоставимость: не удалось прочитать {path}: {error}") from error
    except ValidationError as error:
        raise InputError(
            f"сопоставимость: некорректные поля {path}: {_validation_fields(error)}"
        ) from error


def validation_fields(error: ValidationError) -> str:
    """Expose compact field paths without dumping opaque validation prose."""
    return _validation_fields(error)


def _validation_fields(error: ValidationError) -> str:
    return ", ".join(".".join(str(part) for part in item["loc"]) for item in error.errors())
