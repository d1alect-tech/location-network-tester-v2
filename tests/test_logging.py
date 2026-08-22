"""Тесты структурного журнала: ротация, редакция, корреляция, валидность JSON."""

import json
import logging
from pathlib import Path

from lnt.config.model import LoggingSettings
from lnt.logging import JsonLinesFormatter, attach_file_logging, correlation_scope

_REDACTED = {"redacted": True}


def _record(**extra: object) -> logging.LogRecord:
    """Создаёт запись журнала с произвольными extra-полями (враждебные фикстуры)."""
    record = logging.LogRecord(
        name="lnt.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="сообщение оператора",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _fields(formatted: str) -> dict[str, object]:
    payload = json.loads(formatted)
    assert isinstance(payload, dict)
    fields = payload["fields"]
    assert isinstance(fields, dict)
    return fields


def test_format_when_extra_smuggles_samples_and_identity_redacts_them() -> None:
    formatter = JsonLinesFormatter()

    formatted = formatter.format(
        _record(
            samples=[0.1, 0.2, 0.3],
            ch1_waveform="сырые отсчёты",
            hostname="рабочая-станция",
            username="оператор",
            location_alias="дом-квартира",
            notes="личная заметка",
            innocent="безобидное поле",
        ),
    )

    fields = _fields(formatted)
    assert fields["innocent"] == "безобидное поле"
    assert fields["samples"] == _REDACTED | {"reason": "raw_capture_samples"}
    assert fields["ch1_waveform"] == _REDACTED | {"reason": "raw_capture_samples"}
    assert fields["hostname"] == _REDACTED | {"reason": "host_or_user_identity"}
    assert fields["username"] == _REDACTED | {"reason": "host_or_user_identity"}
    assert fields["location_alias"] == _REDACTED | {"reason": "private_user_metadata"}
    assert fields["notes"] == _REDACTED | {"reason": "private_user_metadata"}


def test_format_when_numeric_array_hidden_under_innocent_key_is_redacted() -> None:
    formatter = JsonLinesFormatter()

    formatted = formatter.format(
        _record(values=[float(i) for i in range(32)], short=[1, 2, 3]),
    )

    fields = _fields(formatted)
    assert fields["values"] == _REDACTED | {"reason": "numeric_array_as_samples"}
    assert fields["short"] == [1, 2, 3]


def test_format_when_private_metadata_explicitly_allowed_keeps_only_it() -> None:
    formatter = JsonLinesFormatter(redact_private_metadata=False)

    formatted = formatter.format(
        _record(location_alias="дом", samples=[1.0], hostname="станция"),
    )

    fields = _fields(formatted)
    assert fields["location_alias"] == "дом"
    assert fields["samples"] == _REDACTED | {"reason": "raw_capture_samples"}
    assert fields["hostname"] == _REDACTED | {"reason": "host_or_user_identity"}


def test_format_when_nested_structure_hides_private_fields_redacts_deeply() -> None:
    formatter = JsonLinesFormatter()

    formatted = formatter.format(
        _record(operation={"step": 2, "label": "до обеда", "counts": [1, 2, 3]}),
    )

    fields = _fields(formatted)
    operation = fields["operation"]
    assert operation == {
        "step": 2,
        "label": _REDACTED | {"reason": "private_user_metadata"},
        "counts": [1, 2, 3],
    }


def test_correlation_ids_present_inside_scope_and_none_outside() -> None:
    formatter = JsonLinesFormatter()

    with correlation_scope(job_id="job-1", session_id="sess-2", request_id="req-3"):
        inside = json.loads(formatter.format(_record()))
    outside = json.loads(formatter.format(_record()))

    assert inside["job_id"] == "job-1"
    assert inside["session_id"] == "sess-2"
    assert inside["request_id"] == "req-3"
    assert outside["job_id"] is None
    assert outside["session_id"] is None
    assert outside["request_id"] is None


def test_format_when_values_are_hostile_still_produces_valid_json_line() -> None:
    formatter = JsonLinesFormatter()

    hostile = formatter.format(_record(broken=set(), nan_value=float("nan")))
    multiline = formatter.format(_record(other=_record.__doc__))

    for line in (hostile, multiline):
        assert "\n" not in line.strip("\n")
        json.loads(line)


def test_rotation_by_size_and_count_keeps_bounded_files(tmp_path: Path) -> None:
    settings = LoggingSettings(max_bytes=400, backup_count=2)
    logger = logging.getLogger("lnt.rotation-test")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = attach_file_logging(tmp_path, settings, logger=logger)
    try:
        for index in range(60):
            logger.info("запись ротации %03d %s", index, "x" * 40)
    finally:
        logger.removeHandler(handler)
        handler.close()

    rolled = sorted(path.name for path in tmp_path.glob("lnt.log.jsonl*"))
    assert rolled == ["lnt.log.jsonl", "lnt.log.jsonl.1", "lnt.log.jsonl.2"]
    for name in rolled:
        for line in (tmp_path / name).read_text(encoding="utf-8").splitlines():
            json.loads(line)


def test_attach_when_log_file_contains_garbage_still_appends(tmp_path: Path) -> None:
    (tmp_path / "lnt.log.jsonl").write_bytes(b"\xff\xfe\x00broken-bytes\n")
    settings = LoggingSettings()
    logger = logging.getLogger("lnt.garbage-test")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = attach_file_logging(tmp_path, settings, logger=logger)
    try:
        logger.info("запись после мусора")
    finally:
        logger.removeHandler(handler)
        handler.close()

    lines = (
        (tmp_path / "lnt.log.jsonl")
        .read_bytes()
        .decode(encoding="utf-8", errors="replace")
        .splitlines()
    )
    payload = json.loads(lines[-1])
    assert payload["message"] == "запись после мусора"
