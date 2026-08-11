"""Disposable SQLite-проекция sibling-экспериментов."""

import sqlite3
from pathlib import Path

from lnt.context.json_codec import decode_object
from lnt.experiments.model import experiment_from_mapping


def replace_experiment_projection(
    connection: sqlite3.Connection,
    session_root: Path,
) -> None:
    """Перестраивает малую проекцию из канонических experiment.json."""
    connection.execute("DELETE FROM catalog_experiments")
    experiments_root = session_root.parent / "experiments"
    if not experiments_root.is_dir():
        return
    for directory in sorted(experiments_root.iterdir()):
        path = directory / "experiment.json"
        if not directory.is_dir() or ".partial-" in directory.name or not path.is_file():
            continue
        experiment = experiment_from_mapping(
            decode_object(path.read_text(encoding="utf-8"), "experiment.json")
        )
        connection.execute(
            """INSERT INTO catalog_experiments
            (id, storage_ref, title, question, status, protocol, revision, health)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ok')""",
            (
                experiment.experiment_id,
                str(path),
                experiment.title,
                experiment.question,
                experiment.status.value,
                experiment.protocol.kind.value,
                experiment.revision,
            ),
        )
        connection.executemany(
            """INSERT INTO catalog_experiment_members
            (experiment_id, ordinal, session_id, storage_ref, role, condition_id,
             block_key, pairing_key, reference_health)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                (
                    experiment.experiment_id,
                    member.order,
                    member.session_id,
                    member.storage_ref,
                    member.role,
                    member.condition_id,
                    member.block_key,
                    member.pairing_key,
                    "ok" if (session_root / member.storage_ref).is_dir() else "broken_reference",
                )
                for member in experiment.members
            ),
        )
