"""Граница запроса безопасной проверки аппаратного захвата."""

from typing import ClassVar

from pydantic import ConfigDict

from lnt.ui.models import CaptureRequest


class CapturePreflightBody(CaptureRequest):
    """Тот же capture-контракт без запуска durable job."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)
