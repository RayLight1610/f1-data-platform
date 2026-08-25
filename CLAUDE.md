# F1 Data Platform — Agent Instructions

Roadmap, phases and decision log: PROJECT_STRUCTURE.md
Data profiling findings: notebooks/01_explore_bronze.ipynb
Neither is guaranteed current — verify against the code.

## Environment
- Python 3.13, dependencies managed with `uv` ONLY. Never `pip`, never `poetry`.
- Add a dependency: `uv add <pkg>` / `uv add --dev <pkg>`. Never hand-edit pyproject deps.
- PostgreSQL 18, database `f1_data`, app user `f1_app`. Config from .env only (see .env.example).
- Package is installed as `f1_platform` (src layout). Import as `from f1_platform...`,
  NEVER as `from src.f1_platform...`.

## Commands
- Install:  `uv sync`
- Tests:    `uv run pytest -q`
- Lint:     `uv run ruff check .`
- Format:   `uv run ruff format .`
- Types:    `uv run mypy`

## Hard rules
- NEVER commit .env, credentials, or connection strings.
- NEVER add a dependency without asking first.
- NEVER run a script that writes to the database. Propose the command; the user runs it.
- NEVER edit files under cache/ or data/.

## Medallion rules
- bronze: raw payload, original column names (PascalCase from FastF1), plus
  ingestion metadata only. No cleaning, no filtering, no type coercion in bronze.
- silver: typed, deduplicated, validated. UTC timestamps. All business logic here.
- gold: derived from silver only, never from bronze.
- Every load must be idempotent AND atomic: an interrupted run must leave the
  table either unchanged or fully loaded, never partially.
- FastF1 pulls from the Jolpica API (Ergast was shut down in early 2025).
  Assume rate limiting (~200 req/hour) and design for resume-after-failure.

## SQL conventions
- Explicit column lists. No `SELECT *` outside notebooks.
- Every silver/gold table needs DDL under sql/<layer>/ and an explicit grain.
- All timestamps stored as `timestamptz` in UTC.
- Name every constraint and index explicitly.

## Known data quirks (do not rediscover these)
- FastF1 timedelta columns arrive as int64 nanoseconds; NaT becomes the sentinel
  -9223372036854775808. Silver must convert these to NULL, then to seconds.
- `IsPersonalBest` arrives as object, not bool. `DriverNumber` arrives as object.

## Definition of done
Lint, types and tests pass, and new behaviour has a test.
Report the actual command output, not a summary of it.

## When unsure
Stop and ask. Do not guess, do not widen the scope of a change.