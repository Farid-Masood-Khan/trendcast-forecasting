"""Unit tests for data cleaning and outlier detection."""

from __future__ import annotations

import pandas as pd

from src.clean import detect_outliers_log_diff
from src.series_store import get_observations, get_series, list_series


def test_detect_outliers_log_diff() -> None:
    # Baseline sequence with one extreme jump at index 15
    vals = pd.Series([10.0] * 15 + [100.0] + [10.0] * 15)
    flags = detect_outliers_log_diff(vals, threshold=3.0)

    assert len(flags) == len(vals)
    # The jump to 100.0 should be flagged
    assert flags[15] == "outlier_flag"
    # Earlier points should be normal
    assert flags[0] == "observed"
    assert flags[1] == "observed"


def test_series_catalogue_integrity() -> None:
    df = list_series()
    assert len(df) >= 7
    expected_cols = [
        "series_id", "display_name", "commodity", "market",
        "source", "source_url", "frequency", "unit",
        "first_obs", "last_obs", "n_obs", "aggregation", "snapshot_version",
    ]
    for col in expected_cols:
        assert col in df.columns

    # Verify Lahore wheat flour
    row = get_series("wfp_wheat_flour_lahore_retail")
    assert row["market"] == "Lahore"
    assert row["commodity"] == "wheat_flour"
    assert row["n_obs"] > 100


def test_get_observations_date_sorting() -> None:
    obs = get_observations("wfp_wheat_flour_lahore_retail")
    assert len(obs) > 0
    assert "date" in obs.columns
    assert "value" in obs.columns
    assert "quality" in obs.columns

    # Check strict ascending order
    dates = pd.to_datetime(obs["date"])
    assert (dates.diff().dropna().dt.days > 0).all()

