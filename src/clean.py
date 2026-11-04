"""Data cleaning and snapshot generation service for TrendCast.

Standardises raw WFP price CSV into versioned Parquet snapshots:
- series.parquet: Catalogue of time series with metadata and quality summary.
- observations.parquet: Tidy observation table with outlier flags (never deleted).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_FILE = DATA_DIR / "raw" / "wfp_food_prices_pakistan.csv"
RAW_MANIFEST = DATA_DIR / "raw" / "manifest.json"
PROCESSED_DIR = DATA_DIR / "processed"
SERIES_FILE = PROCESSED_DIR / "series.parquet"
OBSERVATIONS_FILE = PROCESSED_DIR / "observations.parquet"
SNAPSHOT_MANIFEST = PROCESSED_DIR / "snapshot_manifest.json"

# Curated series for MVP covering staples across markets plus short-history guard test
SERIES_CONFIG: list[dict[str, Any]] = [
    {
        "series_id": "wfp_wheat_flour_lahore_retail",
        "commodity_raw": "Wheat flour",
        "commodity": "wheat_flour",
        "market": "Lahore",
        "display_name": "Wheat flour (retail) — Lahore",
        "unit": "PKR/KG",
    },
    {
        "series_id": "wfp_wheat_flour_karachi_retail",
        "commodity_raw": "Wheat flour",
        "commodity": "wheat_flour",
        "market": "Karachi",
        "display_name": "Wheat flour (retail) — Karachi",
        "unit": "PKR/KG",
    },
    {
        "series_id": "wfp_rice_basmati_lahore_retail",
        "commodity_raw": "Rice (basmati, broken)",
        "commodity": "rice_basmati",
        "market": "Lahore",
        "display_name": "Rice basmati broken (retail) — Lahore",
        "unit": "PKR/KG",
    },
    {
        "series_id": "wfp_rice_basmati_karachi_retail",
        "commodity_raw": "Rice (basmati, broken)",
        "commodity": "rice_basmati",
        "market": "Karachi",
        "display_name": "Rice basmati broken (retail) — Karachi",
        "unit": "PKR/KG",
    },
    {
        "series_id": "wfp_oil_cooking_lahore_retail",
        "commodity_raw": "Oil (cooking)",
        "commodity": "oil_cooking",
        "market": "Lahore",
        "display_name": "Cooking oil (retail) — Lahore",
        "unit": "PKR/L",
    },
    {
        "series_id": "wfp_sugar_lahore_retail",
        "commodity_raw": "Sugar",
        "commodity": "sugar",
        "market": "Lahore",
        "display_name": "Sugar (retail) — Lahore",
        "unit": "PKR/KG",
    },
    {
        "series_id": "wfp_lentils_masur_lahore_retail",
        "commodity_raw": "Lentils (masur)",
        "commodity": "lentils_masoor",
        "market": "Lahore",
        "display_name": "Lentils masoor (retail) — Lahore",
        "unit": "PKR/KG",
    },
    {
        "series_id": "wfp_salt_lahore_retail",
        "commodity_raw": "Salt",
        "commodity": "salt",
        "market": "Lahore",
        "display_name": "Salt (retail) — Lahore [Insufficient History Guard]",
        "unit": "PKR/KG",
    },
]


def detect_outliers_log_diff(series_values: pd.Series, threshold: float = 4.0) -> list[str]:
    """Flag outliers where |z-score of log-differences| > threshold. Never deletes rows."""
    vals = series_values.to_numpy(dtype=float)
    n = len(vals)
    flags: list[str] = ["observed"] * n
    if n < 4:
        return flags

    # Log differences
    with np.errstate(divide="ignore", invalid="ignore"):
        log_vals = np.log(np.maximum(vals, 1e-6))
        log_diff = np.diff(log_vals)

    valid_mask = np.isfinite(log_diff)
    if valid_mask.sum() < 3:
        return flags

    mean_diff = float(np.mean(log_diff[valid_mask]))
    std_diff = float(np.std(log_diff[valid_mask]))

    if std_diff <= 1e-8:
        return flags

    z_scores = (log_diff - mean_diff) / std_diff
    for i, z in enumerate(z_scores):
        if np.isfinite(z) and abs(z) > threshold:
            flags[i + 1] = "outlier_flag"

    return flags


def clean_and_snapshot(raw_path: Path = RAW_FILE, output_dir: Path = PROCESSED_DIR) -> None:
    """Read raw WFP CSV, apply deduplication, quality flags, and write Parquet snapshots."""
    output_dir.mkdir(parents=True, exist_ok=True)

    if not raw_path.exists():
        raise FileNotFoundError(f"Raw data file not found at {raw_path}. Run ingest.py first.")

    source_url = "https://data.humdata.org/dataset/wfp-food-prices-for-pakistan"
    if RAW_MANIFEST.exists():
        with open(RAW_MANIFEST, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            if manifest.get("sources"):
                source_url = manifest["sources"][0].get("url", source_url)

    logger.info("Reading raw data from %s ...", raw_path)
    df_raw = pd.read_csv(raw_path)

    # Standardise column names
    df_raw["date"] = pd.to_datetime(df_raw["date"]).dt.strftime("%Y-%m-01")
    df_raw["price"] = pd.to_numeric(df_raw["price"], errors="coerce")
    df_raw = df_raw.dropna(subset=["date", "price"])

    series_rows: list[dict[str, Any]] = []
    observation_dfs: list[pd.DataFrame] = []

    for conf in SERIES_CONFIG:
        mask = (
            (df_raw["commodity"] == conf["commodity_raw"])
            & (df_raw["market"] == conf["market"])
            & (df_raw["pricetype"] == "Retail")
        )
        subset = df_raw[mask].copy()

        if subset.empty:
            logger.warning("No data found for %s (%s)", conf["series_id"], conf["display_name"])
            continue

        # Deduplicate on (series_id, date) by taking the mean price if duplicated
        deduped = subset.groupby("date", as_index=False).agg({"price": "mean"})
        deduped = deduped.sort_values("date").reset_index(drop=True)

        # Detect outliers
        quality_flags = detect_outliers_log_diff(deduped["price"])
        deduped["quality"] = quality_flags
        deduped["series_id"] = conf["series_id"]
        deduped = deduped.rename(columns={"price": "value"})
        deduped = deduped[["series_id", "date", "value", "quality"]]

        n_obs = len(deduped)
        first_obs = str(deduped["date"].iloc[0])
        last_obs = str(deduped["date"].iloc[-1])

        series_rows.append(
            {
                "series_id": conf["series_id"],
                "display_name": conf["display_name"],
                "commodity": conf["commodity"],
                "market": conf["market"],
                "source": "WFP_HDX",
                "source_url": source_url,
                "frequency": "monthly",
                "unit": conf["unit"],
                "first_obs": first_obs,
                "last_obs": last_obs,
                "n_obs": n_obs,
                "aggregation": "none",
                "snapshot_version": 1,
            }
        )

        observation_dfs.append(deduped)

    series_df = pd.DataFrame(series_rows)
    all_obs_df = pd.concat(observation_dfs, ignore_index=True)

    # Save to Parquet
    series_df.to_parquet(SERIES_FILE, index=False)
    all_obs_df.to_parquet(OBSERVATIONS_FILE, index=False)

    snapshot_manifest = {
        "snapshot_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_series": len(series_df),
        "n_observations": len(all_obs_df),
        "source": "WFP_HDX",
        "source_url": source_url,
    }
    with open(SNAPSHOT_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(snapshot_manifest, f, indent=2)

    logger.info(
        "Cleaned snapshots written: %d series (%s), %d observations (%s)",
        len(series_df),
        SERIES_FILE,
        len(all_obs_df),
        OBSERVATIONS_FILE,
    )


if __name__ == "__main__":
    clean_and_snapshot()

