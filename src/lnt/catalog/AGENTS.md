# src/lnt/catalog — rebuildable SQLite index

## OVERVIEW

18 modules: the only SQLite surface in the repo. A rebuildable projection over sessions/experiments — never the source of truth.

## WHERE TO LOOK

| Task | Location |
|---|---|
| Public API (`__init__.py`) | `CatalogRepositories`, `SessionProjection`, `Experiment`, `ExperimentMember`, `ContextField`, `ArtifactRecipe`, `apply_migrations`, `open_catalog_reader`, `writer_transaction`, `CatalogBusyError`, `CatalogDowngradeError` |
| CLI | `cli.py` — `lnt catalog status\|reindex\|verify [--deep]\|import-context --dry-run`; `automation_cli.py` — top-level `sessions` / `context` / `profiles` / `reindex` groups |
| Reader | `connection.py` (read-only URI) + `query_repository.py` / `query_models.py` |
| Writer | `lock.py` + `session_repositories.py` / `evidence_repositories.py` |
| Schema | `migrations.py` — one explicit ordered `MIGRATIONS` tuple holds all DDL |
| Reconcile | `reconcile.py` / `reconcile_models.py` (`reconcile_catalog`, `verify_catalog`, `catalog_status`) |

## CONVENTIONS

- Every connection: `PRAGMA foreign_keys = ON`, `busy_timeout = 5000` (`DEFAULT_BUSY_TIMEOUT_MS`), `journal_mode = WAL`, custom deterministic SQL function `casefold`.
- Reader opens strictly read-only: `file:…?mode=ro` URI.
- Writer = `O_EXCL` lockfile (default 5 s, `CatalogBusyError` on timeout) + `BEGIN IMMEDIATE`, rollback in `finally`; lock file removed after the write.
- Migrations are forward-only; downgrade raises `CatalogDowngradeError`.
- DB path defaults to `resolve_app_paths().catalog_db` (LocalAppData), overridable via CLI `--database`.
- Consumers: `src/lnt/cli.py`, `session_projection.py`, `ui/{api_support,app,models_catalog,routes_catalog}.py`.

## ANTI-PATTERNS

- The catalog is a projection — sessions on disk remain the truth; repair via `reindex`, never by editing the DB.
- No raw SQL outside repositories/migrations.
- Catalog IDs are opaque case-sensitive ASCII (ADR-0007); new generated IDs are lowercase UUIDv7 text.
