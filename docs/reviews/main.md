## BLOCKER
- `main.py:35-39` — event-name/session-load failures are caught and only logged inside `ingest_fastf1.py:58-62` (each `ingest_*` call swallows the exception and returns). `main()` never checks a return value or catches anything itself, so a typo'd `--event`, an invalid season, or the Jolpica API being down makes all four calls silently no-op and the process still exits 0. An orchestrator/cron sees "success" while bronze stays empty. → Have `ingest_race_laps`/`ingest_race_results`/`ingest_race_weather`/`ingest_race_telemetry` return a success flag (or re-raise), collect results in `main()`, and `sys.exit(1)` if any failed.

## WARNING
- `main.py:36-39` — each of the four calls independently triggers `load_session` (`ingest_fastf1.py:16-21`), so one `--event` invocation loads the same race session 4 times, quadrupling Jolpica API/network calls against the documented ~200 req/hour budget. → Load the session once in `main.py` (or a shared helper) and pass it into each ingest function instead of letting each reload it.
- `main.py:41` — `ingest_season(args.season)` loops over an entire schedule with no upfront check that Postgres is reachable. If the DB is down, every event's `already_ingested()` call fails, gets caught by `ingest_season`'s blanket `except Exception` (`ingest_fastf1.py:182-184`), and the loop burns through the whole season (and API budget) before the failure is visible. → Call `get_engine().connect()` once at the top of `main()` and exit with a clear message if it fails, before entering the season loop.
- `main.py:30-33` — `logging.basicConfig` only attaches a console handler. A long unattended `ingest_season` run that fails partway through leaves no persisted record of which events failed. → Add a `FileHandler` (path from config/env) alongside the console handler.

## NIT
- `main.py:35` — `if args.event:` treats `--event ""` (empty string) as "no event supplied" and silently falls through to a full-season ingest rather than rejecting the invalid input. Unsure how likely this is to be hit in practice (shell quoting mistake), hence NIT not BLOCKER.
- `main.py:22` — `choices=["bronze"]` implies silver/gold layers are dispatched from here eventually; currently harmless but note the file will need a real dispatch table once those layers exist rather than growing another if/else.

## VERDICT: FAIL
BLOCKER: silent success (exit 0) on failed ingestion defeats the purpose of a CLI entry point used for automation/resume-after-failure.
