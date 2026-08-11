"""Раздельные идентичности recipe и исполняемого artifact."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib import metadata
from typing import Final

from lnt.context.json_codec import JsonValue, encode_canonical

SHA256_LENGTH: Final = 64


@dataclass(frozen=True, slots=True, kw_only=True, order=True)
class NamedDigest:
    """Именованная явно объявленная SHA-256 зависимость."""

    name: str
    digest: str

    def __post_init__(self) -> None:
        """Проверяет имя и lowercase SHA-256 digest."""
        if not self.name or len(self.digest) != SHA256_LENGTH:
            raise ValueError("имя зависимости и SHA-256 обязательны")
        try:
            int(self.digest, 16)
        except ValueError as error:
            raise ValueError("digest зависимости должен быть lowercase SHA-256") from error
        if self.digest != self.digest.lower():
            raise ValueError("digest зависимости должен быть lowercase SHA-256")


@dataclass(frozen=True, slots=True, kw_only=True)
class CodeIdentity:
    """Версии LNT и двух locked численных зависимостей."""

    lnt: str
    numpy: str
    scipy: str

    @classmethod
    def current(cls) -> CodeIdentity:
        """Читает deterministic identity из metadata текущего locked environment."""
        return cls(
            lnt=metadata.version("lnt"),
            numpy=metadata.version("numpy"),
            scipy=metadata.version("scipy"),
        )

    @property
    def identity_string(self) -> str:
        """Возвращает однозначную строку identity для ключа artifact."""
        return f"lnt={self.lnt};numpy={self.numpy};scipy={self.scipy}"


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactInputs:
    """Все и только явно объявленные входы content-addressed artifact."""

    recipe_sha256: str
    raw_inputs: tuple[NamedDigest, ...]
    context_dependencies: tuple[NamedDigest, ...]
    profile_dependencies: tuple[NamedDigest, ...]
    calibration_dependencies: tuple[NamedDigest, ...]
    code_identity: CodeIdentity

    def __post_init__(self) -> None:
        """Проверяет recipe identity и уникальность имён зависимостей."""
        if len(self.recipe_sha256) != SHA256_LENGTH:
            raise ValueError("recipe_sha256 должен быть SHA-256")
        all_names = [item.name for group in self.dependency_groups for item in group]
        if len(all_names) != len(set(all_names)):
            raise ValueError("имена входов artifact должны быть уникальными")

    @property
    def dependency_groups(self) -> tuple[tuple[NamedDigest, ...], ...]:
        """Возвращает группы входов в фиксированном порядке manifest."""
        return (
            self.raw_inputs,
            self.context_dependencies,
            self.profile_dependencies,
            self.calibration_dependencies,
        )

    @property
    def artifact_key(self) -> str:
        """Хеширует recipe, declared dependencies и locked code identity."""
        payload: dict[str, JsonValue] = {
            "recipe_sha256": self.recipe_sha256,
            "raw_inputs": _digests(self.raw_inputs),
            "context_dependencies": _digests(self.context_dependencies),
            "profile_dependencies": _digests(self.profile_dependencies),
            "calibration_dependencies": _digests(self.calibration_dependencies),
            "code_identity": self.code_identity.identity_string,
        }
        return hashlib.sha256(encode_canonical(payload, "входы artifact")).hexdigest()


def _digests(values: tuple[NamedDigest, ...]) -> list[JsonValue]:
    return [{"name": item.name, "digest": item.digest} for item in sorted(values)]
