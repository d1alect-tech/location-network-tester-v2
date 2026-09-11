"""Typed failures for characterization artifacts."""

from lnt.errors import InputError


class CharacterizationError(InputError):
    """A malformed, inconsistent, or oversized artifact bundle."""

    def __init__(self, reason_code: str, detail: str) -> None:
        """Store the stable machine reason alongside readable detail."""
        super().__init__(f"characterization artifact: {detail} ({reason_code})")
        self.reason_code: str = reason_code
