from __future__ import annotations

from lnt.characterization import FAMILY_IDS, CharacterizationBundle, FamilyResult, Status


def test_public_api_exposes_exact_family_contract() -> None:
    assert len(FAMILY_IDS) == 18
    assert FAMILY_IDS[0] == "f01_phase_cycle"
    assert FAMILY_IDS[-1] == "f18_bicoherence_triads"
    assert CharacterizationBundle
    assert FamilyResult
    assert tuple(Status) == (Status.AVAILABLE, Status.PARTIAL, Status.UNAVAILABLE)
