import json
from pathlib import Path

import pytest

from lnt.catalog.connection import writer_transaction
from lnt.catalog.migrations import apply_migrations
from lnt.cli import main
from lnt.profiles import LocationProfile, ProfileStore


def test_sessions_context_profiles_and_reindex_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    database = local / "LNT" / "catalog.sqlite3"
    apply_migrations(database)
    session = tmp_path / "sessions" / "known"
    session.mkdir(parents=True)
    with writer_transaction(database) as connection:
        connection.execute(
            """INSERT INTO catalog_sessions(storage_path, session_id, path_fingerprint,
            health, base_health, created_utc) VALUES (?, 'known', 'fp', 'ok', 'ok',
            '2026-01-01T00:00:00Z')""",
            (str(session),),
        )
    ProfileStore(root=local / "LNT" / "support" / "profiles").create(
        "lab", LocationProfile(alias="стенд", outlet="A", circuit="1")
    )

    codes = (
        main(["sessions", "list", "--json"]),
        main(["context", "show", "known", "--json"]),
        main(["context", "set", "known", "--expected-revision", "0", "--tag", "night"]),
        main(["profiles", "list", "--json"]),
        main(["profiles", "show", "lab", "--json"]),
        main(["reindex", "status", "--json"]),
    )
    output = capsys.readouterr().out

    assert codes == (0, 0, 0, 0, 0, 0)
    assert "known" in output
    assert "lab" in output
    assert any(json.loads(line) for line in output.splitlines() if line.startswith("{"))
