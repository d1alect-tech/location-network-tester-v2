"""Контракт одного writer и параллельных WAL-reader процессов."""

import subprocess
import sys
from pathlib import Path

import pytest

from lnt.catalog import (
    CatalogBusyError,
    apply_migrations,
    open_catalog_reader,
    writer_transaction,
)


def test_reader_observes_committed_snapshot_during_writer(tmp_path: Path) -> None:
    # Given
    catalog_path = tmp_path / "catalog.sqlite3"
    apply_migrations(catalog_path)
    with writer_transaction(catalog_path) as connection:
        connection.execute(
            """INSERT INTO sessions (id, storage_path, path_fingerprint, health)
            VALUES ('before', 'D:/sessions/before', 'fp-before', 'valid')""",
        )

    # When
    with writer_transaction(catalog_path) as writer:
        writer.execute(
            """INSERT INTO sessions (id, storage_path, path_fingerprint, health)
            VALUES ('pending', 'D:/sessions/pending', 'fp-pending', 'valid')""",
        )
        with open_catalog_reader(catalog_path) as reader:
            ids = [row[0] for row in reader.execute("SELECT id FROM sessions ORDER BY id")]

    # Then
    assert ids == ["before"]


def test_two_process_writers_contend_without_corruption(tmp_path: Path) -> None:
    # Given
    catalog_path = tmp_path / "catalog.sqlite3"
    apply_migrations(catalog_path)
    child_code = (
        "import sys\n"
        "from pathlib import Path\n"
        "from lnt.catalog import CatalogBusyError, writer_transaction\n"
        "try:\n"
        "    with writer_transaction(Path(sys.argv[1]), lock_timeout_s=0): pass\n"
        "except CatalogBusyError as error:\n"
        "    print(error.reason_code)\n"
        "    raise SystemExit(23)\n"
    )

    # When
    with writer_transaction(catalog_path):
        result = subprocess.run(
            [sys.executable, "-c", child_code, str(catalog_path)],
            check=False,
            capture_output=True,
            text=True,
        )

    # Then
    assert result.returncode == 23
    assert result.stdout.strip() == "catalog_busy"
    with open_catalog_reader(catalog_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_writer_lock_error_is_actionable_and_typed(tmp_path: Path) -> None:
    # Given
    catalog_path = tmp_path / "catalog.sqlite3"
    apply_migrations(catalog_path)

    # When / Then
    with (
        writer_transaction(catalog_path),
        pytest.raises(CatalogBusyError) as raised,
        writer_transaction(catalog_path, lock_timeout_s=0),
    ):
        pytest.fail("второй writer не должен получить транзакцию")
    assert raised.value.reason_code == "catalog_busy"
    assert "закройте другую операцию" in str(raised.value)
