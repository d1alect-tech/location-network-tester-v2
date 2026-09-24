"""F14: общие идентификаторы, коды и persisted quantity names."""

from __future__ import annotations

from typing import Final

F14_ID: Final = "f14_cross_channel_event_association"
F14_INDEX: Final = 13
METHOD: Final = "bidirectional_event_triggered_cross_channel_association"
CHANNEL_MISSING: Final = "channel_missing"
CHANNELS_NOT_SYNCHRONOUS: Final = "channels_not_synchronous"
PHASE_REFERENCE_UNAVAILABLE: Final = "phase_reference_unavailable"
INSUFFICIENT_TRIGGERS: Final = "insufficient_triggers"
WINDOW_TRUNCATED: Final = "window_truncated"
GAPS_PRESENT: Final = "gaps_present"
EVENT_LIMIT: Final = "event_limit"
DECLARED_CODES: Final = (
    CHANNEL_MISSING,
    CHANNELS_NOT_SYNCHRONOUS,
    PHASE_REFERENCE_UNAVAILABLE,
    INSUFFICIENT_TRIGGERS,
    WINDOW_TRUNCATED,
    GAPS_PRESENT,
    EVENT_LIMIT,
)
MEAN_WAVEFORM_NAME: Final = "f14_mean_waveform_v"
EVENT_PROBABILITY_NAME: Final = "f14_event_probability"
NEAREST_LAG_NAME: Final = "f14_nearest_lag_s"
BASELINE_PROBABILITY_NAME: Final = "f14_baseline_probability"
LAG_SIGN_CONVENTION: Final = "target_after_trigger_positive"
CLAIM_BOUNDARY: Final = (
    "temporal association only; physical lead, source, coupling, causality, and utility "
    "are not established"
)
