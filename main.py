from src.f1_platform.bronze.ingest_fastf1 import ingest_race_laps, ingest_race_results, ingest_race_weather, ingest_race_telemetry, ingest_season
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ingest_race_laps(2026, "Australia", "replace")

# ingest_race_laps(2026, "China")

# ingest_race_laps(2026, "Japan")

# ingest_race_results(2026, "Australia", "replace")

# ingest_race_results(2026, "China")

# ingest_race_results(2026, "Japan")

# ingest_race_weather(2026, "Australia", "replace")

# ingest_race_weather(2026, "China")

# ingest_race_weather(2026, "Japan")

# ingest_race_telemetry(2026, "Australia", "replace")

# ingest_race_telemetry(2026, "China")

# ingest_race_telemetry(2026, "Japan")

ingest_season(2025)

ingest_season(2026)