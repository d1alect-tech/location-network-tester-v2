"""Сборка единственного владельца живого режима панели.

``create_app`` регистрирует владельца в ``AppServices.instrument`` и передаёт тот
же объект гейту job-захвата (``JobManager(live_ownership=...)``): объект один,
второго источника владения прибором нет. Сборка НЕ обращается к железу —
``LiveCaptureGate`` прибор не открывает и preflight не запускает, поэтому старт
приложения остаётся дешёвым, а ``InstrumentService`` создаётся лениво, только на
``POST /api/live/start``.

Проба среды внедряется в гейт и вызывается в момент старта: состояние устройства
— только через ``diagnose_device`` (та же диагностика, что у
``/api/device/state``), свободное место и writability корня — как у
``POST /api/capture/preflight``. Baseline живому режиму не нужен (сессия не
пишется), поэтому его совместимость честно ``NOT_REQUESTED``. Per-device таблицу
АЦП гейт не подменяет: провенанс вольт кадра остаётся ``calibration_used=False``.
Режим объявляется при сборке (``LiveMode``) — панель не выводит его из состояния.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lnt.capture_preflight import BaselineCompatibility, CaptureEnvironment
from lnt.instrument.live_gate import LiveCaptureGate, LiveMode
from lnt.scope_io import open_real_scope
from lnt.ui.device import diagnose_device, disk_free_bytes

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from lnt.scope_io import ScopeProtocol


def capture_environment(root: Path) -> CaptureEnvironment:
    """Проба среды live-старта: устройство, свободное место, writability корня."""
    return CaptureEnvironment(
        device_state=diagnose_device().state,
        free_bytes=disk_free_bytes(root),
        root_writable=root.is_dir(),
        baseline_compatibility=BaselineCompatibility.NOT_REQUESTED,
    )


def build_live_gate(
    root: Path,
    *,
    scope_factory: Callable[[], ScopeProtocol] = open_real_scope,
    mode: LiveMode = LiveMode.REAL,
) -> LiveCaptureGate:
    """Собирает владельца живого режима для корня сессий ``root``."""
    return LiveCaptureGate(
        scope_factory=scope_factory,
        environment_probe=lambda: capture_environment(root),
        session_root=root,
        mode=mode,
    )
