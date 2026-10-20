"""CLI-контракт ``lnt ripple``: регистрация, exit-коды, аддитивность, свод.

Истина аналитическая: синус 100 Гц A=0.05 В + DC 0.5 В на fs=10 кГц; время
установления объявлено ``--preconnected``. Ожидания exit-кодов, одна строка
stderr и отсутствие traceback — контракт AGENTS.md. Ни одно ожидание не
выводится из CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from typing import TYPE_CHECKING, cast

import numpy as np
import pytest

from lnt.cli import (
    EXIT_INPUT,
    EXIT_OK,
    _build_parser,  # pyright: ignore[reportPrivateUsage]
    main,
)
from lnt.cli_spec import CLI_SUBCOMMANDS
from lnt.session_store import write_session
from lnt.types import (
    AcquisitionTelemetry,
    ChannelMeta,
    ChannelRole,
    SessionManifest,
    SessionSource,
    SessionType,
)

if TYPE_CHECKING:
    from pathlib import Path

_FS_HZ = 10_000.0
_COUNT = 29_000
_AMPLITUDE_V = 0.05
_TONE_HZ = 100.0
_DC_V = 0.5

_BANDED = ["--band-low", "99.0", "--band-high", "101.0", "--preconnected"]


def _sine_record() -> np.ndarray:
    times = np.arange(_COUNT, dtype=np.float64) / _FS_HZ
    record = _DC_V + _AMPLITUDE_V * np.sin(2.0 * np.pi * _TONE_HZ * times)
    return record.astype(np.float32)


def _telemetry() -> AcquisitionTelemetry:
    return AcquisitionTelemetry(
        requested_samples=_COUNT,
        captured_samples=_COUNT,
        callback_count=1,
        block_lengths=(_COUNT,),
        callback_gaps_s=(),
        expected_block_interval_s=_COUNT / _FS_HZ,
        short_block_count=0,
        ch1_clip_low_count=0,
        ch1_clip_high_count=0,
        ch2_clip_low_count=0,
        ch2_clip_high_count=0,
        calibration_used=False,
    )


def _manifest(session_id: str) -> SessionManifest:
    return SessionManifest(
        schema_version=1,
        session_id=session_id,
        created_utc="2026-10-20T00:00:00Z",
        completed_utc="2026-10-20T00:00:03Z",
        source=SessionSource.SYNTHETIC,
        session_type=SessionType.MEASUREMENT,
        sample_rate_hz=_FS_HZ,
        duration_s=_COUNT / _FS_HZ,
        sample_count=_COUNT,
        line_frequency_hz=50.0,
        profile=None,
        baseline_session=None,
        parameters={},
        ch1=ChannelMeta(
            filename="ch1.npy",
            role=ChannelRole.HF_PROBE,
            unit="V",
            front_end="ripple CLI fixture",
            range_code=10,
            probe_multiplier=1.0,
        ),
        ch2=None,
        acquisition_telemetry=_telemetry(),
        synthetic_truth=None,
    )


def _write_session(path: Path, session_id: str) -> Path:
    write_session(session_dir=path, manifest=_manifest(session_id), ch1=_sine_record(), ch2=None)
    return path


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _sidecar_payload(session_dir: Path) -> dict[str, object]:
    text = (session_dir / "ripple.json").read_text(encoding="utf-8")
    return cast("dict[str, object]", json.loads(text))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parser_subcommands() -> set[str]:
    for action in _build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):  # pyright: ignore[reportPrivateUsage]
            return set(action.choices)
    raise AssertionError("у lnt.cli нет subparsers")


def test_ripple_registered_in_parser_and_cli_spec() -> None:
    # Then: подкоманда зарегистрирована и в парсере, и в каноническом списке.
    assert "ripple" in CLI_SUBCOMMANDS
    assert "ripple" in _parser_subcommands()


def test_happy_direct_path_writes_sidecar_additively(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: синтетическая сессия с известной аналитикой.
    session = _write_session(tmp_path / "meas", "ripple-cli-happy")
    manifest_before = _file_sha256(session / "manifest.json")
    ch1_before = _file_sha256(session / "ch1.npy")

    # When
    code, out, err = _run(capsys, ["ripple", str(session), *_BANDED])

    # Then: exit 0, сайдкар написан, существующие байты не тронуты.
    assert code == EXIT_OK
    assert err == ""
    payload = _sidecar_payload(session)
    assert payload["schema_version"] == 1
    session_block = cast("dict[str, object]", payload["session"])
    assert session_block["session_id"] == "ripple-cli-happy"
    time_domain = cast("dict[str, object]", payload["time_domain"])
    assert time_domain["availability"] == "available"
    assert cast("float", time_domain["rms_ac_v"]) == pytest.approx(
        _AMPLITUDE_V / math.sqrt(2.0), rel=1e-5
    )
    options = cast("dict[str, object]", payload["options"])
    assert (options["band_low_hz"], options["band_high_hz"]) == (99.0, 101.0)
    assert _file_sha256(session / "manifest.json") == manifest_before
    assert _file_sha256(session / "ch1.npy") == ch1_before
    # Свод: имя сайдкара — машинный артефакт, не проверяется прозой.
    assert "ripple.json" in out


def test_happy_resolves_session_id_under_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: каталог сессии с именем, отличным от manifest session_id.
    _write_session(tmp_path / "sess-alpha", "rid-0001")

    # When: ключ — session_id из манифеста.
    code, _, err = _run(capsys, ["ripple", "rid-0001", "--root", str(tmp_path), *_BANDED])

    # Then: сайдкар попал в реальный каталог сессии.
    assert code == EXIT_OK
    assert err == ""
    assert (tmp_path / "sess-alpha" / "ripple.json").is_file()


def test_baseline_is_comparison_only_never_subtracted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: измерение и фон одной геометрии; измерение уже посчитано.
    measurement = _write_session(tmp_path / "meas", "ripple-cli-base")
    background = _write_session(tmp_path / "bg", "ripple-cli-bg")
    _run(capsys, ["ripple", str(measurement), *_BANDED])
    without_baseline = cast("dict[str, object]", _sidecar_payload(measurement)["time_domain"])

    # When: повтор с явным фоном и объявлением короткого замыкания наконечника.
    code, _, err = _run(
        capsys,
        [
            "ripple",
            str(measurement),
            *_BANDED,
            "--baseline",
            str(background),
            "--baseline-shorted-tip",
        ],
    )

    # Then: exit 0; фон лежит рядом со СВОИМИ числами; измерение не меняется.
    assert code == EXIT_OK
    assert err == ""
    payload = _sidecar_payload(measurement)
    assert cast("dict[str, object]", payload["time_domain"]) == without_baseline
    baseline = cast("dict[str, object]", payload["baseline"])
    assert baseline["comparison_status"] == "available"
    baseline_time = cast("dict[str, object]", baseline["time_domain"])
    assert baseline_time["availability"] == "available"


def test_missing_session_key_exits_2_one_line_stderr(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: корень без совпадений.
    (tmp_path / "root").mkdir()

    # When
    code, _, err = _run(capsys, ["ripple", "no-such", "--root", str(tmp_path / "root"), *_BANDED])

    # Then: exit 2, одна строка stderr, без traceback.
    assert code == EXIT_INPUT
    assert len(err.splitlines()) == 1
    assert "Traceback" not in err


def test_ambiguous_session_id_exits_2_one_line_stderr(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: два каталога с одним session_id в манифестах.
    _write_session(tmp_path / "amb-1", "amb-id")
    _write_session(tmp_path / "amb-2", "amb-id")

    # When
    code, _, err = _run(capsys, ["ripple", "amb-id", "--root", str(tmp_path), *_BANDED])

    # Then: неоднозначный ключ — типизированный отказ, одна строка.
    assert code == EXIT_INPUT
    assert len(err.splitlines()) == 1
    assert "Traceback" not in err


def test_probe_mismatch_exits_2_with_reason_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: сессия записана с пробником 1x (манифест probe_multiplier=1.0).
    session = _write_session(tmp_path / "meas", "ripple-cli-probe")

    # When: оператор объявил 10x — проверка равенства против манифеста.
    code, _, err = _run(capsys, ["ripple", str(session), *_BANDED, "--probe", "10x"])

    # Then: типизированный отказ exit 2 с машинным кодом причины.
    assert code == EXIT_INPUT
    assert len(err.splitlines()) == 1
    assert "probe_metadata_mismatch" in err
    assert "Traceback" not in err


def test_band_above_nyquist_exits_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: fs=10 кГц, Найквист 5 кГц.
    session = _write_session(tmp_path / "meas", "ripple-cli-band")

    # When: верхняя граница полосы выше fs/2.
    code, _, err = _run(
        capsys,
        ["ripple", str(session), "--band-low", "99.0", "--band-high", "6000.0", "--preconnected"],
    )

    # Then: exit 2, одна строка, машинное имя поля в сообщении.
    assert code == EXIT_INPUT
    assert len(err.splitlines()) == 1
    assert "band_high_hz" in err


def test_band_flags_required_exits_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: сессия без флагов полосы.
    session = _write_session(tmp_path / "meas", "ripple-cli-noband")

    # When
    code, _, err = _run(capsys, ["ripple", str(session), "--preconnected"])

    # Then: парсер требует полосу, отказ типизированный.
    assert code == EXIT_INPUT
    assert len(err.splitlines()) == 1


def test_directory_without_manifest_exits_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: каталог без manifest.json.
    empty = tmp_path / "empty"
    empty.mkdir()

    # When
    code, _, err = _run(capsys, ["ripple", str(empty), *_BANDED])

    # Then
    assert code == EXIT_INPUT
    assert len(err.splitlines()) == 1
    assert "Traceback" not in err


def test_corrupt_channel_file_exits_2_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: корректная сессия с битым файлом канала.
    session = _write_session(tmp_path / "meas", "ripple-cli-corrupt")
    (session / "ch1.npy").write_bytes(b"not-a-npy-file")

    # When
    code, _, err = _run(capsys, ["ripple", str(session), *_BANDED])

    # Then: испорченный вход — типизированный отказ без traceback.
    assert code == EXIT_INPUT
    assert len(err.splitlines()) == 1
    assert "Traceback" not in err


def test_internal_error_exits_1_one_line_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: сессия и саботаж движка внутренним отказом.
    session = _write_session(tmp_path / "meas", "ripple-cli-internal")

    def _boom(_request: object) -> object:
        raise RuntimeError("внутренний сбой\nвторая строка")

    monkeypatch.setattr("lnt._cli_ripple.run_ripple", _boom)

    # When
    code, _, err = _run(capsys, ["ripple", str(session), *_BANDED])

    # Then: exit 1, ровно одна строка stderr, traceback не утёк.
    assert code == 1
    assert len(err.splitlines()) == 1
    assert "Traceback" not in err


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--cap-nf", "0"],
        ["--cap-nf", "abc"],
        ["--no-such-flag"],
        ["--baseline-shorted-tip"],
    ],
)
def test_invalid_flag_combinations_exit_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    extra_args: list[str],
) -> None:
    # Given: корректная сессия.
    session = _write_session(tmp_path / "meas", "ripple-cli-flags")

    # When: невалидные флаги или их сочетания.
    code, _, err = _run(capsys, ["ripple", str(session), *_BANDED, *extra_args])

    # Then: exit 2, одна строка stderr.
    assert code == EXIT_INPUT
    assert len(err.splitlines()) == 1
    assert "Traceback" not in err
