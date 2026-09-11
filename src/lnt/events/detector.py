"""Legacy candidate inventory collected from the bounded event-run stream."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from lnt.events.metrics import EventRun, MetricContext, materialize_event
from lnt.events.models import EventInventory
from lnt.events.stream import stream_event_runs

if TYPE_CHECKING:
    from lnt.events.models import BaselineFloor
    from lnt.events.settings import DetectionSettings
    from lnt.events.stream import FloatArray

__all__ = ["detect_events", "stream_event_runs"]


def detect_events(
    samples: FloatArray,
    *,
    sample_rate_hz: float,
    settings: DetectionSettings,
    baseline: BaselineFloor | None = None,
) -> EventInventory:
    """Inventory candidates without assigning a physical cause."""
    metric_context = MetricContext(
        samples=samples, sample_rate_hz=sample_rate_hz, settings=settings
    )
    events = []
    gaps = []
    for item in stream_event_runs(
        samples, sample_rate_hz=sample_rate_hz, settings=settings, baseline=baseline
    ):
        if isinstance(item, EventRun):
            events.append(materialize_event(item, metric_context))
        else:
            gaps.append(item)
    settings_json = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return EventInventory(
        schema_version=1,
        sample_rate_hz=sample_rate_hz,
        sample_count=int(samples.size),
        settings_hash=hashlib.sha256(settings_json.encode("utf-8")).hexdigest(),
        settings=settings,
        baseline_qualification_rule_id=(
            baseline.qualification_rule_id if baseline is not None else None
        ),
        events=tuple(events),
        unqualified_gaps=tuple(gaps),
    )
