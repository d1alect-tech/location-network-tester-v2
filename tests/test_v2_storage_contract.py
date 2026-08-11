from __future__ import annotations

from pathlib import Path
from typing import Final

import numpy as np
import pytest

from lnt.errors import InputError
from lnt.input_reference import InputReferenceStatus, derive_input_reference
from lnt.manifest import manifest_from_json, manifest_to_json
from lnt.session_store import load_session
from lnt.spectrum import BandSpectrum

FIXTURE_ROOT: Final = Path(__file__).parent / "fixtures" / "manifest_frozen"
VALID_FIXTURES: Final = (
    "schema_v1_synthetic_legacy.json",
    "schema_v2_hardware_floating_rc.json",
    "schema_v2_hardware_transformer.json",
)
INVALID_FIXTURES: Final = (
    "invalid_schema_v3.json",
    "invalid_v2_unknown_field.json",
)


@pytest.mark.parametrize("fixture_name", VALID_FIXTURES)
def test_frozen_manifest_round_trip_preserves_canonical_bytes(fixture_name: str) -> None:
    # Given: canonical bytes representing a supported frozen manifest schema.
    frozen = (FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8")

    # When: the bytes cross the strict typed boundary and canonical serializer.
    serialized = manifest_to_json(manifest_from_json(frozen))

    # Then: field order, shape, values, and trailing newline remain byte-identical.
    assert serialized == frozen


@pytest.mark.parametrize("fixture_name", INVALID_FIXTURES)
def test_frozen_invalid_manifest_fails_with_typed_input_error(fixture_name: str) -> None:
    # Given: a frozen unsupported-version or unknown-v2-field manifest.
    frozen = (FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8")

    # When/Then: strict compatibility fails closed through the public typed boundary.
    with pytest.raises(InputError):
        manifest_from_json(frozen)


def test_optional_context_sidecars_may_be_absent(tmp_path: Path) -> None:
    # Given: a complete legacy session with only its canonical manifest and channel.
    session_dir = tmp_path / "legacy-session"
    session_dir.mkdir()
    manifest_bytes = (FIXTURE_ROOT / VALID_FIXTURES[0]).read_bytes()
    (session_dir / "manifest.json").write_bytes(manifest_bytes)
    np.save(session_dir / "ch1.npy", np.zeros(4, dtype=np.float32))

    # When: the existing session loader reads it without future context sidecars.
    loaded = load_session(session_dir)

    # Then: current loading behavior is unchanged and no sidecar is synthesized.
    assert loaded.manifest.schema_version == 1
    assert loaded.ch1.tolist() == [0.0, 0.0, 0.0, 0.0]
    assert not (session_dir / "context.json").exists()
    assert not (session_dir / "context.events.jsonl").exists()


def test_schema_v1_without_ch1_setup_is_reason_coded_unavailable(tmp_path: Path) -> None:
    # Given: a loaded schema-v1 session, which cannot declare a CH1 transfer model.
    session_dir = tmp_path / "legacy-session"
    session_dir.mkdir()
    (session_dir / "manifest.json").write_bytes(
        (FIXTURE_ROOT / VALID_FIXTURES[0]).read_bytes(),
    )
    np.save(session_dir / "ch1.npy", np.zeros(4, dtype=np.float32))
    loaded = load_session(session_dir)
    spectrum = BandSpectrum(
        frequencies_hz=np.array([3_000.0], dtype=np.float64),
        psd_v2_per_hz=np.array([1e-12], dtype=np.float64),
        resolution_hz=50.0,
        band_low_hz=3_000.0,
        band_high_hz=3_000.0,
        peaks=(),
    )

    # When: input-reference correction is requested.
    reference = derive_input_reference(session_dir, loaded, spectrum)

    # Then: legacy compatibility is explicit rather than inferred from free text.
    assert reference.status is InputReferenceStatus.UNAVAILABLE
    assert reference.reason_code == "manifest_schema_v1"
