"""Pipeline entry point.

Examples:
    uv run python main.py bronze --season 2025
    uv run python main.py bronze --season 2026 --event "Australia"
"""

import argparse
import logging

from f1_platform.bronze.ingest_fastf1 import (
    ingest_race_laps,
    ingest_race_results,
    ingest_race_telemetry,
    ingest_race_weather,
    ingest_season,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="F1 Data Platform pipeline")
    parser.add_argument("layer", choices=["bronze"], help="Which layer to run")
    parser.add_argument("--season", type=int, required=True, help="Season year")
    parser.add_argument(
        "--event",
        help="Single event name. Omit to ingest the whole season.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if args.event:
        ingest_race_laps(args.season, args.event)
        ingest_race_results(args.season, args.event)
        ingest_race_weather(args.season, args.event)
        ingest_race_telemetry(args.season, args.event)
    else:
        ingest_season(args.season)


if __name__ == "__main__":
    main()
