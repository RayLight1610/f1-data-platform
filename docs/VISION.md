# F1 Data Platform — Vision

Roadmap, phases, decision log: PROJECT_STRUCTURE.md
Architecture: docs/ARCHITECTURE.md (produced by the architect agent)

## 1. Purpose

Primary goal: LEARNING. Understand modern data engineering end to end — the
stages data passes through, the tooling, and the shape of a real platform.
Design decisions should be judged first by what they teach, second by elegance.

Secondary goal: a genuinely useful F1 RAG assistant that helps people who want
to go deeper into the sport.

Explicit non-goal for now: a polished public product. No users besides the
author. Portfolio value is welcome but is not the driver.

## 2. Consumers of gold

Two consumers with different needs. Gold must serve both.

1. **RAG assistant** — answers natural-language questions about F1.
   - Numeric/factual questions ("who won X", "how many stops did Y make")
     are answered via text-to-SQL against the gold star schema.
   - Qualitative and exploratory questions are answered via vector search
     over `gold_documents`.
   - `gold_documents` are natural-language summaries GENERATED FROM gold
     aggregates — per race, per driver-season, per stint. Numbers are never
     embedded directly; embeddings are over generated prose.
   - Wikipedia ingestion (Phase 3) adds a qualitative corpus alongside.
2. **SQL / BI** — charts and statistics for the questions in section 3,
   queried directly against the star schema.

Design implication: gold aggregates need stable, human-readable identifiers
and descriptions, not only surrogate keys, because they become text.

## 3. Questions gold must answer

Grouped by version. v1 defines the first gold layer.

### v1
- **G1. Tyre degradation by compound and circuit.**
  Grain: lap within stint. Needs compound, tyre life, and clean laps only.
- **G2. Which drivers preserve tyres best and hold consistent times longest?**
  Grain: driver-stint. Derived from G1: degradation slope + lap-time variance.
- **G3. Who gains most positions on lap 1, and does the start type matter?**
  Grain: driver-race. Needs grid position, lap-1 position, standing vs
  rolling start.
- **G4. Which circuit types suit which drivers?**
  Grain: driver-circuit-archetype. Depends on G9.
- **G5. How do track and air temperature affect degradation per compound?**
  Grain: stint, joined to weather. Gives the weather table a consumer.
- **G6. Safety car and VSC: how much do they cost, and who benefits?**
  Grain: race phase. Also a PREREQUISITE — laps under SC/VSC/yellow must be
  excluded from G1, G2 and G7, so track status must be modelled first.
- **G7. When does the undercut work, and where?**
  Grain: pit stop event. Needs pit in/out and position before/after.
- **G9. What is the telemetry profile of each circuit?**
  Grain: circuit-season. Derived from the fastest-lap telemetry already
  ingested: full-throttle share, braking event count, mean and top speed,
  time below 100 km/h. Produces the circuit archetypes G4 depends on.

### v2 (deliberately deferred)
- **G8. Is there a systematic pace difference between teammates once traffic
  and fuel effects are removed, and where does it accumulate?**
  Deferred because it is a MODEL, not a query: fuel correction requires a
  calibrated assumption about lap-time gain per lap of burn, and traffic
  detection requires deriving gaps to the car ahead across all drivers.
  Both need documented, defensible assumptions. Revisit once v1 gold is
  stable and the clean-lap definition from G6 is trusted.

## 4. Data scope

Seasons: 2018–present (telemetry availability starts in 2018).
Sessions: RACE ONLY for v1. However, the key includes `session` from day one
  (always 'R' for now) so that adding qualifying and sprint later is an
  INSERT, not a breaking schema migration. Qualifying materially strengthens
  G3 and G4 and is the most likely first extension.
Telemetry depth: fastest lap per race only. Full-race telemetry is out of
  scope — it is roughly a 700x volume increase and would make partitioning
  and COPY-based loading prerequisites rather than optimisations.

## 5. Keys

Canonical event key: `(year, round_number, session)`, sourced from
`fastf1.get_event_schedule()`. Integer, sortable, immune to renames and
accents. Free-text `EventName` is retained as an attribute, never as a key.

## 6. Runtime target

Now:   local. PostgreSQL 18 on the workstation, run manually via the CLI.
       Orchestration stays out of the design; investment goes into
       idempotency, resumability and clear failure signalling instead.
Later: cloud Postgres, explicitly as a learning exercise. Expect the
       connection strategy (pooling, SSL, egress) and the local 5.6 GB cache
       to be the parts that change.
Requirements that apply now because they are cheap and unblock everything
later: non-zero exit codes on failure, file logging, and a visible failure
status. All three are currently missing.

## 7. Constraints

Skill: 15+ years SQL Server OLTP. Python and PySpark deliberately in progress.
  Therefore: SQL-first for transformations. Do not push into Python what
  Postgres does better.
Team size: 1.
Budget: free tiers only.
Learning value counts as a benefit when weighing alternatives — but not
  enough to justify building something the platform does not need.

## 8. Explicitly out of scope

- Kafka / streaming. F1 data is batch by nature.
- Snowflake / BigQuery. PostgreSQL is sufficient at this volume.
- Kubernetes.
- Full-race telemetry (see section 4).
- Any real-time or during-session ingestion.