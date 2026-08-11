import os
from pathlib import Path

import pytest

from lnt.errors import InputError
from lnt.profiles import (
    ConditionsProfile,
    DamperState,
    EquipmentProfile,
    FrontEndProfile,
    LocationProfile,
    ProfileKind,
    ProfileStore,
    TransformerProfile,
    profile_from_json,
)


def test_profile_store_crud_preserves_immutable_revision_history(tmp_path: Path) -> None:
    store = ProfileStore(root=tmp_path, clock=lambda: "2026-08-11T10:00:00.000Z")
    initial = LocationProfile(alias="стенд", outlet="A-3", circuit="lab")

    created = store.create("lab-main", initial)
    updated = store.update(
        "lab-main", LocationProfile(alias="стенд 2", outlet="A-3", circuit="lab")
    )

    assert (created.revision, updated.revision) == (1, 2)
    assert store.get("lab-main") == updated
    assert store.history("lab-main") == (created, updated)
    store.delete("lab-main")
    assert store.list() == ()


@pytest.mark.parametrize("profile_id", ["../escape", "space id", "", ".hidden"])
def test_profile_store_rejects_unsafe_ids(tmp_path: Path, profile_id: str) -> None:
    store = ProfileStore(root=tmp_path)

    with pytest.raises(InputError):
        store.create(profile_id, EquipmentProfile(alias="scope", model="6022BE"))


def test_profile_parser_rejects_unknown_unit_and_secret_looking_field() -> None:
    unknown_unit = (
        '{"schema_version":1,"profile_id":"front-end","kind":"front_end",'
        '"revision":1,"captured_at":"2026-08-11T10:00:00.000Z",'
        '"data":{"resistance":{"value":1000,"unit":"furlong"},'
        '"c1":{"value":1e-9,"unit":"F"},"c2":{"value":1e-9,"unit":"F"}}}'
    )
    forbidden = (
        '{"schema_version":1,"profile_id":"lab","kind":"location",'
        '"revision":1,"captured_at":"2026-08-11T10:00:00.000Z",'
        '"data":{"alias":"lab","outlet":"A","circuit":"1","username":"secret"}}'
    )

    with pytest.raises(InputError):
        profile_from_json(unknown_unit)
    with pytest.raises(InputError):
        profile_from_json(forbidden)


def test_all_profile_kinds_are_versioned_typed_snapshots(tmp_path: Path) -> None:
    store = ProfileStore(root=tmp_path)
    profiles = (
        LocationProfile(alias="lab", outlet="A", circuit="1"),
        EquipmentProfile(alias="scope", model="6022BE"),
        FrontEndProfile.from_si(resistance_ohm=1_000.0, c1_f=1e-9, c2_f=2e-9),
        TransformerProfile.from_si(nominal_primary_v=230.0, nominal_secondary_v=9.0),
        ConditionsProfile(damper_state=DamperState.ON, nearby_load_states=("pc:on", "lamp:off")),
    )

    snapshots = tuple(
        store.create(f"profile-{index}", profile) for index, profile in enumerate(profiles)
    )

    assert {snapshot.kind for snapshot in snapshots} == set(ProfileKind)


def test_failed_atomic_write_leaves_no_partial_profile_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ProfileStore(root=tmp_path)

    def fail_replace(_source: Path | str, _destination: Path | str) -> None:
        raise PermissionError("read only")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(InputError):
        store.create("lab", LocationProfile(alias="lab", outlet="A", circuit="1"))

    assert list(tmp_path.rglob("*.partial-*")) == []
    assert list(tmp_path.rglob("*.json")) == []
