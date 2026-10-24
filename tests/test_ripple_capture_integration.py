"""Сквозная интеграция ripple: декларация захвата -> контекст -> CLI -> GET.

Идиома изоляции — ``tests/test_capture_context_catalog.py``: fake-захват через
monkeypatch ``acquire.run_capture`` + изолированный LOCALAPPDATA-каталог.
Вызов CLI — идиома ``tests/test_cli_ripple.py`` (``main(argv)`` + capsys).
Отсчёты — константа: проверяется контракт доставки (write-once декларация,
валюта сайдкара, 409/422-отказы, GET no-store), а не числа движка; ни одно
ожидание не выводится из кода под тестом.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import TYPE_CHECKING, Final, cast

import numpy as np
from starlette.testclient import TestClient

from lnt import acquire, session_projection
from lnt.cli import EXIT_OK, main
from lnt.context.events import read_event_history
from lnt.context.store import ContextStore
from lnt.instrument import FakeHantekScope
from lnt.ripple.adapter_declaration import ADAPTER_CONTEXT_KEYS, AdapterDeclaration
from lnt.types import AcquisitionTelemetry, ChannelMode, ComponentValuesBasis, SeriesPosition
from lnt.ui.app import create_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_FS_HZ: Final = 50_000.0
_DURATION_S: Final = 2.5
_SAMPLE_COUNT: Final = 125_000  # спан после префикса установления длиннее сегмента Welch

_BAND: Final[list[str]] = ["--band-low", "100", "--band-high", "1000"]

_DECLARATION: Final = AdapterDeclaration(
    cap_nf=100.0,
    series_r_ohm=470.0,
    preconnected=True,
    component_values_basis=ComponentValuesBasis.OPERATOR_MEASURED,
)
_DECLARATION_PAYLOAD: Final[dict[str, object]] = {
    "preconnected": True,
    "cap_nf": 100.0,
    "series_r_ohm": 470.0,
    "component_values_basis": "operator_measured",
}


def _isolate_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return local / "LNT" / "catalog.sqlite3"


def _fake_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подменяет захват прибора детерминированной константой без железа."""
    raw = np.full(_SAMPLE_COUNT, 128, dtype=np.uint8)
    telemetry = AcquisitionTelemetry(
        requested_samples=_SAMPLE_COUNT,
        captured_samples=_SAMPLE_COUNT,
        callback_count=1,
        block_lengths=(_SAMPLE_COUNT,),
        callback_gaps_s=(),
        expected_block_interval_s=_SAMPLE_COUNT / _FS_HZ,
        short_block_count=0,
        ch1_clip_low_count=0,
        ch1_clip_high_count=0,
        ch2_clip_low_count=0,
        ch2_clip_high_count=0,
        calibration_used=False,
    )

    def fake_run_capture(*_args: object, **_kwargs: object) -> tuple[object, object, object]:
        return raw, raw, telemetry

    monkeypatch.setattr(acquire, "run_capture", fake_run_capture)


def _capture_session(
    monkeypatch: pytest.MonkeyPatch,
    out_dir: Path,
    *,
    declaration: AdapterDeclaration | None,
    series: SeriesPosition | None = None,
) -> Path:
    """Захватывает одноканальную сессию fake-прибором с опциональной декларацией."""
    _fake_capture(monkeypatch)
    return acquire.capture_session(
        out_dir=out_dir,
        duration_s=_DURATION_S,
        sample_rate_hz=_FS_HZ,
        channel_mode=ChannelMode.CH1_ONLY,
        scope_factory=FakeHantekScope,
        adapter_declaration=declaration,
        series=series,
    )


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _sidecar(session: Path) -> dict[str, object]:
    text = (session / "ripple.json").read_text(encoding="utf-8")
    return cast("dict[str, object]", json.loads(text))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mutation_headers(client: TestClient) -> dict[str, str]:
    return {"X-LNT-Mutation-Nonce": client.get("/api/config").json()["mutation_nonce"]}


def test_declaration_flows_from_capture_to_cli_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: захват с декларацией адаптера и изолированный каталог.
    database = _isolate_catalog(monkeypatch, tmp_path)
    sessions = tmp_path / "sessions"
    session = _capture_session(monkeypatch, sessions / "cap", declaration=_DECLARATION)

    # Then (до CLI): контекст опубликован и спроецирован в каталог.
    assert (session / "context.json").is_file()
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT field_key, field_value FROM catalog_context_fields WHERE storage_path = ?",
            (str(session.resolve()),),
        ).fetchall()
    values = dict(rows)
    assert set(ADAPTER_CONTEXT_KEYS) <= set(values)
    assert json.loads(values["adapter.cap_nf"]) == 100.0
    assert json.loads(values["adapter.component_values_basis"]) == "operator_measured"

    # When: CLI без флагов адаптера.
    code, out, err = _run(capsys, ["ripple", str(session), *_BAND])

    # Then: сайдкар берёт адаптер и провенанс подключения из декларации.
    assert code == EXIT_OK
    assert err == ""
    payload = _sidecar(session)
    adapter = cast("dict[str, object]", payload["adapter"])
    assert adapter["cap_nf"] == 100.0
    assert adapter["series_r_ohm"] == 470.0
    assert adapter["probe_multiplier"] == 1
    assert adapter["component_values_basis"] == "operator_measured"
    provenance = cast("dict[str, object]", payload["provenance"])
    assert provenance["operator_attachment"] == "preconnected_no_reconnection"
    time_domain = cast("dict[str, object]", payload["time_domain"])
    assert time_domain["availability"] == "available"
    assert "ripple.json" in out


def test_settling_unknown_when_capture_declaration_unchecked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: декларация без галки «подключено до старта записи».
    _isolate_catalog(monkeypatch, tmp_path)
    declaration = AdapterDeclaration(
        cap_nf=100.0,
        series_r_ohm=470.0,
        preconnected=False,
        component_values_basis=ComponentValuesBasis.OPERATOR_MEASURED,
    )
    session = _capture_session(monkeypatch, tmp_path / "sessions" / "cap", declaration=declaration)

    # When
    code, _out, err = _run(capsys, ["ripple", str(session), *_BAND])

    # Then: установление не известно; публичные числа честно недоступны.
    assert code == EXIT_OK
    assert err == ""
    payload = _sidecar(session)
    provenance = cast("dict[str, object]", payload["provenance"])
    assert provenance["operator_attachment"] == "settling_unknown"
    time_domain = cast("dict[str, object]", payload["time_domain"])
    assert time_domain["availability"] == "unavailable"
    assert "settling_unknown" in cast("list[str]", time_domain["reason_codes"])


def test_rerun_republishes_identical_payload_and_leaves_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: сессия с декларацией; первый запуск опубликовал сайдкар.
    _isolate_catalog(monkeypatch, tmp_path)
    session = _capture_session(monkeypatch, tmp_path / "sessions" / "cap", declaration=_DECLARATION)
    argv = ["ripple", str(session), *_BAND]
    code_first, _out, err_first = _run(capsys, argv)
    assert code_first == EXIT_OK
    assert err_first == ""
    watched = ("ripple.json", "context.json", "context.events.jsonl", "manifest.json", "ch1.npy")
    before = {name: _sha(session / name) for name in watched}

    # When: повторный прогон без изменений входов.
    code_second, _out2, err_second = _run(capsys, argv)

    # Then: перепубликация os.replace даёт идентичный payload; входы не тронуты.
    assert code_second == EXIT_OK
    assert err_second == ""
    assert {name: _sha(session / name) for name in watched} == before
    assert not list(session.glob(".ripple.json.partial-*"))


def test_put_rewrite_of_declaration_rejected_409_analysis_converges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: захваченная декларация; анализ уже опубликован.
    _isolate_catalog(monkeypatch, tmp_path)
    sessions = tmp_path / "sessions"
    session = _capture_session(monkeypatch, sessions / "cap", declaration=_DECLARATION)
    session_id = session_projection.session_id_from_manifest(session)
    code, _out, err = _run(capsys, ["ripple", str(session), *_BAND])
    assert code == EXIT_OK
    assert err == ""
    numbers_before = cast("dict[str, object]", _sidecar(session)["time_domain"])
    sidecar_before = _sha(session / "ripple.json")
    context_before = _sha(session / "context.json")

    # When: PUT-попытка переписать декларацию через API контекста.
    with TestClient(create_app(root=sessions, index_catalog=True)) as client:
        current = client.get(f"/api/context/{session_id}")
        assert current.status_code == 200
        fields = dict(current.json()["fields"])
        fields["adapter.cap_nf"] = {**fields["adapter.cap_nf"], "value": 220.0}
        rewrite = client.put(
            f"/api/context/{session_id}",
            json={"expected_revision": current.json()["revision"], "fields": fields},
            headers=_mutation_headers(client),
        )

    # Then: write-once валюта — 409, контекст не мутирован.
    assert rewrite.status_code == 409
    assert rewrite.json()["reason"] == "adapter_declaration_immutable"
    assert _sha(session / "context.json") == context_before

    # And: повторный анализ сходится к тем же числам (R5).
    code_again, _out, err_again = _run(capsys, ["ripple", str(session), *_BAND])
    assert code_again == EXIT_OK
    assert err_again == ""
    assert cast("dict[str, object]", _sidecar(session)["time_domain"]) == numbers_before
    assert _sha(session / "ripple.json") == sidecar_before


def test_get_ripple_serves_sidecar_200_no_store_inputs_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: опубликованный сайдкар; входы сессии зафиксированы хэшами.
    _isolate_catalog(monkeypatch, tmp_path)
    sessions = tmp_path / "sessions"
    session = _capture_session(monkeypatch, sessions / "cap", declaration=_DECLARATION)
    session_id = session_projection.session_id_from_manifest(session)
    code, _out, err = _run(capsys, ["ripple", str(session), *_BAND])
    assert code == EXIT_OK
    assert err == ""
    stored = (session / "ripple.json").read_bytes()
    inputs_before = (_sha(session / "manifest.json"), _sha(session / "ch1.npy"))

    # When: GET по session_id из манифеста.
    with TestClient(create_app(root=sessions, index_catalog=True)) as client:
        response = client.get(f"/api/sessions/{session_id}/ripple")

    # Then: сохранённые байты, no-store; входы и сайдкар не тронуты.
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/json")
    assert response.content == stored
    assert (session / "ripple.json").read_bytes() == stored
    assert (_sha(session / "manifest.json"), _sha(session / "ch1.npy")) == inputs_before


def test_legacy_capture_explicit_flags_match_cli_ripple_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: легаси-захват без декларации (как в фикс-тестах test_cli_ripple).
    _isolate_catalog(monkeypatch, tmp_path)
    sessions = tmp_path / "sessions"
    session = _capture_session(monkeypatch, sessions / "meas", declaration=None)

    # When: явные флаги адаптера.
    code, _out, err = _run(
        capsys,
        [
            "ripple",
            str(session),
            *_BAND,
            "--cap-nf",
            "220",
            "--series-r-ohm",
            "330",
            "--probe",
            "1x",
            "--preconnected",
        ],
    )

    # Then: значения из флагов — тот же контракт, что в существующих фикс-тестах.
    assert code == EXIT_OK
    assert err == ""
    adapter = cast("dict[str, object]", _sidecar(session)["adapter"])
    assert adapter["cap_nf"] == 220.0
    assert adapter["series_r_ohm"] == 330.0
    assert adapter["probe_multiplier"] == 1
    assert adapter["component_values_basis"] == "nominal"
    provenance = cast("dict[str, object]", _sidecar(session)["provenance"])
    assert provenance["operator_attachment"] == "preconnected_no_reconnection"

    # And: без флагов и без декларации — сегодняшние дефолты (H6).
    bare = _capture_session(monkeypatch, sessions / "bare", declaration=None)
    code_bare, _out2, err_bare = _run(capsys, ["ripple", str(bare), *_BAND])
    assert code_bare == EXIT_OK
    assert err_bare == ""
    payload_bare = _sidecar(bare)
    adapter_bare = cast("dict[str, object]", payload_bare["adapter"])
    assert adapter_bare["cap_nf"] == 100.0
    assert adapter_bare["series_r_ohm"] == 0.0
    assert adapter_bare["probe_multiplier"] == 1
    provenance_bare = cast("dict[str, object]", payload_bare["provenance"])
    assert provenance_bare["operator_attachment"] == "settling_unknown"


def test_simulate_job_with_declaration_rejected_422(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: simulate-запрос с декларацией адаптера.
    _isolate_catalog(monkeypatch, tmp_path)
    body: dict[str, object] = {
        "kind": "simulate",
        "profile": "quiet",
        "adapter_declaration": _DECLARATION_PAYLOAD,
    }

    # When
    with TestClient(create_app(root=tmp_path / "sessions")) as client:
        response = client.post("/api/jobs", json=body, headers=_mutation_headers(client))

    # Then: декларация несовместима с симуляцией.
    assert response.status_code == 422


def test_series_repeat_two_children_own_initial_events_no_crosstalk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: серия repeat=2 с декларацией; первый ребёнок захвачен.
    _isolate_catalog(monkeypatch, tmp_path)
    sessions = tmp_path / "sessions"
    first = _capture_session(
        monkeypatch,
        sessions / "series-001",
        declaration=_DECLARATION,
        series=SeriesPosition(index=1, total=2, interval_s=0.0),
    )
    first_id = session_projection.session_id_from_manifest(first)
    first_context = (first / "context.json").read_bytes()

    # When: второй ребёнок той же серии.
    second = _capture_session(
        monkeypatch,
        sessions / "series-002",
        declaration=_DECLARATION,
        series=SeriesPosition(index=2, total=2, interval_s=0.0),
    )
    second_id = session_projection.session_id_from_manifest(second)

    # Then: сосед не заражён; у каждого ребёнка ровно одно своё начальное событие.
    assert first_id != second_id
    assert (first / "context.json").read_bytes() == first_context
    for child, child_id in ((first, first_id), (second, second_id)):
        events = read_event_history(child / "context.events.jsonl", child_id)
        snapshot = ContextStore(child, child_id).load().snapshot
        assert snapshot is not None
        assert len(events) == 1
        assert events[0].event_id == f"initial-{child_id}"
        assert events[0].actor == "lnt.capture"
        assert events[0].new_revision == 1
        assert set(ADAPTER_CONTEXT_KEYS) <= set(snapshot.fields)
