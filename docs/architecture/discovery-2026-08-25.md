# Discovery — F1 Data Platform

Date: 2026-08-25 · Mode: DISCOVER · Branch: `docs/first-review` · Commit: `db8c393`
Read-only pass. No design produced. Stop point: OPEN QUESTIONS below.

---

## 1. Current state

- Entry point `main.py`: argparse CLI, `layer` restricted to `choices=["bronze"]`, `--season` required, optional `--event`. Configures logging (console only) then calls the four ingest functions or `ingest_season`.
- `f1_platform.db.connection.get_engine()`: 13 lines. `load_dotenv()` + f-string URL + `create_engine()`. No pooling config, no caching, no validation, no return type.
- `f1_platform.bronze.ingest_fastf1`: 185 lines, 4 near-identical ingest functions + `load_session`, `add_metadata_columns`, `already_ingested`, `ingest_season`. Module-level side effect: `fastf1.Cache.enable_cache("./cache")` at import, cwd-relative.
- Bronze tables (implicitly created by `DataFrame.to_sql`, no DDL): `bronze.raw_laps`, `raw_results`, `raw_weather_data`, `raw_telemetry`.
- Only SQL artifact: `sql/bronze/ddl_create_schema.sql` — three `CREATE SCHEMA` + `GRANT ALL`. `sql/silver/` and `sql/gold/` are empty directories.
- `src/f1_platform/silver/`, `gold/`, `utils/` contain only empty `__init__.py`. **Confirmed: no silver, no gold, no shared utils, no config module, no migrations tool.**
- Tests: `tests/test_smoke.py` — one test, `import f1_platform`. No test covers any ingestion or DB behaviour.
- Tooling wired: ruff (E,F,W,I,B,UP; line-length 100), pytest, mypy (deliberately lenient, `files=["src"]`). All in `[dependency-groups] dev`.
- Config: `.env` only, 5 `POSTGRES_*` vars. `config/` directory exists and is empty. `logs/` exists, gitignored, empty.
- Data actually loaded (per notebook, 2026-05): laps 32,926 rows / 35 cols · results 607 / 26 · weather 4,744 / 12 · telemetry 19,479 / 25 — across **30 distinct `(year, event)` pairs**, not 27.
- Local FastF1 cache: **5.6 GB** for those 30 events (~190 MB/event), gitignored, no eviction policy.
- Three reviewer reports exist (`docs/reviews/`), all **VERDICT: FAIL** — bronze ingest, db connection, CLI. Findings treated as established fact here.

---

## 2. Gaps

`docs/VISION.md` is a skeleton: the gold-questions list, runtime target, serving surface, hours/week and budget are all unfilled `TODO`s. **Per the architect contract, gold cannot be designed until "Questions the gold layer must answer" is filled in.** Gaps below are therefore measured against `PROJECT_STRUCTURE.md` + `CLAUDE.md`, not against VISION.

| Area | Required by | Status |
|---|---|---|
| Silver layer (any code or SQL) | PROJECT_STRUCTURE Phase 1, CLAUDE medallion rules | Absent — empty package, empty `sql/silver/` |
| Gold layer (star schema, fact/dim) | PROJECT_STRUCTURE Phase 1 | Absent |
| Explicit DDL per table + stated grain | CLAUDE "Every silver/gold table needs DDL under `sql/<layer>/` and an explicit grain" | Absent for silver/gold (nothing exists yet). Bronze DDL also absent — tables are schema-inferred by `to_sql`, so no named constraints, no indexes, no PK |
| Atomic loads | CLAUDE "idempotent AND atomic … never partially" | Not met. `to_sql` is not wrapped in a transaction; reviewer BLOCKER confirms partial writes strand an event permanently |
| Named constraints and indexes | CLAUDE SQL conventions | None exist on any bronze table (nothing to name them in) |
| `timestamptz` in UTC | CLAUDE SQL conventions | Violated: `add_metadata_columns` writes naive `datetime.now()`; notebook confirms `ingested_at` lands as `datetime64[ns]` (i.e. `timestamp without time zone`) |
| Rate-limit / backoff handling | CLAUDE "assume ~200 req/hour, design for resume-after-failure" | No 429 detection, no backoff, no retry, no run-state table. Resume relies solely on "some row exists" |
| Centralised logging config | PROJECT_STRUCTURE known-issues | Still in `main.py`; no file handler, so unattended runs leave no record |
| Tests for behaviour | CLAUDE definition of done | Only an import smoke test; no fixtures, no `conftest.py`, no fake/recorded FastF1 payloads |
| Non-FastF1 sources (Wikipedia, F1 site) | PROJECT_STRUCTURE architecture diagram | Not started (correctly deferred — Phase 3) |
| Visualisations, dbt, Docker, pgvector, Airflow | PROJECT_STRUCTURE Phases 1–4 | Not started (correctly deferred) |

---

## 3. Contradictions (docs vs. code/data)

Ranked by consequence.

| # | Doc claim | Reality |
|---|---|---|
| 1 | PROJECT_STRUCTURE decision log: *"Idempotency check via SELECT before INSERT — Safe re-runs; production-grade pattern"* | It is neither safe nor atomic. Reviewer BLOCKER: an interrupted `to_sql` leaves rows behind; the next run sees them and skips the event **forever**. The documented "production-grade pattern" is the actual defect. |
| 2 | PROJECT_STRUCTURE: *"Data loaded: Full 2025 season (24 races), partial 2026 (Australia, China, Japan)"* | Notebook shows **30** `(year, event)` pairs, including `2025 / Australia` (927 laps) **and** `2025 / Australian Grand Prix` (927 laps) — the same race ingested twice under two spellings — plus `2025 / Pre-Season Testing` (1,229 laps), which is not a race at all. The `event` key is free text supplied by the caller, so `already_ingested` cannot detect the variant. **There is confirmed duplicate and out-of-scope data in bronze today.** |
| 3 | PROJECT_STRUCTURE diagram + bronze section: table `raw_weather` | Actual table is `bronze.raw_weather_data` (`ingest_fastf1.py:109,131`). |
| 4 | PROJECT_STRUCTURE Project Goal lists **Ergast API** as a source | CLAUDE.md states Ergast was shut down early 2025; FastF1 uses Jolpica. The roadmap still names a dead source. |
| 5 | PROJECT_STRUCTURE roadmap: *"**next**: Jupyter exploration"*; known issues: *"No automated tests yet"*; file tree: *"tests/ (not tracked)"* | The notebook was completed 2026-05 (commit `6c4ef03`); `tests/` is tracked with a passing smoke test. The roadmap's "you are here" marker is ~4 months stale. |
| 6 | PROJECT_STRUCTURE "Installed Dependencies" block (5 packages) | `pyproject.toml` has 7 runtime deps (adds `ipykernel`, `jupyter`) plus a dev group (mypy, pytest, ruff). Two independent hand-maintained dependency lists that already disagree. |
| 7 | Commit `6c4ef03` message: *"explicit mutation in metadata helper"* | `add_metadata_columns` still mutates in place and returns `None` (reviewer NIT). The commit message overstates what landed. |
| 8 | PROJECT_STRUCTURE: `main.py # Pipeline entry point` | It dispatches bronze only (`choices=["bronze"]`) and exits 0 even when every ingest silently fails (reviewer BLOCKER). It is an ingestion launcher, not a pipeline entry point. |
| 9 | PROJECT_STRUCTURE architecture diagram implies bronze holds race data keyed by event | Bronze has **no session column**. `load_session` hardcodes `"R"`. The de-facto grain is `(year, event, race)` but nothing records the session, so Q/FP/Sprint can never be added without a schema change — and `Pre-Season Testing` is already stored as if it were a race. |
| 10 | Code doc gap (code does something docs never mention) | `ingest_race_*` accepts a public `mode` parameter forwarded to `to_sql(if_exists=...)`. `mode="replace"` drops the entire table across all years. No doc mentions this parameter exists. |
| 11 | Code doc gap | `fastf1.Cache.enable_cache("./cache")` runs at **import time** and is **cwd-relative** — importing the module from `notebooks/` or a different cwd silently creates a second cache tree. Undocumented. |
| 12 | Code doc gap | `ingest_season` iterates the **entire** `get_event_schedule(year)`, including testing events. Docs say "iterates through full season schedule, calls all 4 ingestions per race". The word "race" is wrong and item #2 is the visible consequence. |

---

## 4. Risks at 100x volume

**What 100x plausibly means here.** Two independent axes, and they fail differently:

| Axis | Today | 100x |
|---|---|---|
| Breadth (seasons × events) | 30 events, race session only | ~3,000 events ≈ 60+ seasons, or ~25 seasons × 5 session types |
| Depth (telemetry) | fastest lap only, ~650 rows/event | all drivers, all laps: ~90 min × 20 drivers at ~4–10 Hz ≈ **400k–500k rows/event** — that alone is ~700x on the telemetry table |

Ordered by what breaks first.

**1. API rate limit — breaks immediately, before anything technical.**
`ingest_season` triggers `load_session()` up to 4× per event (reviewer BLOCKER). At ~200 req/hour and multiple requests per `session.load()`, a *single* cold-cache season already flirts with the ceiling; 4× redundancy quadruples it. At 100x breadth this is a multi-day job. There is no 429 detection, no exponential backoff, no "stop the run" behaviour, and no run-state table — so on throttle the loop keeps hammering, every event fails, `except Exception` swallows each one, and the run reports success. **The single highest-leverage fix in the codebase: load the session once per event.**

**2. Connection exhaustion — breaks second, and diagnoses badly.**
`get_engine()` builds a *new* `Engine` (own `QueuePool`) on every call; called ~8× per event (reviewer WARNING, confirmed at both files). `ingest_season` over 24 events = ~192 Engines, none `.dispose()`d. Pooled connections are only closed when the Engine is garbage-collected — nondeterministically. So the idle-connection count against Postgres is *unpredictable*, which is worse than a clean leak: at 100x events you will intermittently hit `FATAL: sorry, too many clients already` (default `max_connections = 100`) at a different point on every run. Also: no `pool_pre_ping` (stale connections after any blip on a multi-hour run) and no `connect_timeout` (a down DB hangs on OS TCP timeout instead of failing fast).

**3. `to_sql` write throughput — breaks third, and hard.**
`DataFrame.to_sql` with no `chunksize` and no `method=` uses psycopg2 `executemany`, effectively row-at-a-time. Acceptable at 650 telemetry rows/event; at 400k rows/event this is minutes-to-hours per event and a single giant transaction-less write. `COPY` (via `copy_expert` / `method=` callable) is 1–2 orders of magnitude faster and is the boring, correct answer here. Related: the whole DataFrame is materialised in memory *and* pandas builds a full list of parameter tuples — roughly 2–3× the frame size resident.

**4. `already_ingested` degrades to a sequential scan.**
`SELECT 1 FROM bronze.<t> WHERE year=… AND event=… LIMIT 1` with **no index** (no DDL exists, so `to_sql` created bare heaps). `LIMIT 1` masks it while the target rows are early in the heap; on a 40M-row telemetry table probing an event that is *absent*, Postgres scans the entire table — and this runs 4× per event, per run. At 100x this check alone becomes the dominant cost of a no-op re-run.

**5. Schema inference across eras.**
The first `to_sql` per table froze the column set from whichever 2025 frame loaded first. A backfill spanning 2018–2026 hits renamed/added/removed FastF1 columns (sprint fields, `FastF1Generated`, `DeletedReason`), `append` raises on column mismatch, `ingest_season`'s blanket `except Exception` swallows it, and the event is skipped **silently and permanently** (the `already_ingested` interaction makes it unrecoverable without manual SQL). Reviewer WARNING; at 100x breadth it stops being hypothetical.

**6. Free-text `event` as the natural key.**
Already broken at 1x (`Australia` vs `Australian Grand Prix`, item #2 above). At 100x: non-ASCII names (`São Paulo`), renamed races across years, events sharing a name across seasons, and no session discriminator. Any dedup/merge logic in silver inherits this. A stable key (`year, round, session`) needs to exist before backfill, not after.

**7. Storage and cache.**
FastF1 cache: 190 MB/event × 3,000 = **~560 GB** local disk, no eviction. Postgres: 400k rows × 25 cols × ~200 B ≈ 80 MB/event → ~240 GB for telemetry alone in a single unpartitioned heap. Consequences: no partition pruning on `year`, per-event reload via `DELETE` causes bloat and a table-wide vacuum burden, and index maintenance on every bulk insert. Native range/list partitioning on `year` is cheap to adopt now and expensive to retrofit later.

**8. Non-atomic loads become expensive to repair.**
At 1x, hand-fixing a stranded partial event is a 2-minute `DELETE`. At 100x with 400k-row events, the reviewer's BLOCKER (interrupted write → permanently skipped event) means silent, undetectable holes in a multi-day backfill, discovered months later in gold.

**9. No observability.**
Console-only logging (reviewer WARNING), exit 0 on total failure (reviewer BLOCKER), no row-count assertions, no per-run manifest. At 100x you cannot answer "which of the 3,000 events actually landed, and completely?" — the only evidence is the data itself, which item 8 makes untrustworthy.

**Explicitly not a risk yet:** CPU/parallelism. The job is API-rate-limit bound long before it is compute bound; adding concurrency before fixing item 1 makes throttling worse, not better.

---

## 5. OPEN QUESTIONS

Ranked by how much the answer changes the design. Answer these before DESIGN.

### Q1. What are the 5–10 concrete questions gold must answer?
`docs/VISION.md` leaves this empty. **Per the architect contract this is a hard stop for gold design.**
- *(a) Driver/team performance comparison over a season* → gold is a small star schema (`fact_race_result`, `dim_driver`, `dim_team`, `dim_circuit`) built from results + laps; telemetry stays at fastest-lap depth; the 100x depth risk disappears.
- *(b) Lap/stint/tyre-degradation analysis* → laps become the central fact at `(year, round, driver, lap)` grain; needs stint derivation and pit-window logic in silver; still no full telemetry.
- *(c) Telemetry-driven analysis (cornering, braking points, driver style)* → forces full-race telemetry, i.e. the ~700x depth explosion; `to_sql`, partitioning and COPY all become prerequisites, not nice-to-haves.

### Q2. What is the true target scope — seasons, sessions, telemetry depth?
Determines whether the current design merely needs repair or needs replacement.
- *(a) 2018–present, race session only, fastest-lap telemetry* → ~160 events. Current shape survives with the reviewer fixes + a real key. No partitioning needed.
- *(b) 2018–present, all sessions (FP/Q/Sprint/R)* → ~800 sessions; **bronze needs a `session` column and a `(year, round, session)` key — that is a breaking schema change to existing tables.**
- *(c) Full telemetry for all drivers/laps* → COPY-based loading, partitioning on `year`, and a checkpointed multi-day backfill runner are mandatory from day one.

### Q3. Is existing bronze data disposable?
It currently contains a duplicated race and a testing session under a free-text key.
- *(a) Disposable — drop and reload* → cleanest. Define explicit bronze DDL with `(year, round, session)` keys, named constraints and indexes, then re-ingest **from the 5.6 GB local cache** (no API cost, so this is cheap — verify cache completeness first).
- *(b) Must be preserved* → need a backfill/repair migration: derive `round` from the schedule, collapse the `Australia`/`Australian Grand Prix` pair, quarantine `Pre-Season Testing`. Meaningful one-off work, and every future backfill inherits the messy key.
- *(c) Preserve as an archive schema, rebuild clean alongside* → middle path, costs disk only.

### Q4. Silver in SQL or in Python?
The decision log says "SQL-first"; the code is 100% pandas. These have not yet met.
- *(a) SQL-first: bronze→silver as versioned `.sql` in `sql/silver/`, executed by a thin Python runner* → plays directly to 15 years of SQL depth; the nanosecond-sentinel→NULL→seconds conversion and dedup are trivial set-based SQL; **and it removes pandas from the write path entirely.** Recommended unless there's a reason against.
- *(b) pandas transforms, `to_sql` into silver* → continues current style, but re-imports the throughput and memory problems from §4.3 into every layer, and buries business logic in Python where it is harder to test.
- *(c) dbt now rather than in Phase 2* → new dependency requiring approval; buys lineage, tests and docs; costs a learning detour and a second execution model while the fundamentals are still broken. My inclination: (a) now, dbt at Phase 2 as planned.

### Q5. Where does the stable event key come from?
Every layer's PK depends on this.
- *(a) `(year, round_number, session)` from `get_event_schedule()`* → stable, integer, sortable, immune to renames and accents. Requires reading the schedule once per season (cheap, cacheable).
- *(b) Jolpica/Ergast `circuitId` + season* → stable across renames, but ties bronze to a second source's identifier scheme.
- *(c) Keep `EventName` text, normalise in silver* → cheapest now, but bronze remains un-deduplicable and the §4.6 problem is merely deferred, not solved.

### Q6. How will this run, and how much of your week does it get?
`docs/VISION.md` leaves runtime target, budget and hours/week empty. Operational burden is a first-class cost.
- *(a) Manual `uv run python main.py`, local Postgres, ad-hoc* → keep orchestration out of the design entirely; invest in idempotency and a resumable runner instead. Cheapest, and adequate for Phase 1.
- *(b) Scheduled locally (Task Scheduler/cron) during the season* → needs the exit-code fix, file logging and alerting on failure — all cheap, all currently missing.
- *(c) Cloud Postgres (Supabase/RDS) + CI* → changes the connection strategy (pooling, SSL, egress cost) and makes the 5.6 GB cache and COPY-vs-INSERT question materially more expensive. Also: **is this a portfolio artifact that must be publicly runnable by a reviewer?** That changes README/Docker priorities more than it changes architecture.

### Q7. Should the reviewer's BLOCKERs be fixed before or alongside silver?
- *(a) Fix first (session-load dedup, engine lifecycle, atomic load, exit codes, `mode` removal)* → ~1 focused session; every subsequent backfill and every silver re-run benefits; also the prerequisite for trusting Q3(a)'s reload.
- *(b) Build silver first, fix bronze later* → silver gets built on data known to contain a duplicated race and a testing session; the dedup logic you write will encode the workaround permanently.
- *(c) Fix only the atomicity BLOCKER, defer the rest* → minimum viable; leaves the 4× API amplification in place, which is the constraint that hurts most during any backfill.

---

**STOP.** No design will be produced until Q1–Q7 are answered — Q1 in particular, since `docs/VISION.md` currently makes gold undesignable.
