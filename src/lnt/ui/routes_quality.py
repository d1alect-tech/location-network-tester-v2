"""Typed comparability and QC check routes."""

from __future__ import annotations

from dataclasses import asdict
from typing import ClassVar

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from lnt.comparability import SessionDescriptor, assess_pair

router = APIRouter(prefix="/api/v2")


class PairCheck(BaseModel):
    """Strict pair of complete comparability descriptors."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)
    left: SessionDescriptor
    right: SessionDescriptor


@router.post("/comparability/check")
def check_comparability(request: PairCheck) -> JSONResponse:
    """Return every blocking and warning dimension without a numeric effect."""
    report = assess_pair(request.left, request.right)
    return JSONResponse(
        {
            "comparable": report.comparable,
            "findings": [asdict(item) for item in report.findings],
        }
    )
