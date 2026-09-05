"""Характеризация фасада ProtocolRunner перед расслоением на листья.

Пинует то, что расслоение обязано сохранить дословно: коды и русские тексты
трёх исключений, их подъём из реальных путей раннера и HTTP-маппинг кода
ошибки. Эти тесты зелены и до, и после переноса хелперов в
``runner_errors``/``runner_mapping``.

Тесты с ``identity`` в имени — целевой инвариант расслоения: фасад обязан
РЕЭКСПОРТИРОВАТЬ классы листа, а не объявлять свои копии, иначе
``except runner.X`` перестанет ловить исключения, поднятые через
``runner_errors.X``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from lnt.acquisition_quality import AcquisitionQuality
from lnt.experiments import runner as facade
from lnt.experiments import runner_errors as leaves
from lnt.experiments.runner import (
    AutoConfirmationRejectedError,
    CaptureArtifact,
    ProtocolRunMode,
    ProtocolRunner,
    ProtocolRunStatus,
    ProtocolRunStore,
    RandomizationSeedRequiredError,
)
from lnt.runtime import OperationScheduler
from lnt.ui.app import create_app
from tests.experiments.factories import make_experiment

if TYPE_CHECKING:
    from pathlib import Path

    from lnt.experiments.model import Experiment

_AUTO_CONFIRM_TEXT = "физическое вмешательство нельзя подтвердить автоматически в реальном режиме"
_SEED_TEXT = "для рандомизации протокола требуется сохранённый seed"
_STATE_TEXT = "запуск протокола содержит недопустимое состояние: confirmation_missing"


def _headers(client: TestClient) -> dict[str, str]:
    nonce = client.get("/api/config").json()["mutation_nonce"]
    return {"X-LNT-Mutation-Nonce": nonce, "Origin": "http://127.0.0.1"}


def _create(client: TestClient) -> None:
    response = client.post(
        "/api/v2/experiments",
        headers=_headers(client),
        json={"experiment": make_experiment().model_dump(mode="json"), "expected_revision": 0},
    )
    assert response.status_code == 201


def _capture(order: int) -> CaptureArtifact:
    return CaptureArtifact(
        session_id=f"captured-{order}",
        storage_ref=f"captured-{order}",
        artifact_refs=(f"captured-{order}/manifest.json",),
        quality=AcquisitionQuality(
            quality_thresholds_version=1,
            channels=(),
            findings=(),
            maximum_callback_gap_s=0.0,
            short_block_count=0,
        ),
    )


def _runner(tmp_path: Path) -> ProtocolRunner:
    return ProtocolRunner(
        store=ProtocolRunStore(tmp_path / "runs"),
        scheduler=OperationScheduler(cpu_workers=1, cpu_queue_limit=1),
        preflight=lambda: (),
        capture=_capture,
    )


def _randomized() -> Experiment:
    source = make_experiment()
    return source.model_copy(
        update={"protocol": source.protocol.model_copy(update={"order_scheme": "randomized"})}
    )


def test_exception_russian_messages_and_codes_are_pinned_verbatim() -> None:
    """Given три исключения, When приводим к строке, Then тексты совпадают дословно."""
    auto = facade.AutoConfirmationRejectedError()
    seed = facade.RandomizationSeedRequiredError()
    state = facade.ProtocolStateError("confirmation_missing")

    assert auto.code == "real_intervention_auto_confirmation_forbidden"
    assert str(auto) == _AUTO_CONFIRM_TEXT
    assert seed.code == "protocol_randomization_seed_required"
    assert str(seed) == _SEED_TEXT
    assert state.code == "confirmation_missing"
    assert str(state) == _STATE_TEXT


def test_randomized_start_without_seed_raises_pinned_error(tmp_path: Path) -> None:
    """Given рандомизированный протокол без seed, When start, Then типизированный отказ."""
    runner = _runner(tmp_path)
    try:
        with pytest.raises(RandomizationSeedRequiredError) as raised:
            runner.start(
                run_id="char-seedless", experiment=_randomized(), mode=ProtocolRunMode.SIMULATOR
            )
    finally:
        runner.close()

    assert raised.value.code == "protocol_randomization_seed_required"
    assert str(raised.value) == _SEED_TEXT


def test_real_auto_confirmation_raises_pinned_error(tmp_path: Path) -> None:
    """Given реальный запуск на границе, When авто-подтверждение, Then типизированный отказ."""
    runner = _runner(tmp_path)
    try:
        pending = runner.start(
            run_id="char-real", experiment=make_experiment(), mode=ProtocolRunMode.REAL
        )
        assert pending.status is ProtocolRunStatus.AWAITING_CONFIRMATION
        with pytest.raises(AutoConfirmationRejectedError) as raised:
            runner.confirm("char-real", actor="operator", auto_confirm=True)
    finally:
        runner.close()

    assert raised.value.code == "real_intervention_auto_confirmation_forbidden"
    assert str(raised.value) == _AUTO_CONFIRM_TEXT


def test_missing_confirmation_raises_pinned_protocol_state_error(tmp_path: Path) -> None:
    """Given граница без подтверждения, When завершаем участника, Then инвариант падает."""
    runner = _runner(tmp_path)
    try:
        pending = runner.start(
            run_id="char-unconfirmed", experiment=make_experiment(), mode=ProtocolRunMode.REAL
        )
        assert pending.current_confirmation is None
        with pytest.raises(facade.ProtocolStateError) as raised:
            # Характеризация внутреннего перехода: публичного пути к этому состоянию нет.
            runner._finish_member(pending, lambda: False)  # pyright: ignore[reportPrivateUsage]
    finally:
        runner.close()

    assert raised.value.code == "confirmation_missing"
    assert str(raised.value) == _STATE_TEXT


def test_real_run_auto_confirmation_maps_to_403_with_typed_russian_error(tmp_path: Path) -> None:
    """Given реальный запуск, When авто-подтверждение по HTTP, Then 403 с кодом и текстом."""
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        _create(client)
        started = client.post(
            "/api/v2/experiments/latency-study/runs",
            headers=_headers(client),
            json={"run_id": "char-real-1", "mode": "real"},
        )
        response = client.post(
            "/api/v2/protocol-runs/char-real-1/confirm",
            headers=_headers(client),
            json={"actor": "user:tester", "auto_confirm": True},
        )

    assert started.status_code == 201
    assert response.status_code == 403
    assert response.json() == {
        "code": "real_intervention_auto_confirmation_forbidden",
        "detail": _AUTO_CONFIRM_TEXT,
    }


def test_identity_facade_exception_names_are_the_leaf_classes_themselves() -> None:
    """Given фасад и лист, When сравниваем классы, Then это один и тот же объект."""
    assert facade.AutoConfirmationRejectedError is leaves.AutoConfirmationRejectedError
    assert facade.RandomizationSeedRequiredError is leaves.RandomizationSeedRequiredError
    assert facade.ProtocolStateError is leaves.ProtocolStateError


def test_identity_route_error_mapping_catches_the_leaf_exception_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given seam кидает класс листа, When confirm по HTTP, Then маршрут всё ещё ловит его."""

    def _raise_leaf(_self: ProtocolRunner, _run_id: str, **_kwargs: object) -> None:
        raise leaves.AutoConfirmationRejectedError

    monkeypatch.setattr(ProtocolRunner, "confirm", _raise_leaf)

    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        response = client.post(
            "/api/v2/protocol-runs/char-leaf-1/confirm",
            headers=_headers(client),
            json={"actor": "user:tester", "auto_confirm": True},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "real_intervention_auto_confirmation_forbidden"
