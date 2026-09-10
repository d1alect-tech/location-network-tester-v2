"""Typed comparability and QC check routes."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal, cast

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from lnt.comparability import (
    ComparabilityFinding,
    FindingLevel,
    SessionDescriptor,
    assess_pair,
)
from lnt.errors import InputError
from lnt.manifest import manifest_from_json
from lnt.safe_paths import is_linked_path
from lnt.ui.dependencies import AppServices, get_services, resolve_session_or_404

if TYPE_CHECKING:
    from pathlib import Path

router = APIRouter(prefix="/api/v2")


class SessionReference(BaseModel):
    """Strict reference to one persisted session descriptor."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)
    session_id: str


class PairCheck(BaseModel):
    """Pair of complete descriptors or persisted-session references."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)
    left: SessionDescriptor | SessionReference
    right: SessionDescriptor | SessionReference


Services = Annotated[AppServices, Depends(get_services)]


def _unavailable(side: Literal["left", "right"], *fields: str) -> ComparabilityFinding:
    return ComparabilityFinding(
        dimension="descriptor",
        level=FindingLevel.BLOCK,
        code="comparability_descriptor_unavailable",
        fields=tuple(f"{side}.{field}" for field in fields),
    )


def _resolve_descriptor(
    root: Path,
    value: SessionDescriptor | SessionReference,
    side: Literal["left", "right"],
) -> tuple[SessionDescriptor | None, ComparabilityFinding | None]:
    if isinstance(value, SessionDescriptor):
        return value, None
    session_dir = resolve_session_or_404(root, value.session_id)
    descriptor_path = session_dir / "comparability.json"
    if is_linked_path(descriptor_path):
        return None, _unavailable(side, "comparability_descriptor")
    try:
        manifest_id = manifest_from_json(
            (session_dir / "manifest.json").read_text(encoding="utf-8")
        ).session_id
        descriptor = TypeAdapter(SessionDescriptor).validate_json(
            descriptor_path.read_text(encoding="utf-8-sig")
        )
    except ValidationError as error:
        fields = tuple(
            ".".join(str(part) for part in item["loc"]) or "comparability_descriptor"
            for item in error.errors()
        )
        return None, _unavailable(side, *fields)
    except (InputError, OSError, UnicodeError):
        return None, _unavailable(side, "comparability_descriptor")
    if descriptor.session_id != manifest_id:
        return None, _unavailable(side, "session_id")
    return descriptor, None


@router.post("/comparability/check")
def check_comparability(request: PairCheck, services: Services) -> JSONResponse:
    """Return every blocking and warning dimension without a numeric effect."""
    left, left_finding = _resolve_descriptor(services.root, request.left, "left")
    right, right_finding = _resolve_descriptor(services.root, request.right, "right")
    unavailable = tuple(item for item in (left_finding, right_finding) if item is not None)
    if unavailable:
        return JSONResponse(
            {"comparable": False, "findings": [asdict(item) for item in unavailable]}
        )
    report = assess_pair(cast("SessionDescriptor", left), cast("SessionDescriptor", right))
    return JSONResponse(
        {
            "comparable": report.comparable,
            "findings": [asdict(item) for item in report.findings],
        }
    )
