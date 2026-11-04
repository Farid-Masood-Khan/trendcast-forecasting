"""Series Store: access layer for series metadata and observation history.

Reads read-only Parquet snapshots from data/processed/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.exceptions import SeriesNotFound

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
SERIES_FILE = DATA_DIR / "series.parquet"
OBSERVATIONS_FILE = DATA_DIR / "observations.parquet"


def list_series(source: str | None = None) -> pd.DataFrame:
    """Return all series metadata rows, optionally filtered by source."""
    if not SERIES_FILE.exists():
        raise FileNotFoundError(f"Series snapshot not found at {SERIES_FILE}. Run clean.py first.")

    df = pd.read_parquet(SERIES_FILE)
    if source:
        df = df[df["source"] == source]
    return df.reset_index(drop=True)


def get_series(series_id: str) -> dict[str, Any]:
    """Return one series' metadata as a dictionary. Raises SeriesNotFound."""
    df = list_series()
    match = df[df["series_id"] == series_id]
    if match.empty:
        raise SeriesNotFound(f"Series '{series_id}' not found in catalogue.")
    row: dict[str, Any] = {str(k): v for k, v in match.iloc[0].to_dict().items()}
    return row


def get_observations(
    series_id: str,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Return observations for a series sorted ascending by date.

    Never fabricates rows for missing dates.
    Raises SeriesNotFound if the series is not registered or has no observations.
    """
    # Validate series existence
    get_series(series_id)

    if not OBSERVATIONS_FILE.exists():
        raise FileNotFoundError(f"Observations snapshot not found at {OBSERVATIONS_FILE}.")

    df = pd.read_parquet(OBSERVATIONS_FILE)
    subset = df[df["series_id"] == series_id].copy()
    if subset.empty:
        raise SeriesNotFound(f"No observations found for series '{series_id}'.")

    subset["date"] = pd.to_datetime(subset["date"])
    subset = subset.sort_values("date").reset_index(drop=True)

    if start:
        subset = subset[subset["date"] >= pd.to_datetime(start)]
    if end:
        subset = subset[subset["date"] <= pd.to_datetime(end)]

    # Format date back to ISO string for consistent downstream typing
    subset["date"] = subset["date"].dt.strftime("%Y-%m-%d")
    return subset.reset_index(drop=True)

