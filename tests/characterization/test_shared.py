from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
import pytest
from numpy.typing import NDArray

import lnt.characterization.shared as shared_module
from lnt.analysis_store import CharacterizationRecipe, parse_analysis_recipe
from lnt.characterization import prepare_shared_computations
from lnt.characterization.bands import resolve_characterization_bands
from lnt.characterization.clipping import resolve_clipping
from lnt.characterization.envelopes import prepare_band_envelopes
from lnt.characterization.events import compute_root_events
from lnt.characterization.phase import compute_phase_cycles, compute_phase_means
from lnt.characterization.records import Status
from lnt.context.json_codec import decode_object
from lnt.session_store import LoadedSession, load_session, write_session
from lnt.types import ChannelMeta, ChannelRole, SessionManifest, SessionSource, SessionType

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Literal

    from lnt.analysis_store.characterization_settings import PhaseSettings, ResourceLimits
    from lnt.characterization.bands import ResolvedBand
    from lnt.characterization.clipping import ClippingBounds
    from lnt.characterization.envelope_models import BandEnvelopes
    from lnt.characterization.event_models import RootEvents
    from lnt.characterization.phase import PhaseCycles, PhaseMeans
    from lnt.context.json_codec import JsonValue

_EXAMPLE = Path(__file__).parents[2] / "docs/examples/characterization-recipe-v2.json"
_RATE_HZ = 3_200.0
_COUNT = 19_200

type FloatInput = NDArray[np.float32] | NDArray[np.float64]


def _recipe(*channels: str) -> CharacterizationRecipe:
    mapping = decode_object(_EXAMPLE.read_text(encoding="utf-8"), "test recipe")
    mapping["channels"] = cast("JsonValue", list(channels))
    recipe = parse_analysis_recipe(mapping)
    assert isinstance(recipe, CharacterizationRecipe)
    return recipe


def _channel(name: str, role: ChannelRole) -> ChannelMeta:
    return ChannelMeta(
        filename=f"{name}.npy",
        role=role,
        unit="V",
        front_end="synthetic",
        range_code=2,
        probe_multiplier=1.0,
    )


def _loaded_session(tmp_path: Path, *, with_ch2: bool = True) -> LoadedSession:
    time_s = np.arange(_COUNT, dtype=np.float64) / _RATE_HZ
    ch1 = np.resize(np.array([-0.01, 0.0, 0.01], dtype=np.float32), _COUNT)
    ch1[_COUNT // 2] = 0.3
    ch2 = (
        np.sin(2.0 * np.pi * 50.0 * (time_s - 0.25 / _RATE_HZ)).astype(np.float32)
        if with_ch2
        else None
    )
    manifest = SessionManifest(
        schema_version=1,
        session_id="shared-test",
        created_utc="2026-09-11T00:00:00Z",
        completed_utc="2026-09-11T00:00:01Z",
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.MEASUREMENT,
        sample_rate_hz=_RATE_HZ,
        duration_s=_COUNT / _RATE_HZ,
        sample_count=_COUNT,
        line_frequency_hz=50.0,
        profile=None,
        baseline_session=None,
        ch1=_channel("ch1", ChannelRole.HF_PROBE),
        ch2=_channel("ch2", ChannelRole.LF_TRANSFORMER) if with_ch2 else None,
        acquisition_telemetry=None,
        synthetic_truth=None,
    )
    target = tmp_path / "session"
    write_session(session_dir=target, manifest=manifest, ch1=ch1, ch2=ch2)
    return load_session(target)


def _tree_sha256(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_real_session_prepares_ordered_shared_roots_without_writes(tmp_path: Path) -> None:
    session = _loaded_session(tmp_path)
    recipe = _recipe("ch2", "ch1")
    recipe_before = recipe.to_mapping()
    files_before = _tree_sha256(session.session_dir)

    shared = prepare_shared_computations(session, recipe)

    assert tuple(channel.name for channel in shared.channels) == ("ch2", "ch1")
    assert shared.channels[0].samples is session.ch2
    assert shared.channels[1].samples is session.ch1
    assert shared.phase.status in {Status.AVAILABLE, Status.PARTIAL}
    assert shared.phase.sample_count == _COUNT
    assert all(
        tuple(item.resolved for item in channel.band_envelopes.bands) == shared.bands
        for channel in shared.channels
        if channel.band_envelopes is not None
    )
    assert shared.channels[1].root_events is not None
    assert shared.channels[1].root_events.accepted_count > 0
    assert recipe.to_mapping() == recipe_before
    assert _tree_sha256(session.session_dir) == files_before
    assert not (session.session_dir / "analyses").exists()


def test_missing_or_undeclared_ch2_never_disables_ch1_events(tmp_path: Path) -> None:
    session = _loaded_session(tmp_path, with_ch2=False)
    shared = prepare_shared_computations(session, _recipe("ch1"))

    assert shared.phase.status is Status.UNAVAILABLE
    assert shared.phase.sample_count == 0
    channel = shared.channels[0]
    assert channel.phase_means is not None
    assert channel.phase_means.status is Status.UNAVAILABLE
    assert channel.root_events is not None
    assert channel.root_events.accepted_count > 0
    assert channel.band_envelopes is not None
    assert all(
        item.phase_means.reason_code == "phase_reference_unavailable"
        for item in channel.band_envelopes.bands
        if item.resolved.effective is not None
    )


def test_requested_missing_channel_is_explicit_and_ordered(tmp_path: Path) -> None:
    session = _loaded_session(tmp_path, with_ch2=False)

    shared = prepare_shared_computations(session, _recipe("ch2", "ch1"))

    missing, available = shared.channels
    assert missing.name == "ch2"
    assert missing.reason == "channel_missing"
    assert missing.samples is missing.clipping is missing.phase_means is None
    assert missing.root_events is missing.band_envelopes is None
    assert available.name == "ch1"
    assert available.reason is None
    assert available.root_events is not None
    assert available.root_events.accepted_count > 0


def test_each_root_runs_once_and_ch1_recipe_does_not_consume_loaded_ch2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _loaded_session(tmp_path)
    recipe = _recipe("ch1")
    calls: dict[str, int] = dict.fromkeys(
        ("phase", "bands", "clipping", "means", "events", "envelopes"), 0
    )
    phases: list[PhaseCycles] = []

    def tracked_phase(
        ch2: FloatInput | None,
        *,
        sample_rate_hz: float,
        settings: PhaseSettings,
        resources: ResourceLimits,
        checkpoint: Callable[[], None] | None = None,
    ) -> PhaseCycles:
        calls["phase"] += 1
        assert ch2 is None
        return compute_phase_cycles(
            ch2,
            sample_rate_hz=sample_rate_hz,
            settings=settings,
            resources=resources,
            checkpoint=checkpoint,
        )

    def tracked_bands(
        selected_recipe: CharacterizationRecipe, sample_rate_hz: float
    ) -> tuple[ResolvedBand, ...]:
        calls["bands"] += 1
        return resolve_characterization_bands(selected_recipe, sample_rate_hz)

    def tracked_clipping(
        manifest: SessionManifest,
        channel: Literal["ch1", "ch2"],
        fraction_of_range: float,
    ) -> ClippingBounds:
        calls["clipping"] += 1
        return resolve_clipping(manifest, channel, fraction_of_range)

    def tracked_means(
        samples: FloatInput,
        phase: PhaseCycles,
        *,
        settings: PhaseSettings,
        resources: ResourceLimits,
        checkpoint: Callable[[], None] | None = None,
    ) -> PhaseMeans:
        calls["means"] += 1
        assert samples is session.ch1
        phases.append(phase)
        return compute_phase_means(
            samples,
            phase,
            settings=settings,
            resources=resources,
            checkpoint=checkpoint,
        )

    def tracked_events(
        samples: NDArray[np.floating],
        *,
        sample_rate_hz: float,
        recipe: CharacterizationRecipe,
        clipping: ClippingBounds,
        checkpoint: Callable[[], None] | None = None,
    ) -> RootEvents:
        calls["events"] += 1
        assert samples is session.ch1
        return compute_root_events(
            samples,
            sample_rate_hz=sample_rate_hz,
            recipe=recipe,
            clipping=clipping,
            checkpoint=checkpoint,
        )

    def tracked_envelopes(
        samples: FloatInput,
        phase: PhaseCycles,
        recipe: CharacterizationRecipe,
        *,
        sample_rate_hz: float,
        checkpoint: Callable[[], None] | None = None,
    ) -> BandEnvelopes:
        calls["envelopes"] += 1
        assert samples is session.ch1
        return prepare_band_envelopes(
            samples,
            phase,
            recipe,
            sample_rate_hz=sample_rate_hz,
            checkpoint=checkpoint,
        )

    monkeypatch.setattr(shared_module, "compute_phase_cycles", tracked_phase)
    monkeypatch.setattr(shared_module, "resolve_characterization_bands", tracked_bands)
    monkeypatch.setattr(shared_module, "resolve_clipping", tracked_clipping)
    monkeypatch.setattr(shared_module, "compute_phase_means", tracked_means)
    monkeypatch.setattr(shared_module, "compute_root_events", tracked_events)
    monkeypatch.setattr(shared_module, "prepare_band_envelopes", tracked_envelopes)

    shared = prepare_shared_computations(session, recipe)

    assert calls == {
        "phase": 1,
        "bands": 1,
        "clipping": 1,
        "means": 1,
        "events": 1,
        "envelopes": 1,
    }
    assert phases == [shared.phase]


def test_checkpoint_exception_propagates_by_identity_before_work(tmp_path: Path) -> None:
    session = _loaded_session(tmp_path)
    error = RuntimeError("cancel")

    def cancel() -> None:
        raise error

    with pytest.raises(RuntimeError) as caught:
        prepare_shared_computations(session, _recipe("ch1", "ch2"), checkpoint=cancel)
    assert caught.value is error
