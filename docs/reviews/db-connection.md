## BLOCKER
- `src/f1_platform/db/connection.py:17` — user/password are interpolated raw into the URL string. A Postgres password containing `@`, `/`, `:`, `#` or `%` (all realistic) breaks URL parsing — psycopg2 either fails to connect or misparses host/db from the password contents. → Build the URL with `sqlalchemy.engine.URL.create(drivername="postgresql+psycopg2", username=user, password=password, host=host, port=port, database=db)`, which percent-encodes automatically.

## WARNING
- `src/f1_platform/db/connection.py:11-15` — no validation that `POSTGRES_HOST/PORT/DB/USER/PASSWORD` are set. If any is missing, the string becomes `...:None@None:None/None`, and the failure surfaces later as an opaque psycopg2 error at first query, not here. → Check for `None`/empty and raise a clear `RuntimeError` naming the missing var, at `get_engine()` call time.
- `src/f1_platform/db/connection.py:18` — every call builds a new `Engine` (own connection pool); confirmed at call sites (`bronze/ingest_fastf1.py` calls `get_engine()` up to 8x per ingest run, none disposed). This file is where the fix belongs. → Cache the engine (module-level singleton or `functools.lru_cache`) and expose a `dispose_engine()` for shutdown/tests.
- `src/f1_platform/db/connection.py:18` — no `pool_pre_ping`. After a Postgres restart or network blip, pooled connections go stale and the next query fails instead of transparently reconnecting. → `create_engine(connection_string, pool_pre_ping=True)`.
- `src/f1_platform/db/connection.py:18` — no `connect_timeout`. If Postgres is unreachable at startup, `connect()` hangs on the OS-level TCP timeout (can be minutes) instead of failing fast. → `create_engine(connection_string, connect_args={"connect_timeout": 5})`.
- `src/f1_platform/db/connection.py:17-18` — password is embedded in the plain `Engine.url`. Any future `str(engine.url)`, `repr(engine)`, or unguarded exception logging elsewhere in the codebase will leak the credential into logs. → Note in the function contract that callers must use `engine.url.render_as_string(hide_password=True)` for any logging; never log `connection_string` itself.
- `src/f1_platform/db/connection.py:9` — `load_dotenv()` runs on every call with no explicit path; it searches upward from the current working directory, so behavior differs between scripts, notebooks and pytest depending on cwd, and can silently load an unintended `.env` from a parent directory. → Call `load_dotenv()` once at process entry with an explicit path (e.g. `Path(__file__).resolve().parents[N] / ".env"`), not inside `get_engine()`.

## NIT
- `src/f1_platform/db/connection.py:7` — no return type hint (`-> Engine`) or docstring stating that a new pool is created per call; makes the lifecycle bug above easy to miss on review.

## VERDICT: FAIL
BLOCKER: unescaped credentials in the connection URL can break or misparse connections on realistic passwords.
