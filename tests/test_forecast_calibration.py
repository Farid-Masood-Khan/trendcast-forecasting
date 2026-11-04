"""Unit tests for uncertainty calibration and forecast intervals."""

from __future__ import annotations

import pandas as pd

from src.forecast import calibrate_intervals, run_forecast


def test_calibrate_intervals_per_step_and_fallback() -> None:
    # 5 origins for step 1, but only 2 origins for step 2
    records = []
    for o in range(5):
        records.append({
            "series_id": "test_s",
            "model": "naive",
            "origin_date": f"2024-0{o+1}-01",
            "step": 1,
            "actual": 100.0,
            "predicted": 100.0 + o * 2.0,
        })
    for o in range(2):
        records.append({
            "series_id": "test_s",
            "model": "naive",
            "origin_date": f"2024-0{o+1}-01",
            "step": 2,
            "actual": 100.0,
            "predicted": 100.0 + o * 5.0,
        })

    bt_df = pd.DataFrame(records)
    calib = calibrate_intervals(bt_df)

    # Step 1 should have per_step calibration
    assert calib[("naive", 1)]["calibration"] == "per_step"
    # Step 2 (< 4 origins) should fall back to pooled calibration
    assert calib[("naive", 2)]["calibration"] == "pooled"
    assert calib[("naive", 1)]["q_80"] <= calib[("naive", 1)]["q_95"]


def test_run_forecast_interval_monotonicity() -> None:
    fc = run_forecast("wfp_wheat_flour_lahore_retail", model_name="naive", horizon=6)
    assert len(fc) == 6

    # Verify interval bounds monotonicity
    for _, row in fc.iterrows():
        p = float(row["point"])
        l80 = float(row["lower_80"])
        u80 = float(row["upper_80"])
        l95 = float(row["lower_95"])
        u95 = float(row["upper_95"])

        assert l95 <= l80 <= p <= u80 <= u95
        assert l95 > 0.0  # Prices remain strictly positive

