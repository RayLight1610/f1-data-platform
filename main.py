from src.f1_platform.db.connection import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    result = conn.execute(text("SELECT current_database(), current_user, version();"))
    for row in result:
        print(row)