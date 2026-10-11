"""Фейк-приборы живого режима: подмена железа без драйвера и USB.

Публичная поверхность — ``FakeHantekScope`` (полный ``ScopeProtocol`` с
кадровым каденсом) и ``ManualClock`` (инжектируемое время для
детерминированных тестов).
"""

from .fake_scope import FakeHantekScope, ManualClock

__all__ = ["FakeHantekScope", "ManualClock"]
