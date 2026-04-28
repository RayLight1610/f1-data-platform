import fastf1
import pandas as pd
from datetime import datetime
from src.f1_platform.db.connection import get_engine
import logging

#Setup FastF1 cache
fastf1.Cache.enable_cache("./cache")

logger = logging.getLogger(__name__)

def ingest_race_laps(year: int, event: str, mode: str = "append") -> None:

    #Load session
    session = fastf1.get_session(year, event, "R") # R = Race
    logger.info(f"Loading {year} {event} race...")
    session.load()

    #Get Laps DataFrame
    laps = session.laps
    logger.info(f"Loaded {len(laps)} laps")

    #Add metadata columns (ingested_at and source)
    laps['ingested_at'] = datetime.now()
    laps['source'] = 'FastF1'

    engine = get_engine()
    laps.to_sql("raw_laps", engine, schema="bronze", if_exists=mode, index=False)
    logger.info(f"Wrote {len(laps)} rows to bronze.raw_laps")

