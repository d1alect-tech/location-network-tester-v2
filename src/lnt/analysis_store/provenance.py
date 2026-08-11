"""Воспроизводимая provenance locked execution environment.

Она описывает среду, но не обещает побитовую идентичность между платформами.
"""

from __future__ import annotations

import contextlib
import io
import platform
import sys
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from lnt.analysis_store.identity import CodeIdentity
    from lnt.context.json_codec import JsonValue


@dataclass(frozen=True, slots=True, kw_only=True)
class ProvenanceField:
    """Best-effort значение либо стабильный reason code."""

    value: str | None
    reason_code: str | None

    def to_mapping(self) -> dict[str, JsonValue]:
        """Возвращает typed JSON field."""
        return {"value": self.value, "reason_code": self.reason_code}


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisProvenance:
    """OS/Python/numerical backend provenance без времени исполнения."""

    os: ProvenanceField
    python: ProvenanceField
    numpy: ProvenanceField
    scipy: ProvenanceField
    fft_backend: ProvenanceField
    blas_impl: ProvenanceField

    @classmethod
    def current(cls, identity: CodeIdentity) -> AnalysisProvenance:
        """Собирает deterministic best-effort provenance текущей среды."""
        return cls(
            os=ProvenanceField(value=platform.platform(), reason_code=None),
            python=ProvenanceField(value=sys.version.split()[0], reason_code=None),
            numpy=ProvenanceField(value=identity.numpy, reason_code=None),
            scipy=ProvenanceField(value=identity.scipy, reason_code=None),
            fft_backend=ProvenanceField(value="scipy.fft:pocketfft-default", reason_code=None),
            blas_impl=_blas_field(),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        """Возвращает manifest-ready JSON."""
        return {
            "os": self.os.to_mapping(),
            "python": self.python.to_mapping(),
            "numpy": self.numpy.to_mapping(),
            "scipy": self.scipy.to_mapping(),
            "fft_backend": self.fft_backend.to_mapping(),
            "blas_impl": self.blas_impl.to_mapping(),
            "bit_identity_scope": (
                "только та же locked среда; межплатформенная идентичность не обещается"
            ),
        }


def _blas_field() -> ProvenanceField:
    stream = io.StringIO()
    try:
        with contextlib.redirect_stdout(stream), warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            np.show_config()
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return ProvenanceField(value=None, reason_code="numpy_show_config_failed")
    lines = [line.strip() for line in stream.getvalue().splitlines() if "blas" in line.lower()]
    if not lines:
        return ProvenanceField(value=None, reason_code="blas_not_reported")
    return ProvenanceField(value=" | ".join(lines), reason_code=None)
