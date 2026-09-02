# F1 Data Platform — Architecture

Date: 2026-09-01 · Mode: DESIGN · Supersedes nothing; first architecture document.
Inputs: `docs/VISION.md` (complete), `docs/architecture/discovery-2026-08-25.md`,
`docs/reviews/{bronze-ingest_fastf1,db-connection,main}.md` (all VERDICT: FAIL — binding),
`CLAUDE.md`, answers to Q1–Q7.

Revision 4 (2026-09-01): all blocking verification is complete. Twelve corrections are
marked **[HR-n]** in place; the table below indexes them and records the outcome of each.
**All four blocking `[VERIFY]` items are RESOLVED** against the live database and the local
cache. HR-4 (schema drift across 2018–2023) remains open by nature and resolves during
Appendix B item 8.
Three new findings (HR-10, HR-11, HR-12) came out of the verification queries and are
material — HR-10 changes the diagnosis of the duplicate data, HR-11 changes the clean-lap
rule that G1/G2/G7 depend on.

Scope of this document: **bronze remediation + bronze DDL + silver**. Gold is not designed
here. The only gold-facing commitment made below is the join key
`(year, round_number, session)`, which every silver table carries.

New dependencies required by this design: **none**. Everything below uses
fastf1, pandas, sqlalchemy, psycopg2, python-dotenv, ruff, pytest, mypy — all already in
`pyproject.toml`.

### Human review corrections (revision 2)

| Ref | What changed | Section |
|---|---|---|
| HR-1 | Resume predicate contradicted itself: `IS DISTINCT FROM 'loaded'` would retry `skipped_no_data` forever, which §5.5 explicitly says must not happen. Corrected to `NOT IN ('loaded','skipped_no_data')`. | §4.7, §5.5 |
| HR-2 | **RESOLVED — assumption holds.** `LapStartDate` is naive **UTC**. Measured over 26 rows of 2025: clock-hour stddev 4.71, range 04:18–20:03; Australia 04:18 (15:00 AEDT), Bahrain 15:03 (18:00 AST), Miami 20:03 (16:00 EDT), Las Vegas 04:04 (20:00 PST). A local-time column would have clustered at 14:00–16:00. `AT TIME ZONE 'UTC'` stands. | §4.6 quirk 5, §9 D-6 |
| HR-3 | **RESOLVED — `NOT NULL` is safe.** 61,921 laps: 0 NULL, 0 empty string, 0 `'nan'` in `"TrackStatus"`. Keep the constraint; it is a real invariant. | §4.5 |
| HR-4 | **[VERIFY — deferred by design]** Bronze PKs and the column contract (G-B7) have only ever been exercised against 2024–2026 data. The 2018–2023 backfill is therefore **iterative, not a single run**, newest season first. Not resolvable without loading old seasons. | §5.5, Appendix B item 8 |
| HR-5 | **RESOLVED — the reload is provably free.** Cache audit: 2024 has 24/24 events populated, 2025 has 24/24, 2026 has 5/22 (Australia, China, Japan, Miami, Canada) — exactly the five 2026 races present in bronze. Every `(year, event)` group in bronze has a populated cache directory, so D-16's zero-API-cost premise holds. Uniformly 11 files per event; total ~4.6 GB in the season trees (the discovery report's 5.6 GB includes `http_cache.sqlite` at the cache root). `pg_dump` remains a mandatory precondition to the drop regardless. | Appendix B item 7 |
| HR-6 | `sql/bronze/ddl_create_schema.sql` already exists; it is superseded by `000_create_schemas.sql`, not duplicated. | Appendix A |
| HR-7 | Event count corrected from ~185 to ~197 for 2018–2026. Changes no decision. | §4.2, §5.1 |
| HR-8 | **RESOLVED — `.rowcount` returns the INSERT count.** Measured: `DELETE` of 3 rows then `INSERT` of 7 in one script returns 7; table holds 7. G-B5 works as designed with psycopg2 + PostgreSQL 18. Keep the mechanism; the §8 integration test remains the regression guard. | Appendix A |
| HR-9 | `notebooks/*` is already excluded from ruff in `pyproject.toml`; the proposed per-file-ignore is redundant. | §6 |
| HR-10 | **NEW — the duplicate diagnosis was wrong.** `Pre-Season Testing` does not contain testing data. It is a **byte-identical second copy of the Singapore Grand Prix**, stored under a testing label. Filtering `RoundNumber = 0` prevents recurrence, but the mislabelling implies the season loop resolved a session by position rather than by round. | §4.4, §9 D-16, new §4.8 |
| HR-11 | **NEW — `TrackStatus` is a concatenation of status codes, not one code.** 25 distinct values observed, e.g. `'12'`, `'124'`, `'671'`. A clean lap is `track_status = '1'` **exactly**; never `LIKE '%1%'`. 90.1% of laps are clean. This is the rule G1, G2 and G7 depend on. | new §4.8 |
| HR-12 | **NEW —** `IsPersonalBest` is `boolean` in the *current* bronze table, not `text`: pandas coerced it on the first write. The new DDL pins it to `text`, so the quirk-2 expression is correct **after** the rebuild, but it must also tolerate `'nan'`. Expression extended. | §4.6 quirk 2 |

**Verification gate — cleared.** HR-2, HR-3, HR-5 and HR-8 are resolved. Every item in
Appendix B is unblocked. HR-4 resolves itself during item 8 and is an expectation about how
that item unfolds, not a precondition.

One incidental corroboration of HR-10: **no `Pre-Season Testing` directory exists in the
cache for any season.** The label appeared in the schedule, but the session actually loaded
under it was Singapore. Testing data never entered the platform at any point.

---

## 1. Purpose and non-goals

**Purpose.** Move Formula 1 race data from FastF1 into a local PostgreSQL medallion
warehouse so that a set of nine stated analytical questions (VISION §3, G1–G7 and G9) can be
answered with SQL, and so that generated prose over those answers can later feed a RAG
assistant. The platform must be re-runnable to the point of boredom: any job, killed at any
instant, leaves the database in a state where re-issuing the identical command converges to
the correct result without manual repair. Everything else — throughput, elegance, breadth of
sources — is subordinate to that property, because the operator is one person with limited
hours and the upstream API is rate-limited to roughly 200 requests per hour.

**Non-goals.** No orchestrator, no scheduler, no containerisation, no cloud, no streaming,
no full-race telemetry, no sessions other than the race, and no gold layer in this document.
No dbt yet (Phase 2). No concurrency: the job is API-bound, not CPU-bound, and adding
parallelism before the rate limit is respected makes throttling worse. No attempt to preserve
the bronze data currently in the database — it is disposable (Q3) and will be dropped. No
generalised framework: every module below exists because a named requirement in VISION.md or
a named BLOCKER in `docs/reviews/` demands it.

---

## 2. Context diagram

```
  EXTERNAL                        │  PLATFORM (local workstation)                  │  CONSUMERS
──────────────────────────────────┼───────────────────────────────────────────────┼──────────────
                                  │                                               │
 Jolpica API  ──┐                 │  ┌──────────────────────────────────────────┐ │
 (results,      │                 │  │ main.py  — CLI, logging, exit codes      │ │
  schedule)     │                 │  └───┬───────────────────┬──────────────────┘ │
                ├─► fastf1 ───────┼──►   │                   │                    │
 F1 Live Timing │   Session       │  ┌───▼──────────────┐ ┌──▼──────────────────┐ │
 (laps, car     │   .load()       │  │ f1_platform.     │ │ f1_platform.silver  │ │
  data, weather,│      ▲          │  │   bronze         │ │   (SQL runner only) │ │
  track status) │      │          │  │ (pandas allowed  │ │  no pandas          │ │
                │      │          │  │  ONLY here)      │ │  no fastf1          │ │
                │  ┌───┴────────┐ │  └───┬──────────────┘ └──┬──────────────────┘ │
                └──┤ cache/     │ │      │ DataFrame→INSERT  │ INSERT…SELECT      │
                   │ ff1pkl +   │ │      │                   │                    │
                   │ http sqlite│ │      ▼                   ▼                    │
                   │ (5.6 GB)   │ │  ╔════════════════════════════════════════╗   │
                   └────────────┘ │  ║ PostgreSQL 18  ·  database f1_data     ║   │
                                  │  ║  schema bronze │ silver │ gold │ meta  ║───┼─► psql / BI
                                  │  ╚════════════════════════════════════════╝   │  (§3 gold,
                                  │      ▲ credentials from .env only             │   future)
                                  │      │                                        │
                                  │  ┌───┴──────────────────┐  ┌───────────────┐  │
                                  │  │ f1_platform.db       │  │ logs/*.log    │  │
                                  │  │ (one Engine per run) │  │ (file handler)│  │
                                  │  └──────────────────────┘  └───────────────┘  │
```

Boundaries that matter:

| Boundary | Crossed by | Guarantee at the boundary |
|---|---|---|
| Network → cache | `fastf1` | Rate-limited. `Cache.offline_mode(True)` makes it impossible to cross. |
| cache → bronze | `f1_platform.bronze` | One `session.load()` per `(year, round_number, session)`. |
| bronze → silver | `sql/silver/transform/*.sql` | SQL only. No Python object crosses this line. |
| silver → gold | future | Gold never reads bronze (CLAUDE.md). |
| process → DB | `f1_platform.db` | Exactly one `Engine`, disposed at process exit. |

---

## 3. Layer contracts

Each contract is stated so another agent can verify it with a query, not with judgement.

### bronze

| | |
|---|---|
| **Enters** | A loaded `fastf1.core.Session` object for one `(year, round_number, session)`, plus that season's `EventSchedule`. |
| **Leaves** | Rows in `bronze.raw_*`, original FastF1 PascalCase column names, source values byte-faithful, plus five ingestion-metadata columns. |
| **Guarantees** | G-B1. Every table has explicit DDL in `sql/bronze/`; no column is created by pandas type inference.<br>G-B2. Every row carries `year, round_number, session, ingested_at, source`.<br>G-B3. A load unit is atomic: `(table, year, round_number, session)` is either absent or complete. No partial slice can be observed or left behind.<br>G-B4. A load unit is idempotent: re-running produces byte-identical rows except `ingested_at`.<br>G-B5. For every `meta.load_audit` row with `status='loaded'`, `row_count` equals the actual row count of that slice. Verifiable in one query (§8).<br>G-B6. `round_number >= 1`. Testing events (`RoundNumber = 0`) never enter bronze.<br>G-B7. Unknown source column ⇒ the load **fails**; it is never silently dropped. |
| **NOT guaranteed** | Types are not corrected. Timedeltas remain `bigint` nanoseconds including the sentinel `-9223372036854775808`. `IsPersonalBest` and `DriverNumber` remain `text`. Source timestamps remain naive `timestamp` (see §9 D-6). No cross-table referential integrity. No deduplication beyond the natural-key PK. No validation of value ranges. Nothing is filtered. |

### silver

| | |
|---|---|
| **Enters** | `bronze.raw_*` only. Never FastF1, never a file, never a pandas object. |
| **Leaves** | Typed, deduplicated, validated tables in `silver.*`, snake_case, one stated grain per table. |
| **Guarantees** | G-S1. Every table has a named PK whose columns are exactly the stated grain.<br>G-S2. Every table carries `(year, round_number, session)`, and `(year, round_number, session)` has an FK to `silver.event`.<br>G-S3. All timestamps are `timestamptz` in UTC.<br>G-S4. All durations are `numeric(9,3)` **seconds**; the ns sentinel is `NULL`, never `-9.2e9`.<br>G-S5. No `text` column holds a value that is semantically boolean or numeric.<br>G-S6. A transform is atomic and idempotent per `(year, round_number, session)` slice, by delete-then-insert in one transaction.<br>G-S7. Rebuilding silver from an unchanged bronze produces identical rows (deterministic; no `now()` in transform logic other than the audit column). |
| **NOT guaranteed** | No aggregation, no stint rollups, no clean-lap flag semantics, no derived analytics — those are gold. No history/SCD: silver is a current-state projection of bronze. No cross-season conformance of driver identity beyond what FastF1 supplies (`DriverId` is trusted as-is). No guarantee that a lap exists for every driver in results, or vice versa. |

### gold

Out of scope here. Contract fixed in advance on exactly one point: **gold facts join to silver
on `(year, round_number, session)` and never on `event_name`.**

---

## 4. Data model

### 4.1 Conventions

- Schemas: `bronze`, `silver`, `gold` (existing) + **`meta`** (new; §9 D-4).
- Table names singular in silver (`silver.lap`), original-ish in bronze (`bronze.raw_laps`).
- Constraints named explicitly: `pk_<table>`, `fk_<table>_<target>`, `ck_<table>_<rule>`,
  `ix_<table>_<cols>`.
- `session` is `varchar(3)` with
  `CHECK (session IN ('R','Q','S','SQ','FP1','FP2','FP3'))`. v1 only ever inserts `'R'`;
  the CHECK is what makes adding qualifying later an INSERT rather than a migration
  (VISION §4). Not `char(1)` — `SQ` and `FP1` are two and three characters.

### 4.2 Volume (v1 scope, for sizing decisions)

2018–2026 race sessions ≈ **197 events** **[HR-7]** (2018: 21, 2019: 21, 2020: 17,
2021: 22, 2022: 22, 2023: 22, 2024: 24, 2025: 24, 2026: ~24).

| Table | Rows/event | v1 total | Notes |
|---|---|---|---|
| `bronze.raw_laps` | ~1,100 | ~217k | |
| `bronze.raw_results` | 20 | ~3.9k | |
| `bronze.raw_weather` | ~160 | ~32k | |
| `bronze.raw_telemetry` | ~650 | ~128k | fastest lap only |
| `bronze.raw_track_status` | ~30 | ~5.9k | new (§4.4) |
| `bronze.raw_event_schedule` | 1 | ~197 | new (§4.4) |
| **bronze total** | | **< 400k rows** | |

**This number drives four decisions**: no partitioning, no `COPY`, no chunking, no
concurrency. 400k rows across five tables is a laptop-scale problem. See §9 D-11.

Cache: **re-verified [HR-5]** at ~4.6 GB across the season trees, covering **53 complete
race sessions** — 2024 (24/24), 2025 (24/24), 2026 (5/22: Australia, China, Japan, Miami,
Canada). Uniformly 11 `.ff1pkl` files per event, averaging ~85 MB. 2018–2023 are **absent**;
17 of the 2026 event directories exist but hold zero files, including races already run
(Monaco 06-07 through Abu Dhabi 12-06). Every event currently in bronze has a populated cache
directory, which is what makes D-16's reload free. Backfilling to ~197 events costs ~144 cold
session loads and grows the cache to roughly **16 GB** (144 × 85 MB ≈ 12 GB additional).
See §5.5.

### 4.3 Bronze — existing four tables

Ingestion-metadata columns present on every bronze table:

| Column | Type | Meaning |
|---|---|---|
| `year` | `smallint` | from the season being ingested |
| `round_number` | `smallint` | from `get_event_schedule()`, `>= 1` |
| `session` | `varchar(3)` | `'R'` in v1 |
| `ingested_at` | `timestamptz` | `datetime.now(timezone.utc)` — **the only timestamptz in bronze** |
| `source` | `text` | `'FastF1'` |

Free-text `event` is **dropped from the key** but retained nowhere in these four tables — the
event name lives once, in `bronze.raw_event_schedule`. This removes the
`Australia` / `Australian Grand Prix` failure mode structurally.

`bronze.raw_laps` — grain: one lap per driver.

```sql
CREATE TABLE bronze.raw_laps (
    year                smallint      NOT NULL,
    round_number        smallint      NOT NULL,
    session             varchar(3)    NOT NULL,
    "Time"                  bigint,          -- timedelta64 ns, sentinel-bearing
    "Driver"                text,
    "DriverNumber"          text,            -- object dtype at source; stays text here
    "LapTime"               bigint,
    "LapNumber"             double precision NOT NULL,
    "Stint"                 double precision,
    "PitOutTime"            bigint,
    "PitInTime"             bigint,
    "Sector1Time"           bigint,
    "Sector2Time"           bigint,
    "Sector3Time"           bigint,
    "Sector1SessionTime"    bigint,
    "Sector2SessionTime"    bigint,
    "Sector3SessionTime"    bigint,
    "SpeedI1"               double precision,
    "SpeedI2"               double precision,
    "SpeedFL"               double precision,
    "SpeedST"               double precision,
    "IsPersonalBest"        text,            -- object dtype at source; stays text here
    "Compound"              text,
    "TyreLife"              double precision,
    "FreshTyre"             boolean,
    "Team"                  text,
    "LapStartTime"          bigint,
    "LapStartDate"          timestamp,       -- naive, see D-6
    "TrackStatus"           text,
    "Position"              double precision,
    "Deleted"               boolean,
    "DeletedReason"         text,
    "FastF1Generated"       boolean,
    "IsAccurate"            boolean,
    ingested_at         timestamptz   NOT NULL,
    source              text          NOT NULL,
    CONSTRAINT pk_raw_laps PRIMARY KEY (year, round_number, session, "DriverNumber", "LapNumber")
);
```

`bronze.raw_results` — grain: one row per driver entry.
Columns: the 22 `SessionResults` columns (`DriverNumber, BroadcastName, Abbreviation,
DriverId, TeamName, TeamColor, TeamId, FirstName, LastName, FullName, HeadshotUrl,
CountryCode, Position, ClassifiedPosition, GridPosition, Q1, Q2, Q3, Time, Status, Points,
Laps`) — `Q1/Q2/Q3/Time` as `bigint` ns, `Position/GridPosition/Points/Laps` as
`double precision`, rest `text`.
`CONSTRAINT pk_raw_results PRIMARY KEY (year, round_number, session, "DriverNumber")`.

`bronze.raw_weather` — grain: one weather sample.
Columns: `Time bigint`, `AirTemp/Humidity/Pressure/TrackTemp/WindSpeed double precision`,
`Rainfall boolean`, `WindDirection integer`, `sample_index integer NOT NULL`.
`CONSTRAINT pk_raw_weather PRIMARY KEY (year, round_number, session, sample_index)`.

`bronze.raw_telemetry` — grain: one telemetry sample of the session's fastest lap.
Columns: the 19 `Telemetry` channels + the four lap-identity columns already added today
(`driver`, `lap_number`, `lap_time_seconds` — keep, they are cheap and identify the lap) +
`sample_index integer NOT NULL`.
`CONSTRAINT pk_raw_telemetry PRIMARY KEY (year, round_number, session, sample_index)`.

`sample_index` is the zero-based row ordinal of the source DataFrame. It is ingestion
metadata, not source data, so it is permitted in bronze. It exists because time-series keys
are only *empirically* unique (verified over 30 events in the notebook, not over 2018–2023)
and because telemetry sample order is itself information worth preserving.

### 4.4 Bronze — two new tables

**`bronze.raw_event_schedule`** — grain: one row per `(year, round_number)`.
Source: `fastf1.get_event_schedule(year)`. All 23 schedule columns, PascalCase.
`CONSTRAINT pk_raw_event_schedule PRIMARY KEY (year, "RoundNumber")`.
Reason for existence: it is the *only* authoritative mapping from round number to event name,
country, location and date; it is what makes `(year, round_number, session)` derivable; and
`EventFormat = 'testing'` / `RoundNumber = 0` is the mechanical filter that keeps
Pre-Season Testing out of the platform. One cheap API call per season.

**`bronze.raw_track_status`** — grain: one status change per session.
Source: `session.track_status` (a DataFrame with `Time`, `Status`, `Message`).
Columns: `Time bigint`, `Status text`, `Message text`, `sample_index integer NOT NULL`.
`CONSTRAINT pk_raw_track_status PRIMARY KEY (year, round_number, session, sample_index)`.
Reason for existence: VISION G6 is not only a question, it is a **prerequisite** for G1, G2
and G7 (laps under SC/VSC/yellow must be excluded). The data is already fetched by the
`session.load()` we are paying for — `track_status_data.ff1pkl` is present in every cached
event directory — so this table costs **zero additional API requests**. Not ingesting it now
would mean re-running ~197 session loads later.

### 4.5 Silver — six tables

| Table | Grain (= PK) | Source | Serves |
|---|---|---|---|
| `silver.event` | `(year, round_number, session)` | `raw_event_schedule` × the session set actually loaded | spine; every other silver table FKs here |
| `silver.session_result` | `(year, round_number, session, driver_number)` | `raw_results` | G3, G4, G7 |
| `silver.lap` | `(year, round_number, session, driver_number, lap_number)` | `raw_laps` | G1, G2, G5, G6, G7 |
| `silver.track_status` | `(year, round_number, session, status_index)` | `raw_track_status` | G6 (and the clean-lap rule it gates — §4.7.1) |
| `silver.weather` | `(year, round_number, session, sample_index)` | `raw_weather` | G5 |
| `silver.telemetry_fastest_lap` | `(year, round_number, session, sample_index)` | `raw_telemetry` | G9 → G4 |

`silver.event` also carries `event_name`, `official_event_name`, `country`, `location`,
`event_date`, `event_format`, `session_date_utc timestamptz`, `circuit_key` — the
human-readable identifiers VISION §2 requires for generated prose.

`silver.lap`, the table that absorbs all three documented quirks:

```sql
CREATE TABLE silver.lap (
    year                    smallint      NOT NULL,
    round_number            smallint      NOT NULL,
    session                 varchar(3)    NOT NULL,
    driver_number           smallint      NOT NULL,
    lap_number              smallint      NOT NULL,
    driver_abbreviation     text          NOT NULL,
    team_name               text,
    stint_number            smallint,
    compound                text,
    tyre_life               smallint,
    is_fresh_tyre           boolean,
    lap_time_s              numeric(9,3),
    sector1_s               numeric(9,3),
    sector2_s               numeric(9,3),
    sector3_s               numeric(9,3),
    pit_in_s                numeric(9,3),
    pit_out_s               numeric(9,3),
    lap_start_time_s        numeric(9,3),
    lap_start_at            timestamptz,
    speed_i1                smallint,
    speed_i2                smallint,
    speed_fl                smallint,
    speed_st                smallint,
    position                smallint,
    track_status            text          NOT NULL,   -- HR-3 verified: 0 NULLs in 61,921 laps
    is_personal_best        boolean,
    is_deleted              boolean       NOT NULL,
    deleted_reason          text,
    is_accurate             boolean       NOT NULL,
    is_fastf1_generated     boolean       NOT NULL,
    transformed_at          timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT pk_lap PRIMARY KEY (year, round_number, session, driver_number, lap_number),
    CONSTRAINT fk_lap_event FOREIGN KEY (year, round_number, session)
        REFERENCES silver.event (year, round_number, session),
    CONSTRAINT ck_lap_time_positive  CHECK (lap_time_s IS NULL OR lap_time_s > 0),
    CONSTRAINT ck_lap_number_positive CHECK (lap_number >= 1),
    CONSTRAINT ck_lap_compound CHECK (compound IS NULL OR compound IN
        ('SOFT','MEDIUM','HARD','INTERMEDIATE','WET','UNKNOWN','TEST_UNKNOWN'))
);
CREATE INDEX ix_lap_event_driver ON silver.lap (year, round_number, session, driver_number);
CREATE INDEX ix_lap_compound     ON silver.lap (compound) WHERE compound IS NOT NULL;
```

**[HR-3 — RESOLVED] `track_status NOT NULL` is safe.** Measured across all 61,921 laps
currently in bronze: 0 NULL, 0 empty string, 0 `'nan'`. The constraint stays and is a real
invariant, not an aspiration. Re-check once after the 2018–2023 backfill; older seasons have
not been observed. See §4.7 for what the values actually mean.

Note `ck_lap_compound` deliberately allows `NULL` — the profile found 446 rows with a `'nan'`
string and 57 with `NULL`; both become `NULL` (§4.6). It does **not** allow the string
`'nan'`. That constraint is what makes the quirk handling non-optional.

Partitioning: **none**. See §9 D-11.

### 4.6 Quirk handling — the exact expressions

These three quirks are stated in CLAUDE.md and confirmed in the profile. Each is handled in
exactly one place: the bronze→silver transform SQL. Nowhere else.

| # | Quirk | Evidence | Silver expression |
|---|---|---|---|
| 1 | Timedeltas arrive as `int64` nanoseconds; `NaT` becomes `-9223372036854775808` | 31,872 sentinels in `PitInTime`, 479 in `LapTime` over 30 events | `round(NULLIF("LapTime", -9223372036854775808)::numeric / 1e9, 3) AS lap_time_s` |
| 2 | `IsPersonalBest` arrives as `object`, not `bool` — **[HR-12]** | dtype `object`, 28 NULLs | `CASE lower(nullif(nullif("IsPersonalBest",''),'nan')) WHEN 'true' THEN true WHEN 'false' THEN false ELSE NULL END` |
| 3 | `DriverNumber` arrives as `object` | dtype `object` | `NULLIF("DriverNumber",'')::smallint` — will raise on a non-numeric value, which is the intent: a driver number that is not a number is a schema break, not a data value |
| 4 (found) | `Compound` contains the *string* `'nan'` | 446 rows | `NULLIF(NULLIF("Compound",'nan'),'')` |
| 5 (found) | `LapStartDate` is a naive **UTC** timestamp — **[HR-2] verified, see below** | dtype `datetime64[ns]` | `"LapStartDate" AT TIME ZONE 'UTC'` → `timestamptz` |

**[HR-2 — RESOLVED] `LapStartDate` is UTC.** The assumption was load-bearing and is now
measured rather than assumed. Method: a local-time column would cluster every race between
14:00 and 16:00, because that is when Grands Prix start locally; a UTC column spreads across
the clock according to each circuit's offset. Over the 26 rows of 2025 in bronze, the
clock-hour standard deviation is **4.71** and the range is **04:18 to 20:03**. Individually:

| Race | `min(LapStartDate)` | Local start | Offset |
|---|---|---|---|
| Australian GP | 04:18 | 15:00 AEDT | UTC+11 ✓ |
| Bahrain GP | 15:03 | 18:00 AST | UTC+3 ✓ |
| Miami GP | 20:03 | 16:00 EDT | UTC−4 ✓ |
| Las Vegas GP | 04:04 | 20:00 PST (prev. day) | UTC−8 ✓ |

Conclusive. `AT TIME ZONE 'UTC'` is correct, D-6 stands, and no circuit-timezone join is
needed. Note that `bronze.raw_event_schedule` is still worth having for the round number and
the testing filter — but not for timezone conversion.

Quirk 3 is a deliberate fail-loud. If 2018 data contains a non-numeric driver number, the
transform aborts, the slice is rolled back, and the audit row records `failed` — which is
strictly better than silently NULLing a join key.

Define once, in `sql/silver/000_helpers.sql`, so the sentinel literal appears in the codebase
exactly once:

```sql
CREATE FUNCTION silver.ns_to_seconds(ns bigint) RETURNS numeric(9,3)
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS
$$ SELECT round(NULLIF(ns, -9223372036854775808)::numeric / 1000000000, 3) $$;
```

Trade-off: a scalar SQL function is inlinable by Postgres, so there is no measurable cost,
and it makes the sentinel a single-point-of-truth. The alternative — repeating the literal in
~12 places across four transform files — is how a `-9223372036854775.808` second lap time
eventually reaches gold.

### 4.7 Measured properties of the current bronze data

Everything in this section is measured against the 61,921 laps currently in
`bronze.raw_laps` (2024, 2025, 5×2026). It is recorded here because it changes design
decisions, and because re-deriving it costs queries someone has already run.

#### 4.7.1 `TrackStatus` is a concatenation, not a code **[HR-11]**

The column holds the **ordered concatenation of every status code that was active during
that lap**, not a single code. Observed distribution over 61,921 laps:

| Value | Laps | Reading |
|---|---|---|
| `1` | 55,815 | clear for the whole lap |
| `4` | 1,901 | safety car for the whole lap |
| `12` | 1,552 | clear, then yellow |
| `41` | 604 | safety car, then clear |
| `124` | 463 | clear → yellow → safety car |
| `671` | 306 | VSC deployed → VSC ending → clear |
| `21`, `126`, `6`, `16`, `24`, `26`, `14`, `167`, `71`, `2`, `67`, `1254`, … | tail | 25 distinct values in total |

Underlying single-character codes: `1` all clear, `2` yellow, `4` safety car, `5` red flag,
`6` VSC deployed, `7` VSC ending.

**Consequence — the clean-lap rule.** VISION G6 gates G1, G2 and G7, and this is its
mechanical definition:

```sql
-- CORRECT: the lap was clear from start to finish
WHERE track_status = '1'

-- WRONG: matches '12', '124', '41', '1254' — laps that were interrupted
WHERE track_status LIKE '%1%'
```

**55,815 of 61,921 laps (90.1%) are fully clean.** The remaining 9.9% is not noise to be
ignored: G6 asks what safety cars cost, so those laps are the *subject* of one question and
must be *excluded* from three others. Both uses need the exact string, so silver stores
`track_status` verbatim and classification lives in gold.

`bronze.raw_track_status` (§4.4) remains necessary despite this column: `raw_laps.TrackStatus`
says *that* the status changed during a lap, not *when* or for how long. Deployment and
withdrawal timestamps only exist in the track-status table.

#### 4.7.2 `Pre-Season Testing` is a duplicate race, not testing data **[HR-10]**

The discovery report concluded that a pre-season testing session had been ingested as if it
were a race. That diagnosis is wrong, and the correct one matters more.

| Year | Row labelled | Laps | Drivers |
|---|---|---|---|
| 2024 | `Pre-Season Testing` | 1,177 | 20 |
| 2024 | `Singapore Grand Prix` | 1,177 | 20 |
| 2025 | `Pre-Season Testing` | 1,229 | 20 |
| 2025 | `Singapore Grand Prix` | 1,229 | 20 |

Identical row counts, identical driver counts, and identical
`min("LapStartDate")` — 2025-10-05 12:03:32.198 for both 2025 rows. `Pre-Season Testing`
contains the **Singapore Grand Prix**, stored under the wrong label.

Confirm before relying on it:

```sql
SELECT count(*) AS rows_that_differ
FROM (
    SELECT "Driver", "LapNumber", "LapTime", "Compound"
    FROM bronze.raw_laps WHERE year = 2025 AND event = 'Pre-Season Testing'
    EXCEPT
    SELECT "Driver", "LapNumber", "LapTime", "Compound"
    FROM bronze.raw_laps WHERE year = 2025 AND event = 'Singapore Grand Prix'
) d;
```

Zero rows confirms the duplication.

**Why this matters beyond one bad row.** A testing session leaking in is a *filter* problem,
solved by excluding `RoundNumber = 0`. A race session stored under a testing label is a
**key-resolution** problem: the season loop bound a label from one source to a session
resolved from another, and nothing detected the mismatch. `(year, round_number, session)`
sourced from `get_event_schedule()` (D-1) eliminates the whole class, because the label and
the session then come from the same row. But the rewritten `ingest_event` must be explicit:
the round number passed to `fastf1.get_session()` and the round number written to the
metadata columns must be the **same variable**, not two lookups that happen to agree.

Add to the §8 unit tests: given a stub schedule of three events, assert that the
`round_number` written to bronze equals the `round_number` used to resolve the session, for
every event.

#### 4.7.3 Other measured facts

- **Bronze currently holds 56 rows-per-event groups: 53 distinct races + 3 duplicates**
  (2024 Singapore ×2, 2025 Australia ×2, 2025 Singapore ×2 — where one of each pair carries
  the wrong label).
- **Driver counts vary legitimately**: 19 in 2024 Australia, 2024 São Paulo and 2025 Spain
  (a driver classified with zero recorded laps); 21 in 2026 Australia against 22 elsewhere.
  This is why silver's contract explicitly does **not** guarantee a lap for every driver in
  results.
- **`IsPersonalBest` is `boolean` in the current table**, not `text` — pandas coerced it on
  the first write, which is exactly the schema-inference problem the new DDL removes. After
  the rebuild it is `text` and quirk 2 applies. **[HR-12]**
- **`year` is `bigint` and `ingested_at` is `timestamp without time zone`** in the current
  table. Both are fixed by the new DDL (`smallint`, `timestamptz`).

---

### 4.8 `meta.load_audit` — the visible failure status

```sql
CREATE TABLE meta.load_audit (
    layer           text        NOT NULL,      -- 'bronze' | 'silver'
    target_table    text        NOT NULL,      -- e.g. 'raw_laps'
    year            smallint    NOT NULL,
    round_number    smallint    NOT NULL,
    session         varchar(3)  NOT NULL,
    status          text        NOT NULL,      -- 'loaded' | 'failed' | 'skipped_no_data'
    row_count       integer,
    started_at      timestamptz NOT NULL,
    finished_at     timestamptz NOT NULL,
    run_id          uuid        NOT NULL,
    error_message   text,
    CONSTRAINT pk_load_audit PRIMARY KEY (layer, target_table, year, round_number, session),
    CONSTRAINT ck_load_audit_status CHECK (status IN ('loaded','failed','skipped_no_data')),
    CONSTRAINT ck_load_audit_rowcount CHECK (status <> 'loaded' OR row_count IS NOT NULL)
);
CREATE INDEX ix_load_audit_status ON meta.load_audit (status) WHERE status <> 'loaded';
```

One row per load unit, upserted **inside the same transaction as the data write**. That
co-location is the whole point: the audit row cannot disagree with the data, because they
commit together or not at all.

`status='skipped_no_data'` is a first-class outcome, not a failure — it is what a red-flagged
race with no valid fastest lap produces (reviewer BLOCKER on `pick_fastest()` returning
empty). It is distinct from `failed` so that a resume run does not retry it forever.

This table replaces `already_ingested()` entirely. Resume logic is **[HR-1]**:

```sql
-- a load unit is "still owed" when it has no terminal outcome
WHERE status IS NULL OR status NOT IN ('loaded', 'skipped_no_data')
```

An index-backed lookup against ~1,180 rows, instead of a sequential scan of a data table.

`skipped_no_data` must be on that exclusion list. Revision 1 of this document wrote
`IS DISTINCT FROM 'loaded'`, which contradicted §5.5's requirement that a skipped unit not be
retried forever: a red-flagged race with no valid fastest lap would have been re-attempted on
every single run, for ever. `--force` ignores the predicate entirely and re-loads regardless
of status. It also answers the question the discovery report said
was unanswerable: *which events actually landed, completely?*

---

## 5. Ingestion strategy

### 5.1 Load unit

The atomic unit is **one `(table, year, round_number, session)` slice**. Six tables ×
197 events × 1 session = ~1,180 load units for a full v1 backfill. **[HR-7]**

### 5.2 Full vs incremental

There is no incremental mode and no watermark column. Rationale: an F1 race session is
**immutable once loaded** — the data does not accrete after the chequered flag. The unit of
incrementality is therefore the event, not the row, and the "watermark" is
`meta.load_audit`. This is the single biggest simplification in the design; it is only valid
because of the immutability property, and it stops being valid the moment a source is added
whose rows change in place (Wikipedia will be such a source — see §10).

Two exceptions handled explicitly:

- **The current season's schedule changes** (races added, cancelled, renamed).
  `bronze.raw_event_schedule` is re-loaded in full for the requested year on every run — it is
  ~197 rows, so a full refresh costs nothing and removes an entire class of staleness bug.
- **A recently-finished race may have incomplete data.** FastF1 backfills for a few hours.
  Mitigation is operational, not architectural: re-run the event; the slice is replaced.

### 5.3 Idempotency and atomicity mechanism

One transaction per load unit:

```
BEGIN
  DELETE FROM bronze.<t> WHERE year=:y AND round_number=:r AND session=:s;
  INSERT <rows>;                                  -- pandas to_sql bound to THIS connection
  INSERT INTO meta.load_audit (...) VALUES (...)  -- ON CONFLICT DO UPDATE
    ON CONFLICT ON CONSTRAINT pk_load_audit DO UPDATE SET ...;
COMMIT
```

Properties, each traceable to a reviewer BLOCKER:

| Property | Mechanism | Fixes |
|---|---|---|
| Atomic | single transaction; `to_sql(con=connection)` inside `with engine.begin()` — pandas will not commit when handed a live `Connection` | *"interrupted `to_sql` strands an event permanently"* |
| Idempotent | delete-slice-then-insert, not append | *"`if_exists='append'` allows duplicates"* |
| No check-then-write race | there is no check; the DELETE **is** the idempotency, and the PK is the backstop | *"`already_ingested` and the write are not in one transaction"* |
| Blast radius bounded | DELETE is always keyed by the full `(year, round_number, session)` | *"`mode='replace'` drops the whole table across all years"* |
| `mode` parameter | **removed from the public signature.** `if_exists` is hard-coded `'append'` against a pre-created table | same |

Delete-then-insert is chosen over `INSERT … ON CONFLICT DO UPDATE` because a re-load whose
row set *shrinks* (a lap deleted upstream, a driver disqualified from results) leaves orphan
rows under upsert and does not under delete-insert. Cost: the slice is briefly absent inside
the transaction — invisible to any reader under Postgres MVCC, and irrelevant with a single
writer.

### 5.4 Session loading — the rate-limit fix

`ingest_season` currently calls `session.load()` up to **four times per event**. The fix, and
the reason it is the highest-leverage change in the codebase:

```python
def ingest_event(session: Session, year: int, round_number: int, session_code: str,
                 conn: Connection) -> list[LoadOutcome]: ...
```

The `Session` object is loaded **once**, by the caller, and passed in. Every `ingest_*`
function takes an already-loaded session and never calls `fastf1` itself. This cuts API
traffic by 75% and — equally important — makes every ingest function unit-testable with a
stub object, no network and no mocking library (§8).

### 5.5 Failure, resume, and rate limits

| Event | Behaviour |
|---|---|
| DB unreachable at startup | `SELECT 1` before the loop begins. Abort, exit **2**. Never burn API budget against a dead DB. |
| `fastf1.exceptions.RateLimitExceededError` | **Abort the whole run immediately.** Log the last completed unit. Exit **3**. Do not sleep, do not retry, do not continue the loop. |
| Network/timeout on one event | Record `status='failed'` with the message, continue to the next event, exit **1** at the end. |
| Empty `pick_fastest()` | `status='skipped_no_data'` for `raw_telemetry` only; other tables for that event still load. Not a failure. |
| Unknown source column | Raise. Slice rolls back. `status='failed'`. This is G-B7 and it is deliberate. |
| Process killed (Ctrl-C, power) | In-flight transaction rolls back. At most one unit is lost, and it is the one *without* a `loaded` audit row. |
| Re-run of the identical command | Units with `status IN ('loaded','skipped_no_data')` are skipped by default **[HR-1]**; `--force` re-loads them regardless of status. |

**Backoff is deliberately not implemented.** fastf1 already enforces the Jolpica rate limit
internally (`_CallsPerIntervalLimitRaise`) and raises. Sleeping inside a manually-invoked
job for an unknown period is worse operator experience than exiting 3 with a clear message and
letting the human re-run in an hour — and re-running is free, because the audit table makes
resume exact. Revisit if the run ever becomes unattended (§10).

**`--offline` flag.** `fastf1.Cache.offline_mode(True)` makes cache misses raise instead of
hitting the network. This makes the Q3 reload provably free: `main.py bronze --season 2025
--offline` cannot spend a single request. It is also the flag under which integration tests
run. Verified present in the installed fastf1.

**Backfill sequencing**, given the verified cache state:

| Phase | Events | Cost |
|---|---|---|
| 1. Reload 2024–2025 + 5×2026 from cache | 53 | zero API requests (`--offline`) |
| 2. Fill 2026 gaps (Monaco → Dutch) | ~7 | one season's worth |
| 3. Backfill 2023 → 2018, **one season per run, newest first** | ~125 | ~6 runs spread across days; +~11 GB cache |

**[VERIFY] HR-4 — phase 3 is iterative, not a single run.** Every schema guarantee in this
document has been validated against 2024–2026 data only. Two of them are deliberately
fail-loud and will therefore fire on older seasons:

- **G-B7** (unknown source column ⇒ the load fails) — FastF1's column set has changed across
  eras. `DeletedReason`, `FastF1Generated` and `IsAccurate`, for instance, do not exist in the
  earliest seasons.
- **The natural-key PKs** (D-7) — never exercised against 2018–2023.

Expect a cycle per season: run → fail loud → extend the DDL and the column contract → re-run.
That is the design working as intended, not a defect; the alternative is silent data loss.
Two consequences for planning:

1. Go **newest first** (2023, then 2022, … 2018). Each season is closer to the schema you
   have already proven, so failures arrive one at a time instead of all at once.
2. Column additions must be **nullable** and appended, never repositioned. A season that
   lacks a column stores NULL for it; a column contract violation means an *unknown* column,
   not a *missing* one (see §8, "column contract" unit test).

Record per-season outcomes in `meta.load_audit`; it is already the ledger for exactly this.

### 5.6 Exit codes

| Code | Meaning | Consumer action |
|---|---|---|
| 0 | every requested unit is `loaded` or `skipped_no_data` | none |
| 1 | at least one unit `failed`; others succeeded | inspect `meta.load_audit`, re-run |
| 2 | usage or precondition error (bad args, missing env var, DB unreachable) — also argparse's own code | fix config |
| 3 | aborted on rate limit; work remains | re-run later; resume is exact |

`main.py` is the only module permitted to call `sys.exit`. Library functions return outcomes
or raise; they never terminate the process.

### 5.7 Logging

`f1_platform.utils.logging.configure(log_dir)` — called once, from `main.py`, before anything
else. Console handler (INFO) + `RotatingFileHandler` to `logs/f1-platform-<run_id>.log`
(DEBUG). Every log line carries `run_id`. `logging.basicConfig` disappears from `main.py`.
Modules only ever do `logger = logging.getLogger(__name__)`.

---

## 6. Module boundaries

| Package | Owns | May import | Must NOT import |
|---|---|---|---|
| `f1_platform.config` | reading and validating `.env`; resolving `cache/` and `logs/` paths from the **repo root**, never cwd | stdlib, dotenv | anything in `f1_platform` |
| `f1_platform.utils` | logging configuration | stdlib, config | bronze, silver, gold, db |
| `f1_platform.db` | one `Engine` per process; URL construction; disposal | sqlalchemy, config | fastf1, pandas, bronze, silver, gold |
| `f1_platform.bronze` | FastF1 → `bronze.raw_*`; the column contract | fastf1, pandas, db, config, utils | silver, gold; must not read from `silver.*` |
| `f1_platform.silver` | discovering and executing `sql/silver/*.sql` | sqlalchemy, db, config, utils | **pandas**, **fastf1**, bronze, gold |
| `f1_platform.gold` (future) | executing `sql/gold/*.sql` | sqlalchemy, db, config, utils | pandas, fastf1, bronze; must not read `bronze.*` |
| `main.py` | argument parsing, logging init, `sys.exit` | all of the above | — |

**pandas exists in exactly one package: `bronze`.** That is the whole content of the Q4
answer. FastF1 hands back DataFrames; that is the only reason pandas is in the write path at
all, and the boundary is where it stops.

Mechanically enforceable today with ruff (already a dependency, no new package):

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"pandas".msg = "pandas is permitted only in f1_platform.bronze"
"fastf1".msg = "fastf1 is permitted only in f1_platform.bronze"

[tool.ruff.lint.per-file-ignores]
"src/f1_platform/bronze/*" = ["TID251"]
```
(requires adding `TID` to `select`; this is a config change for the developer to make, not
made by this document).

**[HR-9]** No entry is needed for `notebooks/*` — that directory is already listed under
`[tool.ruff].exclude`, so ruff never inspects it.

---

## 7. Configuration and secrets

| Item | Where | Rule |
|---|---|---|
| DB host/port/db/user/password | `.env`, five `POSTGRES_*` vars | Never committed. `.env.example` is the schema and stays in sync. |
| `FASTF1_CACHE_DIR` | `.env`, default `<repo_root>/cache` | Resolved from `Path(__file__).resolve().parents[3]`, **not cwd** — kills the "import from `notebooks/` creates a second cache tree" bug. |
| `F1_LOG_DIR` | `.env`, default `<repo_root>/logs` | already gitignored |

Rules, each tied to a reviewer finding:

1. `load_dotenv()` is called **once**, in `f1_platform.config`, with an explicit path. Not in
   `get_engine()`, not per call, never searching upward from cwd.
2. Missing or empty variable ⇒ `RuntimeError` naming the variable, raised at config load,
   before any network or DB activity. Not an opaque psycopg2 error five minutes later.
3. The URL is built with `sqlalchemy.engine.URL.create(...)`, never an f-string. This is the
   `db-connection.md` BLOCKER: a password containing `@ / : # %` breaks f-string URL parsing.
4. Nothing logs the URL. Where a connection must be identified in a log line, it is
   `engine.url.render_as_string(hide_password=True)`.
5. `get_engine()` returns a **cached module-level singleton** with
   `pool_pre_ping=True`, `pool_size=5`, `connect_args={"connect_timeout": 5}`, and a
   `-> Engine` annotation. `dispose_engine()` exists for shutdown and test teardown, and
   `main.py` calls it in a `finally`.
6. Cloud move (VISION §6, later): only item 5 changes — `sslmode`, pool size, and possibly a
   `NullPool` for a pooler-fronted service. No other module knows the connection exists.

---

## 8. Testing strategy

Fixtures live in `tests/fixtures/`. No new dependency.

### Unit — no database, no network

| Target | Fixture | Asserts |
|---|---|---|
| config validation | monkeypatched env | missing `POSTGRES_PASSWORD` raises naming that variable |
| URL construction | password `p@ss:w/ord#1` | round-trips; `render_as_string(hide_password=True)` contains no password |
| column contract | frame with an extra column / a missing column | extra ⇒ raises (G-B7); missing ⇒ NULL-filled |
| schedule filtering | 3-row schedule incl. `RoundNumber=0` | testing event excluded (G-B6) |
| **round-number binding [HR-10]** | stub schedule of 3 events | the `round_number` written to the metadata columns is the *same variable* passed to `get_session()`, for every event — not two lookups that happen to agree. This is the test that would have caught the Singapore-as-Pre-Season-Testing duplication |
| `ingest_*` functions | **`FakeSession`** — a plain object exposing `.laps`, `.results`, `.weather_data`, `.track_status`, `.laps.pick_fastest()` | correct target table, correct metadata columns, correct row count |
| empty fastest lap | `FakeSession` whose `pick_fastest()` returns an empty `Laps` | returns `skipped_no_data`, does not raise |
| exit-code mapping | outcome lists | all-ok⇒0, one-failed⇒1, rate-limit⇒3 |

The `FakeSession` approach is only possible because of the §5.4 signature change. That is the
second reason to make it, after the API budget.

### Integration — requires local Postgres, marked `@pytest.mark.integration`, skipped when `POSTGRES_HOST` is unset

| Target | Fixture | Asserts |
|---|---|---|
| DDL | `sql/bronze/*.sql`, `sql/silver/*.sql` applied to a scratch DB | applies cleanly; re-applying is a no-op |
| atomicity | a frame engineered to violate `pk_raw_laps` on its last row | table row count unchanged; **no** `load_audit` row written (G-B3) |
| idempotency | load the golden event twice | row counts identical; `load_audit.row_count` matches `count(*)` (G-B4, G-B5) |
| quirk handling | **pathological fixture** (below) | no `-9223372036854775808` survives; no `'nan'` compound; `is_personal_best` is boolean-or-null, including from the string `'nan'` (HR-12) |
| **clean-lap rule [HR-11]** | laps with `track_status` in `('1','12','124','41','671')` | exactly one row is classified clean; `LIKE '%1%'` would wrongly return five |
| silver transform | golden event in bronze | row count matches; every `ck_` constraint holds; FK to `silver.event` satisfied |
| G-B5 as a query | after any load | `SELECT ... FROM meta.load_audit a JOIN LATERAL (SELECT count(*) …) WHERE a.status='loaded' AND a.row_count <> c` returns zero rows |

**Golden-event fixture**: 2025 Australian GP (round 1), trimmed to **2 drivers** — ~110 lap
rows, 2 result rows, full weather and track status, one telemetry lap. Stored as CSV under
`tests/fixtures/golden_event/`. Small enough to read in a diff, real enough to be honest.

**Pathological fixture**: hand-written, ~10 rows, containing every known trap at once —
all-sentinel timedeltas, `Compound='nan'`, `Compound=NULL`, `IsPersonalBest` as `'True'` /
`'nan'` / empty, `DriverNumber=''`, `Position=NULL`, a `LapStartDate` at a DST boundary, and
`TrackStatus` values `'1'`, `'12'` and `'671'` so the clean-lap rule is exercised. This
is the file that stops quirk regressions.

Deliberately **not** tested: live FastF1 network calls (non-deterministic, rate-limited,
would make the suite unrunnable). Deliberately **not** added: testcontainers, Great
Expectations, hypothesis — all would be new dependencies, and CHECK constraints plus the two
fixtures above cover v1. See §10.

---

## 9. Decision log

| # | Decision | Alternatives considered | Why | Revisit when |
|---|---|---|---|---|
| D-1 | Canonical key `(year, round_number, session)` everywhere | free-text `EventName`; Jolpica `circuitId` | integer, sortable, immune to renames and accents; already caused a real duplicate (`Australia` vs `Australian Grand Prix`) at 1x volume; `session` in the key from day one makes qualifying an INSERT not a migration | never for v1 |
| D-2 | `meta.load_audit` replaces `already_ingested()` | keep SELECT-then-INSERT; a marker file per event | the SELECT probe is a sequential scan on an unindexed heap, runs 4–6× per event, and cannot distinguish "loaded" from "partially loaded"; the audit row commits in the same transaction as the data, so the two cannot disagree | if a second writer ever exists — then it needs a lease column |
| D-3 | Delete-slice + insert in one transaction | `INSERT … ON CONFLICT DO UPDATE`; truncate-and-reload; append-only | upsert leaves orphans when the source row set shrinks; truncate has a table-wide blast radius; append duplicates | when a single slice exceeds ~1M rows and the DELETE becomes a vacuum problem |
| D-4 | New `meta` schema for the audit table | `bronze.load_audit`; `public.load_audit` | silver must read the ledger without importing anything bronze-owned; a control table in a data schema inverts the layer dependency. Cost: one more `CREATE SCHEMA` line | never |
| D-5 | Two new bronze tables (`raw_event_schedule`, `raw_track_status`) | derive round from the schedule at runtime without storing it; skip track status until gold | the schedule is the only source of the key and of the testing-event filter; track status is a **prerequisite** for G1/G2/G7 clean laps (VISION G6) and is already inside the `session.load()` we pay for — **zero extra API cost**. `raw_laps.TrackStatus` is not a substitute: it records *that* the status changed during a lap (§4.7.1), never when or for how long. Skipping it means re-running ~197 loads later | never |
| D-6 | Bronze source timestamps stay naive `timestamp`; only `ingested_at` is `timestamptz` | make everything `timestamptz` in bronze | writing a naive Python datetime into a `timestamptz` column makes Postgres interpret it in the **session** `TimeZone` — on a non-UTC workstation that silently shifts every value. Naive→naive round-trips exactly, and silver applies `AT TIME ZONE 'UTC'` explicitly. This is a **named exception** to the CLAUDE.md "all timestamps timestamptz" rule, scoped to bronze source columns only. **[HR-2]** The *silver-side* half of this decision rests on `LapStartDate` actually being UTC, which is unverified — see §4.6 | if bronze is ever loaded by something that supplies aware datetimes; or immediately, if the HR-2 check shows the source is local time |
| D-7 | Bronze tables get a real PK on the natural key | surrogate id + unique index; no constraint at all | the PK is the last line of defence against the duplicate-row failure that already happened; a PK violation on a 2018 backfill is a *useful* loud failure. Cost: a genuinely duplicated source row aborts the load rather than landing | if a source is found that legitimately emits duplicate natural keys |
| D-8 | `sample_index` as key component for the three time-series tables | rely on `Time`/`Date` uniqueness | uniqueness of the time column is empirically verified over 30 events of 2025–2026 only, not over 2018–2023; and sample order is itself information. `sample_index` is ingestion metadata, so bronze rules permit it | never |
| D-9 | Silver as versioned `.sql` executed by a thin runner | pandas transforms + `to_sql`; dbt now | plays to 15 years of SQL; the sentinel→NULL→seconds conversion and dedup are trivial set-based SQL; removes pandas from the write path; transforms become reviewable artifacts, not buried Python. Cost: no lineage graph, no automatic docs, and file ordering is the developer's responsibility | Phase 2 — dbt, once ≥ 12 transform files exist or a dependency graph is genuinely needed |
| D-10 | `silver.ns_to_seconds()` SQL function | repeat the literal in ~12 places; a Python constant | the sentinel appears exactly once in the codebase; Postgres inlines IMMUTABLE SQL functions so the cost is zero | never |
| D-11 | No partitioning, no `COPY`, no chunking | partition all bronze tables on `year` now; COPY-based loader | v1 bronze is **< 400k rows across five tables** and the largest single load unit is ~1,400 rows. Partitioning ~197 rows/partition is pure operational cost. `executemany` at 1,400 rows is milliseconds | a single load unit exceeds ~100k rows, or a table exceeds ~20M rows — i.e. the moment full-race telemetry or all-session scope is admitted. Both are explicit VISION non-goals |
| D-12 | Abort on rate limit (exit 3), no backoff/sleep | exponential backoff; sleep-and-continue; token bucket | fastf1 already enforces the limit and raises; sleeping for an unknown period inside a manually-run job is worse than exiting with a clear signal, because `meta.load_audit` makes resume exact and free | when the job becomes unattended |
| D-13 | Session loaded once per event, passed into ingest functions | keep four independent loads; a module-level session cache | cuts API traffic 75% against a 200 req/hr ceiling — the single highest-leverage fix in the repo — and is what makes every ingest function unit-testable with a stub | never |
| D-14 | Exit codes 0/1/2/3; only `main.py` calls `sys.exit` | boolean success flag; always exit 0 | current behaviour is exit 0 when every ingest fails (reviewer BLOCKER); distinguishing "partial failure" from "resumable rate-limit abort" is what makes a retry wrapper possible later at zero cost now | never |
| D-15 | `--offline` flag wrapping `Cache.offline_mode(True)` | trust that the cache is warm | makes the Q3 reload *provably* free rather than probably free, and gives integration tests a network-proof mode. Verified present in installed fastf1 | never |
| D-16 | Drop and reload all existing bronze data | migrate in place; archive schema | **[HR-5] the zero-cost premise is not yet verified** — re-check with the corrected script in Appendix B before item 7. The design decision itself is strengthened by HR-10: the bad row is not a stray testing session but a mislabelled copy of a real race, so in-place repair would mean detecting and unpicking a label/session mismatch, not just deleting a row. In-place migration would have to invent `round_number` for `'Australia'` and quarantine `Pre-Season Testing`, and every future backfill would inherit the messy key | n/a — one-time |
| D-17 | Bronze keeps PascalCase quoted identifiers | snake_case bronze | CLAUDE.md medallion rule: bronze is the raw payload with original column names. Cost: every bronze query needs double quotes, which is genuinely unpleasant — but it makes "did silver rename this?" answerable by inspection | never |
| D-19 | Clean lap is `track_status = '1'` exactly; classification lives in gold, silver stores the string verbatim | parse the concatenation into flags in silver; store a `is_clean` boolean in silver | the column is an ordered concatenation of every code active during the lap (§4.7.1), so equality is the only correct test and `LIKE '%1%'` is actively wrong. G6 *studies* the interrupted 9.9% while G1/G2/G7 *exclude* them — both need the raw string, and a silver-side boolean would serve one and destroy the other | if a third consumer needs the parsed codes, add a gold dimension, not a silver column |
| D-18 | No `silver.stint` table | derive stints in silver | `Stint` is already a *source column* in `raw_laps`, so a stint table would be an aggregation, and aggregation is gold's job. `silver.lap` carries `stint_number` and `tyre_life`, which is everything G2/G5/G7 need | when two or more gold models independently recompute identical stint boundaries |

---

## 10. Deferred

| Not built | Trigger that makes it worth building |
|---|---|
| Gold star schema (G1–G7, G9) | bronze remediation lands and silver passes its integration tests. This is the immediate next document. |
| G8 (teammate pace, fuel/traffic correction) | VISION defers it explicitly: it is a model, not a query. Revisit once the G6 clean-lap definition is trusted. |
| Qualifying / sprint / FP sessions | a gold question needs grid-vs-quali pace (G3, G4 get materially stronger). Cost is already paid: `session` is in every key, `varchar(3)` with a CHECK that already lists the values. It is an INSERT of new rows and one new value in a filter. |
| Full-race telemetry | never, under current VISION (~700× volume). If admitted: partitioning on `year`, `COPY`-based loading and a checkpointed multi-day runner all become prerequisites simultaneously, and D-11 flips. |
| `bronze.raw_race_control_messages` | when SC/VSC classification from `track_status` codes proves insufficient for G6. The data is in the already-loaded session, so the cost is one table and one transform. |
| Table partitioning | any bronze table exceeds ~20M rows (D-11). |
| `COPY`-based loading | any single load unit exceeds ~100k rows (D-11). |
| Retry/backoff on rate limit | the job stops being manually invoked (D-12). |
| dbt | ≥ 12 silver/gold transform files, or the moment file-order-as-dependency-management produces its first bug (D-9). |
| testcontainers / Great Expectations | when the integration suite must run somewhere without a local Postgres (i.e. CI). Both are new dependencies requiring approval. |
| SCD Type 2 in silver | a source is added whose rows mutate in place. FastF1 race sessions do not; Wikipedia will. This is the assumption in §5.2 and it is the one most likely to be invalidated. |
| Cache eviction policy | local disk pressure. Backfilling 2018–2023 takes the cache from 5.6 GB to ~16 GB; the ceiling under current scope is ~16 GB, which is tolerable. |
| Cloud Postgres | learning exercise (VISION §6). Only `f1_platform.db` and `.env` change; §7 item 6. |
| Orchestration (Airflow/cron) | explicitly out of scope. The exit codes and file logging in §5.6–5.7 are the entire preparation, and they cost nothing. |

---

## Appendix A — Silver runner mechanics

### Layout

```
sql/
├── bronze/
│   ├── 000_create_schemas.sql          # bronze, silver, gold, meta + grants  [HR-6]
│   ├── 010_meta_load_audit.sql
│   ├── 020_raw_event_schedule.sql
│   ├── 030_raw_laps.sql
│   ├── 040_raw_results.sql
│   ├── 050_raw_weather.sql
│   ├── 060_raw_telemetry.sql
│   └── 070_raw_track_status.sql
└── silver/
    ├── ddl/
    │   ├── 000_helpers.sql             # silver.ns_to_seconds()
    │   ├── 010_event.sql
    │   ├── 020_session_result.sql
    │   ├── 030_lap.sql
    │   ├── 040_track_status.sql
    │   ├── 050_weather.sql
    │   └── 060_telemetry_fastest_lap.sql
    └── transform/
        ├── 010_event.sql
        ├── 020_session_result.sql
        ├── 030_lap.sql
        ├── 040_track_status.sql
        ├── 050_weather.sql
        └── 060_telemetry_fastest_lap.sql
```

**[HR-6]** `sql/bronze/ddl_create_schema.sql` already exists in the repository and creates
bronze/silver/gold plus grants to `f1_app`. It is **superseded** by `000_create_schemas.sql`,
which adds the `meta` schema and its grant. Rename or delete the old file as part of item 3 —
do not leave two files that both create schemas, because the next person will not know which
one is authoritative.

Numeric prefixes are the dependency order. `010_event.sql` runs first because everything
FKs to `silver.event`. This is dependency management by filename — crude, adequate for six
files, and the trigger for adopting dbt (D-9).

### Contract every `transform/*.sql` file must satisfy

1. Exactly one target table, named in the filename.
2. Accepts exactly three bind parameters: `:year`, `:round_number`, `:session`.
3. Body is exactly: `DELETE` the slice, then one `INSERT … SELECT … FROM bronze.…` filtered
   to the same slice.
4. No `CREATE`, no `DROP`, no `TRUNCATE`, no `COMMIT`, no `now()` outside a `DEFAULT`.
5. Explicit column lists on both sides. No `SELECT *`.
6. Deterministic: same bronze in ⇒ same silver out.

Rules 3–5 are greppable. A pre-commit check or a test can assert them without executing SQL.

### Runner

`f1_platform.silver.runner`, roughly 60 lines:

```
run_silver(year, round_number, session, only=None) -> list[LoadOutcome]:
    for path in sorted(SQL_DIR / "transform"):
        with engine.begin() as conn:            # one transaction per file
            rows = conn.execute(text(path.read_text()),
                                {"year": y, "round_number": r, "session": s}).rowcount
            upsert_audit(conn, 'silver', target_table_from(path), y, r, s,
                         'loaded', rows, run_id)
    # first failure: transaction rolls back, audit records 'failed', re-raise
```

**[HR-8 — RESOLVED] `.rowcount` returns the INSERT's count.** Measured on this stack
(psycopg2 + PostgreSQL 18): a script that deletes 3 rows and then inserts 7 returns
`rowcount = 7`, and the table holds 7. G-B5 works as designed and no `RETURNING` clause is
needed.

Two caveats worth keeping. The behaviour is a property of the driver, not of the SQL
standard — a move to psycopg3 or asyncpg must re-verify it. And the value is the *last*
statement's count, so the transform contract (rule 3 below: DELETE then exactly one INSERT,
in that order) is what makes it meaningful; a file with a trailing `ANALYZE` would silently
break the audit count. The §8 integration test for G-B5 is the regression guard for both.

It does not know what any file does. It does not import pandas. It has no SQL of its own
except the audit upsert. That is the entire point: the transformation logic lives in files a
SQL developer can read, and the Python is a loop.

### Full-layer rebuild

`main.py silver --season 2025` iterates the events found in `meta.load_audit` with
`layer='bronze' AND status='loaded'`, and runs the six files for each. Silver never reads
FastF1, never reads a schedule, and cannot process an event bronze has not fully loaded.

---

## Appendix B — Work order

Ordered by dependency. Q7(a): all bronze remediation lands before any silver code.

| # | Work | Closes |
|---|---|---|
| 1 | `f1_platform.config` + `utils.logging`; `main.py` uses both | db-connection WARNINGs; main WARNING (no file handler) |
| 2 | `db.connection`: `URL.create`, singleton, `pool_pre_ping`, `connect_timeout`, `dispose_engine`, type hints | db-connection BLOCKER + all WARNINGs |
| 3 | `sql/bronze/*.sql` DDL for six tables + `meta.load_audit` | bronze BLOCKER (schema inference); CLAUDE "DDL + named constraints" |
| 4 | Rewrite `bronze.ingest_fastf1`: session passed in, transactional slice load, column contract, `mode` removed, UTC `ingested_at`, empty-fastest-lap guard, lazy cache init | all five remaining bronze BLOCKERs + WARNINGs |
| 5 | `main.py`: outcome collection, exit codes 0/1/2/3, DB precondition check, `--offline`, `--force` | main BLOCKER |
| 6 | Unit tests (`FakeSession`, fixtures) | CLAUDE definition of done |
| 7 | **Verify cache completeness [HR-5], `pg_dump` the bronze schema**, then drop it and reload the 53 distinct races with `--offline` | D-16 |
| 8 | Backfill 2018–2023, one season per run | §5.5 |
| 9 | `sql/silver/ddl/*` + `transform/*` + runner + integration tests | Q4 |
| 10 | Update `PROJECT_STRUCTURE.md` — it has 12 documented contradictions with reality | discovery §3 |

**[HR-5] Item 7 is the only irreversible step in this plan.** The claim that the cache covers
everything currently in bronze was verified by an agent, not by a human, and the drop cannot be
undone. Take the backup first; it costs a minute and a few gigabytes:

```powershell
pg_dump -h localhost -U f1_app -d f1_data -n bronze -Fc -f bronze_pre_rebuild.dump
```

**[HR-5 — RESOLVED] Cache completeness verified.** A first attempt used a script that
counted files directly inside each *event* directory and reported every event as empty; that
script was wrong, because fastf1 stores payloads one level deeper, under a per-session folder
(`cache/<year>/<date>_<Event>/<n>_<Session>/*.ff1pkl`). The corrected audit below returned
24/24 populated events for 2024, 24/24 for 2025 and 5/22 for 2026 — matching bronze exactly.
Re-run it before item 7 to confirm nothing has been evicted since:

```powershell
Get-ChildItem cache -Directory | ForEach-Object {
    $season = $_.Name
    Get-ChildItem $_.FullName -Directory | ForEach-Object {
        $files = Get-ChildItem $_.FullName -File -Recurse -ErrorAction SilentlyContinue
        [PSCustomObject]@{
            Season = $season
            Event  = $_.Name
            Files  = $files.Count
            MB     = [math]::Round((($files | Measure-Object Length -Sum).Sum / 1MB), 1)
        }
    }
} | Sort-Object Season, Event | Format-Table -AutoSize
```

Then confirm the total against the 5.6 GB the discovery report claimed:

```powershell
"{0:N2} GB" -f ((Get-ChildItem cache -Recurse -File |
    Measure-Object Length -Sum).Sum / 1GB)
```

**The gate for item 7** is that every `(year, event)` group returned by the duplicate-check
query in §4.7.2 has a corresponding cache directory containing more than zero files. An event
present in bronze but absent from the cache is an event whose reload costs API requests, and
D-16 is priced on the assumption that the reload is free. As of 2026-09-01 this gate **passes**:
53 distinct races in bronze, 53 populated cache directories.

Keep the dump until the reload has completed and this query returns no rows:

```sql
SELECT layer, target_table, year, round_number, session, status
FROM meta.load_audit
WHERE layer = 'bronze' AND status <> 'loaded'
ORDER BY year, round_number;
```

**Verification gate before item 4.** Items 1–3 have no unverified assumptions. Items 4 and 9
do. Resolve HR-2, HR-3 and HR-8 and record the outcomes in the correction table at the top of
this document before writing the code that depends on them. HR-4 is not a gate — it is an
expectation about how item 8 will unfold.
