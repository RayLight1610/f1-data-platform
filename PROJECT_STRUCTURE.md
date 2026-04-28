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
SOURCES                  →  BRONZE         →  SILVER         →  GOLD            →  PRESENTATION
─────────                   ──────            ──────            ────                ────────────
FastF1 API                  raw_laps          clean_laps        fact_results        Visualizations
Ergast API                  raw_results       clean_results     dim_drivers         RAG Chatbot (Phase 2)
F1 Official site            raw_telemetry     clean_telemetry   agg_standings       ML Predictions (Phase 2)
Wikipedia (text)            text_docs         embeddings (pgVector — Phase 2)
```

**Storage:** PostgreSQL (single instance), with table prefixes per layer:
- `bronze_*` — raw data, untransformed
- `silver_*` — cleaned, typed, deduplicated
- `gold_*` — aggregations, ready for analytics
- `embeddings_*` — pgVector tables (Phase 2)

---

## Current State

### Environment

| Component | Version / Status |
|---|---|
| Python | 3.13+ |
| Package manager | `uv` 0.11.3 |
| Database | PostgreSQL (running locally) |
| IDE | VS Code |
| Repository | GitHub `RayLight1610/f1-data-platform` (private) |

### Installed Dependencies

```toml
dependencies = [
    "fastf1>=3.8.2",        # F1 data extraction
    "pandas>=2.3.3",        # Data manipulation
    "psycopg2-binary>=2.9.12",  # PostgreSQL driver
    "sqlalchemy>=2.0.49",   # ORM / DB abstraction
]
```

### Files Created So Far

```
f1-data-platform/
├── .gitignore              # Python + project-specific exclusions
├── README.md               # Project overview
├── pyproject.toml          # Project config + dependencies
├── uv.lock                 # Locked dependency versions
├── .python-version         # Python version marker
└── main.py                 # Default entry point (placeholder)
```

---

## Planned Structure

```
f1-data-platform/
├── .gitignore
├── README.md
├── PROJECT_STRUCTURE.md    # This document
├── pyproject.toml
├── uv.lock
├── main.py                 # Pipeline entry point
│
├── config/                 # Configuration (DB conn, paths)
│   └── settings.py
│
├── src/f1_platform/
│   ├── bronze/             # Raw data ingestion
│   │   └── ingest_fastf1.py
│   ├── silver/             # Cleaned transformations
│   │   └── transform_laps.py
│   ├── gold/               # Aggregations
│   │   └── agg_standings.py
│   ├── db/                 # Database connection helpers
│   │   └── connection.py
│   └── utils/              # Logging, helpers
│       └── logger.py
│
├── sql/                    # SQL DDL + transformations
│   ├── bronze/
│   ├── silver/
│   └── gold/
│
├── notebooks/              # Jupyter exploration
├── tests/                  # Unit tests (pytest)
├── cache/                  # FastF1 cache (gitignored)
└── dbt/                    # dbt project (Phase 2)
```

---

## Roadmap — Aligned with 2026 Data Engineering Standards

### Phase 1 — MVP (Months 1-3)

**Goal:** End-to-end pipeline for one F1 season, demonstrating core DE skills.

| Week | Milestone | Skills Practiced |
|---|---|---|
| 1-2 | Project structure + DB setup + first connection | PostgreSQL, SQLAlchemy, env config |
| 3-4 | Bronze layer — FastF1 ingestion for one race | Python, API integration, pandas, raw storage |
| 5-6 | Silver layer — clean transformations | SQL transformations, type casting, foreign keys |
| 7-8 | Gold layer — aggregations | Star schema, fact/dim tables, window functions |
| 9-10 | Visualizations — 3-4 key charts | matplotlib/plotly basics |
| 11-12 | Orchestration + polish | Logging, error handling, single entry point |

**Phase 1 deliverable:** `python main.py` runs the full pipeline; CSV/visualizations produced; CV-ready GitHub repo.

### Phase 1.5 — Modern DE Tooling (Months 3-4)

| Tool | Purpose | Time Investment |
|---|---|---|
| **dbt** | Replace manual SQL transformations with declarative models | 1-2 weeks |
| **Docker** | Containerize the application | 1 week |
| **pytest + Great Expectations** | Data quality tests | 1 week |
| **SCD Type 2** | Schema evolution in Silver layer | 1 week |

### Phase 2 — Production-Grade (Months 4-6)

| Tool | Purpose |
|---|---|
| **Airflow** | Replace `main.py` with proper DAG orchestration |
| **Cloud** (Supabase / AWS RDS free tier) | Move PostgreSQL to cloud |
| **CI/CD** | GitHub Actions for tests + deploy |

### Phase 3 — AI Layer (Months 6-9)

| Component | Purpose |
|---|---|
| **pgVector** | Vector search extension on PostgreSQL |
| **Wikipedia ingestion** | Text data for RAG context |
| **F1 Analyst chatbot** | RAG agent with LLM |

### Phase 4 — Scale & ML (Months 9-12)

| Component | Purpose |
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

**Commit checkpoints (recommended):**
- After folder structure creation
- After each new dependency added
- After each working script per layer
- After tests added
- After documentation updates

---

## Learning Resources Referenced

- **Designing Data-Intensive Applications** — Martin Kleppmann (architectural intuition)
- **The Fundamentals of Data Engineering** — Joe Reis (DE concepts)
- **dbt Learn** — official dbt courses
- **DP-800** — Microsoft SQL AI Developer Associate (parallel certification track)

---

## Decision Log

| Date | Decision | Rationale |
|---|---|---|
| Initial | PostgreSQL over SQL Server | Industry standard for DE; pgVector support; free |
| Initial | `uv` over pip + venv | 10x faster, deterministic locking, modern standard |
| Initial | Single-DB Medallion vs separate DBs | Simpler for MVP; layer separation via table prefixes |
| Initial | SQL-first, Python where necessary | Leverage 15 yrs SQL Server experience |
| Initial | dbt added to scope | Critical 2026 DE skill, low cost to integrate |
| Initial | Databricks deferred to Phase 4 | Community Edition limited; PostgreSQL sufficient initially |

---

*Last updated: Project initialization phase*
