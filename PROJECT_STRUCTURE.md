# F1 Data Platform — Project Structure & Roadmap

This document tracks the structural decisions, current state, and upcoming milestones for the `f1-data-platform` project. It is a living document — update it as the project evolves.

---

## Project Goal

Build a Data Engineering platform that ingests Formula 1 data from multiple sources (FastF1 API, Ergast API, Wikipedia), transforms it through a Medallion architecture (Bronze → Silver → Gold), and serves it to downstream consumers (visualizations, RAG agent, ML predictions).

**Target audience:** F1 fans + technical demonstration of Data Engineering skills aligned with 2026 industry expectations.

**Timeline:** MVP in 2-3 months, full platform iteratively over 6-12 months.

---

## Architecture Overview

```
SOURCES                  →  BRONZE              →  SILVER         →  GOLD            →  PRESENTATION
─────────                   ──────                 ──────            ────                ────────────
FastF1 API ✓                raw_laps ✓             clean_laps        fact_results        Visualizations
Jolpica-F1 API              raw_results ✓          clean_results     dim_drivers         RAG Chatbot (Phase 3)
F1 Official site            raw_weather ✓          clean_telemetry   agg_standings       ML Predictions (Phase 5)
Wikipedia (text)            raw_telemetry ✓        embeddings (pgVector — Phase 3)
```

**Storage:** PostgreSQL 18, with separate schemas per Medallion layer:
- `bronze` — raw data, untransformed (✓ implemented)
- `silver` — cleaned, typed, deduplicated (next)
- `gold` — aggregations, ready for analytics
- `embeddings` — pgVector tables (Phase 3)

---

## Current State

### Environment

| Component | Version / Status |
|---|---|
| Python | 3.13+ |
| Package manager | `uv` 0.11.3 |
| Database | PostgreSQL 18 (local) — `f1_data` database |
| DB users | `postgres` (superuser), `f1_app` (application) |
| IDE | VS Code |
| Repository | GitHub `RayLight1610/f1-data-platform` (public) |

### Installed Dependencies

```toml
dependencies = [
    "fastf1>=3.8.2",            # F1 data extraction
    "pandas>=2.3.3",            # Data manipulation
    "psycopg2-binary>=2.9.12",  # PostgreSQL driver
    "sqlalchemy>=2.0.49",       # DB abstraction layer
    "python-dotenv>=1.2.2",     # Environment variable management
]
```

### Files Created

```
f1-data-platform/
├── .env                          # DB credentials (gitignored)
├── .gitignore
├── .python-version
├── README.md
├── PROJECT_STRUCTURE.md
├── pyproject.toml
├── uv.lock
├── main.py                       # Pipeline entry point
│
├── src/f1_platform/
│   ├── __init__.py
│   ├── bronze/
│   │   ├── __init__.py
│   │   └── ingest_fastf1.py     # ✓ 4 ingestion functions + season loader
│   ├── silver/                   # (empty — next phase)
│   ├── gold/                     # (empty)
│   ├── db/
│   │   ├── __init__.py
│   │   └── connection.py        # ✓ get_engine() with .env support
│   └── utils/                    # (empty)
│
├── sql/
│   ├── bronze/                   
│   ├── silver/
│   └── gold/
│
├── notebooks/                    
├── tests/                        # (not tracked)
└── cache/                        # FastF1 cached data (not tracked)
```

### Bronze Layer — Implemented ✓

**Module:** `src/f1_platform/bronze/ingest_fastf1.py`

**Helper functions:**
- `load_session(year, event)` — wrapper around FastF1 session loading
- `add_metadata_columns(df)` — adds `ingested_at` + `source` columns
- `already_ingested(table, year, event, engine)` — idempotency check

**Ingestion functions (all with idempotency, error handling, logging):**
- `ingest_race_laps(year, event, mode)` → `bronze.raw_laps`
- `ingest_race_results(year, event, mode)` → `bronze.raw_results`
- `ingest_race_weather(year, event, mode)` → `bronze.raw_weather`
- `ingest_race_telemetry(year, event, mode)` → `bronze.raw_telemetry` (fastest lap only)

**Bulk loader:**
- `ingest_season(year)` — iterates through full season schedule, calls all 4 ingestions per race, with try/except per event

**Data loaded:**
- Full 2025 season (24 races)
- Partial 2026 (Australia, China, Japan)

---

## Roadmap — Aligned with 2026 Data Engineering Standards

### Phase 1 — MVP (Months 1-3)

| Status | Milestone | Skills Practiced |
|---|---|---|
| ✓ | Project structure + DB setup + first connection | PostgreSQL, SQLAlchemy, env config, .gitignore |
| ✓ | Bronze layer — FastF1 ingestion (4 tables, full season) | Python, API integration, pandas, idempotency, logging |
| **next** | Jupyter exploration — analyze Bronze data quality | pandas analysis, data profiling |
| | Silver layer — clean transformations (SQL-first) | SQL transformations, type casting, normalization |
| | Gold layer — aggregations | Star schema, fact/dim tables, window functions |
| | Visualizations — 3-4 key charts | matplotlib/plotly basics |
| | Orchestration + polish | Single entry point, robust logging |

**Phase 1 deliverable:** `python main.py` runs the full pipeline; visualizations produced; CV-ready repo.

### Phase 2 — Modern DE Tooling (Months 3-4)

| Tool | Purpose | Time |
|---|---|---|
| **dbt** | Replace manual SQL with declarative models | 1-2 weeks |
| **Docker** | Containerize the application | 1 week |
| **pytest + Great Expectations** | Data quality tests | 1 week |
| **SCD Type 2** | Schema evolution in Silver | 1 week |

### Phase 3 — AI Layer (Months 4-7)

| Component | Purpose |
|---|---|
| **pgVector** | Vector search extension |
| **Wikipedia ingestion** | Text data for RAG context |
| **F1 Analyst chatbot** | RAG agent with LLM |

### Phase 4 — Production-Grade (Months 7-9)

| Tool | Purpose |
|---|---|
| **Airflow** | Proper DAG orchestration |
| **Cloud** (Supabase / AWS RDS free tier) | Move PostgreSQL to cloud |
| **CI/CD** | GitHub Actions for tests + deploy |

### Phase 5 — Scale & ML (Months 9-12)

| Tool | Purpose |
|---|---|
| **Databricks Community Edition** | PySpark + Mosaic AI experimentation |
| **scikit-learn** | Race outcome prediction models |

### Explicitly Out of Scope

- Kafka / streaming (overkill for batch F1 data)
- Snowflake / BigQuery (PostgreSQL sufficient for MVP)
- Kubernetes (too advanced for first project)

---

## Git Workflow

**Branching:** `main` for MVP phase. Feature branches introduced when working on parallel features (Phase 2+).

**Commit conventions:**
- One logical change per commit
- Imperative mood: "Add Bronze ingestion" not "Added Bronze ingestion"
- Reference layer when relevant: "Bronze: ingest FastF1 race results"

**Commit checkpoints (in practice):**
- After folder structure creation ✓
- After each new dependency added ✓
- After each working script per layer ✓
- After tests added
- After documentation updates ✓

---

## Decision Log

| Decision | Rationale |
|---|---|
| PostgreSQL over SQL Server | Industry standard for DE; pgVector support; free |
| `uv` over pip + venv | 10x faster, deterministic locking, modern standard |
| Single-DB Medallion (separate schemas) vs separate DBs | Simpler for MVP; layer separation via schema prefixes |
| SQL-first, Python where necessary | Leverage 15 yrs SQL Server experience |
| Bronze keeps raw column names (PascalCase from FastF1) | Bronze principle: untransformed data; normalization happens in Silver |
| dbt added to scope | Critical 2026 DE skill, low cost to integrate |
| Databricks deferred to Phase 5 | Community Edition limited; PostgreSQL sufficient initially |
| Idempotency check via SELECT before INSERT | Safe re-runs; production-grade pattern |
| `f1_app` user instead of `postgres` superuser | Security best practice; minimal privileges |

---

## Learning Resources Referenced

- **Designing Data-Intensive Applications** — Martin Kleppmann (architectural intuition)
- **The Fundamentals of Data Engineering** — Joe Reis (DE concepts)
- **dbt Learn** — official dbt courses
- **DP-800** — Microsoft SQL AI Developer Associate (parallel certification track)

---

## Known Issues / Technical Debt

- `logging.basicConfig()` should be centralized (currently set in `main.py`)
- No automated tests yet
- `cache/` size grows quickly — consider periodic cleanup strategy
- `if_exists="append"` allows duplicates if idempotency check is bypassed — Silver layer should deduplicate
- Dev tooling added 2026-08: ruff, pytest, mypy (lenient config; tighten with Silver).
- FIXED 2026-08: package was imported as both `f1_platform` and `src.f1_platform`.
  Canonical import is `f1_platform` (src layout, installed via hatchling).

---

*Last updated: After Bronze layer completion (full 2025 season + partial 2026)*
