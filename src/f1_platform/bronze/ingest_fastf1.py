import logging
from datetime import datetime

import fastf1
import pandas as pd
from sqlalchemy import text

from f1_platform.db.connection import get_engine

# Setup FastF1 cache
fastf1.Cache.enable_cache("./cache")

logger = logging.getLogger(__name__)


def load_session(year: int, event: str):
    # Load session
    session = fastf1.get_session(year, event, "R")  # R = Race
    logger.info(f"Loading {year} {event} race...")
    session.load()
    return session


def add_metadata_columns(df: pd.DataFrame) -> None:
    df["ingested_at"] = datetime.now()
    df["source"] = "FastF1"


def already_ingested(table: str, year: int, event: str, engine) -> bool:
    with engine.connect() as conn:
        table_exists = conn.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'bronze' AND table_name = :table
                )
            """),
            {"table": table},
        ).scalar()

        if not table_exists:
            return False

        result = conn.execute(
            text(f"SELECT 1 FROM bronze.{table} where year = :year AND event = :event LIMIT 1"),
            {"year": year, "event": event},
        ).fetchone()
    return result is not None


def ingest_race_laps(year: int, event: str, mode: str = "append") -> None:
    # Add idempotency check
    if already_ingested("raw_laps", year, event, get_engine()):
        logger.info(f"Laps data for {year} {event} already exists. Skipping.")
        return

    # Load session
    try:
        session = load_session(year, event)
    except Exception as e:
        logger.error(f"Failed {year} {event}: {e}")
        return

    # Get Laps DataFrame
    laps = session.laps
    logger.info(f"Loaded {len(laps)} laps")

    # Add metadata columns (event, year, ingested_at and source)
    laps["event"] = event
    laps["year"] = year
    add_metadata_columns(laps)

    # Write in the database
    engine = get_engine()
    laps.to_sql("raw_laps", engine, schema="bronze", if_exists=mode, index=False)
    logger.info(f"Wrote {len(laps)} rows to bronze.raw_laps")


def ingest_race_results(year: int, event: str, mode: str = "append") -> None:
    # Add idempotency check
    if already_ingested("raw_results", year, event, get_engine()):
        logger.info(f"Results data for {year} {event} already exists. Skipping.")
        return

    # Load session
    try:
        session = load_session(year, event)
    except Exception as e:
        logger.error(f"Failed {year} {event}: {e}")
        return

    # Get results DataFrame
    results = session.results
    logger.info(f"Loaded the official results of Grand Prix of {event}")

    # Add metadata columns (year, event, ingested_at and source)
    results["event"] = event
    results["year"] = year
    add_metadata_columns(results)

    # Write in the database
    engine = get_engine()
    results.to_sql("raw_results", engine, schema="bronze", if_exists=mode, index=False)
    logger.info(f"Wrote {len(results)} rows to bronze.raw_results")


def ingest_race_weather(year: int, event: str, mode: str = "append") -> None:
    # Add idempotency check
    if already_ingested("raw_weather_data", year, event, get_engine()):
        logger.info(f"Weather data for {year} {event} already exists. Skipping.")
        return

    # Load session
    try:
        session = load_session(year, event)
    except Exception as e:
        logger.error(f"Failed {year} {event}: {e}")
        return

    # Get results DataFrame
    weather_data = session.weather_data
    logger.info(f"Loaded the weather data for Grand Prix of {event}")

    # Add metadata columns (year, event, ingested_at and source)
    weather_data["event"] = event
    weather_data["year"] = year
    add_metadata_columns(weather_data)

    # Write in the database
    engine = get_engine()
    weather_data.to_sql("raw_weather_data", engine, schema="bronze", if_exists=mode, index=False)
    logger.info(f"Wrote {len(weather_data)} rows to bronze.raw_weather_data")


def ingest_race_telemetry(year: int, event: str, mode: str = "append") -> None:
    # Add idempotency check
    if already_ingested("raw_telemetry", year, event, get_engine()):
        logger.info(f"Telemetry for {year} {event} already exists. Skipping.")
        return

    # Load session
    try:
        session = load_session(year, event)
    except Exception as e:
        logger.error(f"Failed {year} {event}: {e}")
        return

    fastest_lap = session.laps.pick_fastest()
    telemetry = fastest_lap.get_telemetry()
    logger.info(f"Loaded the telemetry for the fastest lap for Grand Prix of {event}")

    # Add metadata for the lap object
    driver = fastest_lap["Driver"]
    lap_number = fastest_lap["LapNumber"]
    lap_time_seconds = fastest_lap["LapTime"].total_seconds()

    logger.info(f"Loaded telemetry: {driver} fastest lap #{lap_number} ({lap_time_seconds:.3f}s)")

    # Add metadata columns (lap_number, event, year, ingested_at and source)
    telemetry["driver"] = driver
    telemetry["lap_number"] = lap_number
    telemetry["lap_time_seconds"] = lap_time_seconds
    telemetry["event"] = event
    telemetry["year"] = year
    add_metadata_columns(telemetry)

    # Write in the database
    engine = get_engine()
    telemetry.to_sql("raw_telemetry", engine, schema="bronze", if_exists=mode, index=False)
    logger.info(f"Wrote {len(telemetry)} rows to bronze.raw_telemetry")


def ingest_season(year: int) -> None:
    """Ingest all races for a given season"""
    schedule = fastf1.get_event_schedule(year)
    for _, event in schedule.iterrows():
        try:
            ingest_race_laps(year, event["EventName"])
            ingest_race_results(year, event["EventName"])
            ingest_race_weather(year, event["EventName"])
            ingest_race_telemetry(year, event["EventName"])
        except Exception as e:
            logger.error(f"Failed {year} {event}: {e}")
            continue
