"""One-off: what does .rowcount return after a two-statement script?"""

from sqlalchemy import text

from f1_platform.db.connection import get_engine

SCRIPT = """
DELETE FROM pg_temp.rc_probe WHERE k = 1;
INSERT INTO pg_temp.rc_probe (k, v)
SELECT 1, g FROM generate_series(1, 7) g;
"""

engine = get_engine()
with engine.begin() as conn:
    conn.execute(text("CREATE TEMP TABLE rc_probe (k int, v int)"))
    conn.execute(text("INSERT INTO pg_temp.rc_probe (k, v) "
                      "SELECT 1, g FROM generate_series(1, 3) g"))

    result = conn.execute(text(SCRIPT))
    print(f"rowcount after DELETE(3) + INSERT(7) = {result.rowcount}")

    actual = conn.execute(text("SELECT count(*) FROM pg_temp.rc_probe")).scalar()
    print(f"actual rows in table            = {actual}")