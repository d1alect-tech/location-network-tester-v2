from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from lnt.characterization import (
    FAMILY_IDS,
    ArrayReference,
    Band,
    CharacterizationBundle,
    FamilyResult,
    Filter,
    Inference,
    Qc,
    ScalarSummary,
    SignalPlane,
    Status,
    Support,
    TableBlock,
    TableColumn,
    TableReference,
    TableValueType,
    Unit,
    Window,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def _support(*, observations: int = 10, missing: int = 0, stored: int = 10) -> Support:
    return Support(
        start_s=0.0,
        end_s=1.0,
        duration_s=1.0,
        sample_count=observations + missing,
        observation_count=observations,
        missing_count=missing,
        stored_count=stored,
        selection_rule="all" if stored == observations else "even_floor_index",
    )


def make_bundle() -> CharacterizationBundle:
    results: list[FamilyResult] = []
    for index, family_id in enumerate(FAMILY_IDS):
        status = Status.UNAVAILABLE
        reasons = ("not_computed",)
        support = _support(observations=0, stored=0)
        summaries: tuple[ScalarSummary, ...] = ()
        array_refs: tuple[ArrayReference, ...] = ()
        table_refs: tuple[TableReference, ...] = ()
        if index == 0:
            status = Status.AVAILABLE
            reasons = ()
            support = _support()
            summaries = (ScalarSummary(name="frequency_hz", value=50.0, unit=Unit.HZ),)
        elif index == 1:
            status = Status.PARTIAL
            reasons = ("clipped",)
            support = _support(missing=2, stored=4)
            array_refs = (
                ArrayReference(
                    array_id="event_waveform_v",
                    role="representative_event_waveform",
                    unit=Unit.V,
                    dtype="float64",
                    shape=(4,),
                    validity_mask_id="event_waveform_valid",
                    offsets_id="event_waveform_offsets",
                ),
            )
            table_refs = (TableReference(table_id="events", role="event_inventory"),)
        results.append(
            FamilyResult(
                family_id=family_id,
                status=status,
                reason_codes=reasons,
                method=f"test_{family_id}",
                method_version=1,
                units=(Unit.V, Unit.HZ),
                window=Window(
                    kind="fixed", duration_s=0.2, sample_count=None, overlap_fraction=0.0
                ),
                band=Band(low_hz=3000.0, high_hz=200000.0),
                filter=Filter(kind="none", order=None, phase="none"),
                n=support.observation_count,
                support=support,
                missing_rule="exclude_and_count",
                qc=Qc(passed=status is Status.AVAILABLE, reason_codes=reasons),
                signal_plane=SignalPlane.CH1_SCOPE_INPUT,
                inference=Inference(),
                array_refs=array_refs,
                table_refs=table_refs,
                comparison_summary=summaries,
            )
        )
    return CharacterizationBundle(families=tuple(results))


def make_arrays() -> Mapping[str, np.ndarray]:
    return {
        "event_waveform_v": np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float64),
        "event_waveform_valid": np.array([1, 0, 1, 1], dtype=np.uint8),
        "event_waveform_offsets": np.array([0, 2, 4], dtype=np.int64),
    }


def make_tables() -> Mapping[str, TableBlock]:
    return {
        "events": TableBlock(
            table_id="events",
            columns=(
                TableColumn(name="peak_v", unit=Unit.V, type=TableValueType.NUMBER),
                TableColumn(
                    name="peak_v_reason_code",
                    unit=None,
                    type=TableValueType.REASON_CODE,
                ),
            ),
            rows=((1.5, None), (None, "clipped")),
            row_count=2,
            stored_count=2,
            selection_rule="all",
        )
    }


@pytest.fixture
def bundle() -> CharacterizationBundle:
    return make_bundle()


@pytest.fixture
def arrays() -> Mapping[str, np.ndarray]:
    return make_arrays()


@pytest.fixture
def tables() -> Mapping[str, TableBlock]:
    return make_tables()
