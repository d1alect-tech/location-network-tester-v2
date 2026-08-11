# /// script
# requires-python = ">=3.12"
# ///
# ─── How to run ───
# uv run python benchmarks/baseline.py --json <output.json>
# uv run python benchmarks/baseline.py --self-check
"""Measure the recovered LNT behavior without retaining synthetic sessions."""

from __future__ import annotations

import argparse
import ctypes
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Final, Literal, Protocol, TypedDict

from starlette.testclient import TestClient

from lnt.ui.app import create_app
from lnt.ui.sessions import list_sessions

ROOT: Final = Path(__file__).resolve().parent
SCHEMA_PATH: Final = ROOT / "schema.json"
FIXTURE_PATH: Final = ROOT / "fixtures" / "baseline.json"
PACKAGE_NAMES: Final = ("lnt", "numpy", "scipy", "fastapi", "starlette", "uvicorn")
CLI_PREFIX: Final = (
    sys.executable,
    "-c",
    "from lnt.cli import main; raise SystemExit(main())",
)
FAILURE_EXIT_CODE: Final = 7
HTTP_OK: Final = 200
Status = Literal["passed", "failed"]


class Fixture(TypedDict):
    """Trusted benchmark fixture parsed from the checked-in JSON file."""

    profile_a: str
    profile_b: str
    duration_seconds: float
    sample_rate_hz: int
    seed_a: int
    seed_b: int


class Environment(TypedDict):
    """Host and dependency identity for a baseline run."""

    os: str
    cpu: str
    ram_bytes: int
    python: str
    packages: dict[str, str]


class Baseline(TypedDict):
    """Serializable top-level baseline document."""

    schema_version: int
    environment: Environment
    measurements: list[MeasurementPayload]


class MeasurementPayload(TypedDict):
    """JSON-compatible representation of one measurement."""

    name: str
    seconds: float
    status: Status
    exit_code: int | None
    detail: str


class Operation(Protocol):
    """In-process benchmark operation."""

    def __call__(self) -> str:
        """Run the operation and return its success detail."""
        ...


@dataclass(frozen=True, slots=True)
class Measurement:
    """One timed operation and its observable outcome."""

    name: str
    seconds: float
    status: Status
    exit_code: int | None
    detail: str


def _ram_bytes() -> int:
    if platform.system() == "Windows":
        installed_kib = ctypes.c_ulonglong()
        if ctypes.windll.kernel32.GetPhysicallyInstalledSystemMemory(ctypes.byref(installed_kib)):
            return int(installed_kib.value * 1024)
    page_size = int(os.sysconf("SC_PAGE_SIZE"))
    pages = int(os.sysconf("SC_PHYS_PAGES"))
    return page_size * pages


def _environment() -> Environment:
    packages = {name: importlib.metadata.version(name) for name in PACKAGE_NAMES}
    return {
        "os": platform.platform(),
        "cpu": platform.processor() or "unknown",
        "ram_bytes": _ram_bytes(),
        "python": platform.python_version(),
        "packages": packages,
    }


def record_command(name: str, command: tuple[str, ...]) -> Measurement:
    """Run a command and derive status exclusively from its exit code."""
    started = perf_counter()
    completed = subprocess.run(  # noqa: S603 - commands are constructed from trusted fixtures.
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    seconds = perf_counter() - started
    output = (completed.stdout + completed.stderr).strip().splitlines()
    return Measurement(
        name=name,
        seconds=seconds,
        status="passed" if completed.returncode == 0 else "failed",
        exit_code=completed.returncode,
        detail=output[-1] if output else "",
    )


def record_callable(name: str, operation: Operation) -> Measurement:
    """Time an in-process operation whose return value describes success."""
    started = perf_counter()
    detail = operation()
    return Measurement(name, perf_counter() - started, "passed", None, detail)


def failure_guard() -> Measurement:
    """Prove that a deliberately failing process cannot be recorded as passed."""
    measured = record_command(
        "deliberate_failure",
        (sys.executable, "-c", f"raise SystemExit({FAILURE_EXIT_CODE})"),
    )
    if measured.status == "passed" or measured.exit_code != FAILURE_EXIT_CODE:
        raise AssertionError("non-zero command was not retained as a failure")
    return measured


def _load_fixture() -> Fixture:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return Fixture(
        profile_a=str(raw["profile_a"]),
        profile_b=str(raw["profile_b"]),
        duration_seconds=float(raw["duration_seconds"]),
        sample_rate_hz=int(raw["sample_rate_hz"]),
        seed_a=int(raw["seed_a"]),
        seed_b=int(raw["seed_b"]),
    )


def _simulate_command(
    session: Path,
    fixture: Fixture,
    *,
    profile_key: Literal["profile_a", "profile_b"],
    seed_key: Literal["seed_a", "seed_b"],
) -> tuple[str, ...]:
    return (
        *CLI_PREFIX,
        "simulate",
        "--profile",
        fixture[profile_key],
        "--out",
        str(session),
        "--duration",
        str(fixture["duration_seconds"]),
        "--rate",
        str(fixture["sample_rate_hz"]),
        "--seed",
        str(fixture[seed_key]),
    )


def _payload(measurement: Measurement) -> MeasurementPayload:
    return {
        "name": measurement.name,
        "seconds": measurement.seconds,
        "status": measurement.status,
        "exit_code": measurement.exit_code,
        "detail": measurement.detail,
    }


def run_baseline() -> Baseline:
    """Run all measurements under a temporary root that is deleted on exit."""
    fixture = _load_fixture()
    failure_guard()
    measurements: list[Measurement] = []
    with tempfile.TemporaryDirectory(prefix="lnt-baseline-") as temporary:
        root = Path(temporary)
        session_a, session_b = root / "session-a", root / "session-b"
        measurements.append(
            record_command(
                "simulate",
                _simulate_command(session_a, fixture, profile_key="profile_a", seed_key="seed_a"),
            )
        )
        measurements.append(
            record_command(
                "simulate_compare_fixture",
                _simulate_command(session_b, fixture, profile_key="profile_b", seed_key="seed_b"),
            )
        )
        measurements.append(record_command("analyze", (*CLI_PREFIX, "analyze", str(session_a))))
        measurements.append(
            record_command(
                "compare",
                (*CLI_PREFIX, "compare", str(session_a), str(session_b)),
            )
        )
        measurements.append(
            record_callable("session_listing", lambda: f"sessions={len(list_sessions(root))}")
        )

        def ui_health() -> str:
            with TestClient(create_app(root=root)) as client:
                response = client.get("/api/health")
            if response.status_code != HTTP_OK or response.json() != {"status": "ok"}:
                raise AssertionError(f"unexpected UI health response: {response.status_code}")
            return f"http_status={response.status_code}"

        measurements.append(record_callable("ui_health_startup", ui_health))
    return {
        "schema_version": 1,
        "environment": _environment(),
        "measurements": [_payload(item) for item in measurements],
    }


def validate_against_schema(document: Baseline) -> None:
    """Validate the emitted shape against the checked-in schema contract."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    required = set(schema["required"])
    expected_version = schema["properties"]["schema_version"]["const"]
    if set(document) != required or document["schema_version"] != expected_version:
        raise AssertionError("baseline top-level shape does not match schema")
    environment_required = set(schema["properties"]["environment"]["required"])
    environment_matches = set(document["environment"]) == environment_required
    if not environment_matches or document["environment"]["ram_bytes"] <= 0:
        raise AssertionError("environment does not match schema")
    minimum = int(schema["properties"]["measurements"]["minItems"])
    item_required = set(schema["properties"]["measurements"]["items"]["required"])
    status_schema = schema["properties"]["measurements"]["items"]["properties"]["status"]
    allowed_statuses = set(status_schema["enum"])
    if len(document["measurements"]) < minimum:
        raise AssertionError("measurement array is shorter than schema minimum")
    for item in document["measurements"]:
        item_matches = set(item) == item_required and item["status"] in allowed_statuses
        if not item_matches or item["seconds"] < 0:
            raise AssertionError(f"measurement does not match schema: {item['name']}")


def main() -> int:
    """Parse arguments, run measurements, validate, and write JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        sys.stdout.write(json.dumps(_payload(failure_guard()), indent=2) + "\n")
        return 0
    if args.json is None:
        parser.error("--json is required unless --self-check is used")
    document = run_baseline()
    validate_against_schema(document)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return 0 if all(item["status"] == "passed" for item in document["measurements"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
