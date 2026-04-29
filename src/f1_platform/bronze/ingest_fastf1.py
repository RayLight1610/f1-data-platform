import fastf1
import pandas as pd
from datetime import datetime
from src.f1_platform.db.connection import get_engine
import logging
from sqlalchemy import text

#Setup FastF1 cache
fastf1.Cache.enable_cache("./cache")

logger = logging.getLogger(__name__)

def load_session(year: int, event: str):
    #Load session
    session = fastf1.get_session(year, event, "R") # R = Race
    logger.info(f"Loading {year} {event} race...")
    session.load()
    return session

def add_metadata_columns(df: pd.DataFrame) -> pd.DataFrame:
    df['ingested_at'] = datetime.now()
    df['source'] = 'FastF1'
    return df

def already_ingested(table: str, year: int, event: str, engine) -> bool:
    with engine.connect() as conn:
        result = conn.execute(
            text(f"SELECT 1 FROM bronze.{table} where year = :year AND event = :event LIMIT 1"),
            {"year": year, "event": event}
        ).fetchone()
    return result is not None

def ingest_race_laps(year: int, event: str, mode: str = "append") -> None:
    #Load session
    try:
        session = load_session(year, event)
    except Exception as e:
        logger.error(f"Failed {year} {event}: {e}")
        return

    #Get Laps DataFrame
    laps = session.laps
    logger.info(f"Loaded {len(laps)} laps")

    #Add metadata columns (event, year, ingested_at and source)
    laps['event'] = event
    laps['year'] = year
    laps = add_metadata_columns(laps)

    engine = get_engine()

    #Add idempotency check
    result = already_ingested("raw_laps", year, event, engine)
    if result:
        logger.info(f"Data for {year} {event} already exists. Skipping.")
        return
    
    #Write in the database
    laps.to_sql("raw_laps", engine, schema="bronze", if_exists=mode, index=False)
    logger.info(f"Wrote {len(laps)} rows to bronze.raw_laps")

def ingest_race_results(year: int, event: str, mode: str = "append") -> None:
    #Load session
    session = load_session(year, event)

    #Get results DataFrame
    results = session.results
    logger.info(f"Loaded the official results of Grand Prix of {event}")
     
    #Add metadata columns (year, event, ingested_at and source)
    results['event'] = event
    results['year'] = year
    results = add_metadata_columns(results)

    engine = get_engine()

    #Add idempotency check
    result = already_ingested("raw_results", year, event, engine)
    if result:
        logger.info(f"Data for {year} {event} already exists. Skipping.")
        return
    
    #Write in the database
    results.to_sql("raw_results", engine, schema="bronze", if_exists=mode, index=False)
    logger.info(f"Wrote {len(results)} rows to bronze.raw_results")

def ingest_race_weather(year: int, event: str, mode: str = "append") -> None:
    #Load session
    session = load_session(year, event)

    #Get results DataFrame
    weather_data = session.weather_data
    logger.info(f"Loaded the weather data for Grand Prix of {event}")
    
    #Add metadata columns (year, event, ingested_at and source)     
    weather_data['event'] = event
    weather_data['year'] = year
    weather_data = add_metadata_columns(weather_data)

    engine = get_engine()

    #Add idempotency check
    result = already_ingested("raw_weather_data", year, event, engine)
    if result:
        logger.info(f"Data for {year} {event} already exists. Skipping.")
        return

    #Write in the database
    weather_data.to_sql("raw_weather_data", engine, schema="bronze", if_exists=mode, index=False)
    logger.info(f"Wrote {len(weather_data)} rows to bronze.raw_weather_data")

def ingest_race_telemetry(year: int, event: str, mode: str = "append") -> None:
    #Load session
    session = load_session(year, event)

    fastest_lap = session.laps.pick_fastest()
    telemetry = fastest_lap.get_telemetry()
    logger.info(f"Loaded the telemetry for the fastest lap for Grand Prix of {event}")

    #Add metadata columns (lap_number, event, year, ingested_at and source)
    telemetry['lap_number'] = fastest_lap["LapNumber"]
    telemetry['event'] = event
    telemetry['year'] = year
    telemetry = add_metadata_columns(telemetry)

    engine = get_engine()

    #Add idempotency check
    result = already_ingested("raw_telemetry", year, event, engine)
    if result:
        logger.info(f"Data for {year} {event} already exists. Skipping.")
        return
    
    #Write in the database
    telemetry.to_sql("raw_telemetry", engine, schema="bronze", if_exists=mode, index=False)
    logger.info(f"Wrote {len(telemetry)} rows to bronze.raw_telemetry")

def ingest_season(year: int) -> None:
    """Ingest all races for a given season"""
    schedule = fastf1.get_event_schedule(year)
    for _, event in schedule.iterrows():
        try:
            ingest_race_laps(year, event['EventName'])
            ingest_race_results(year, event['EventName'])
            ingest_race_weather(year, event['EventName'])
            ingest_race_telemetry(year, event['EventName'])
        except Exception as e:
            logger.error(f"Failed {year} {event}: {e}")
            continue