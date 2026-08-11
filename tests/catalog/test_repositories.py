"""CRUD-контракты типизированных SQL-репозиториев каталога."""

from pathlib import Path

from lnt.catalog import (
    ArtifactRecipe,
    CatalogRepositories,
    ContextField,
    Experiment,
    ExperimentMember,
    SessionProjection,
    apply_migrations,
    writer_transaction,
)


def test_repository_crud_round_trips_all_projections(tmp_path: Path) -> None:
    # Given
    catalog_path = tmp_path / "catalog.sqlite3"
    apply_migrations(catalog_path)
    session = SessionProjection(
        id="session-1",
        storage_path="D:/evidence/session-1",
        path_fingerprint="sha256:path-one",
        health="valid",
        manifest_schema=2,
        created_utc="2026-08-11T12:00:00Z",
        source="device",
        session_type="measurement",
        profile=None,
        sample_rate_hz=500_000.0,
        duration_s=2.4,
        sample_count=1_200_000,
        label="стол A",
        channels="dual",
    )
    recipe = ArtifactRecipe(
        recipe_sha256="a" * 64,
        session_id=session.id,
        artifact_key="default",
        storage_ref="analyses/default",
    )
    experiment = Experiment(
        id="experiment-1",
        storage_ref="experiments/experiment-1",
        health="valid",
    )
    member = ExperimentMember(
        experiment_id=experiment.id,
        ordinal=0,
        session_id=session.id,
        session_storage_ref=session.storage_path,
        artifact_key=recipe.artifact_key,
        recipe_sha256=recipe.recipe_sha256,
    )

    # When
    with writer_transaction(catalog_path) as connection:
        repositories = CatalogRepositories(connection)
        repositories.sessions.upsert(session)
        repositories.context.replace(
            session.id,
            fields=(ContextField(session.id, "room", "lab"),),
            tags=("baseline", "mains"),
        )
        repositories.artifacts.upsert(recipe)
        repositories.experiments.upsert(experiment)
        repositories.experiments.replace_members(experiment.id, (member,))
        actual = (
            repositories.sessions.get(session.id),
            repositories.context.fields(session.id),
            repositories.context.tags(session.id),
            repositories.artifacts.for_session(session.id),
            repositories.experiments.get(experiment.id),
            repositories.experiments.members(experiment.id),
        )

    # Then
    assert actual == (
        session,
        (ContextField(session.id, "room", "lab"),),
        ("baseline", "mains"),
        (recipe,),
        experiment,
        (member,),
    )


def test_repository_delete_cascades_projection_children(tmp_path: Path) -> None:
    # Given
    catalog_path = tmp_path / "catalog.sqlite3"
    apply_migrations(catalog_path)
    session = SessionProjection.minimal(
        id="gone",
        storage_path="D:/gone",
        path_fingerprint="fp-gone",
        health="missing",
    )

    # When
    with writer_transaction(catalog_path) as connection:
        repositories = CatalogRepositories(connection)
        repositories.sessions.upsert(session)
        repositories.context.replace(session.id, fields=(), tags=("temporary",))
        repositories.sessions.delete(session.id)
        result = repositories.sessions.get(session.id), repositories.context.tags(session.id)

    # Then
    assert result == (None, ())
