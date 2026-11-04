"""Forecast generation and uncertainty interval calibration.

Implements TRD §3.3:
Calibrated interval half-widths from empirical quantiles of backtest residuals.
Symmetric on log-scale for price non-negativity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from src.models import make_model
from src.series_store import get_observations, get_series


def calibrate_intervals(backtest: pd.DataFrame) -> dict[tuple[str, int], dict[str, Any]]:
    """Compute calibrated interval parameters per (model, step) from backtest residuals.

    Falls back to pooled-across-steps quantiles if a step has < 4 origins.
    Returns mapping (model, step) -> {'q_80': float, 'q_95': float, 'calibration': 'per_step' | 'pooled'}.
    """
    if backtest.empty:
        raise ValueError("Cannot calibrate intervals from empty backtest table.")

    # Calculate log residuals
    calib_df = backtest.copy()
    actual = np.maximum(calib_df["actual"].to_numpy(dtype=float), 1e-4)
    pred = np.maximum(calib_df["predicted"].to_numpy(dtype=float), 1e-4)
    calib_df["log_abs_err"] = np.abs(np.log(actual / pred))

    models = calib_df["model"].unique()
    max_step = int(calib_df["step"].max())

    calibration_map: dict[tuple[str, int], dict[str, Any]] = {}

    for model_name in models:
        m_subset = calib_df[calib_df["model"] == model_name]

        # Pooled fallback quantiles for this model
        pooled_errors = m_subset["log_abs_err"].dropna().to_numpy()
        if len(pooled_errors) > 0:
            pooled_q80 = float(np.quantile(pooled_errors, 0.80))
            pooled_q95 = float(np.quantile(pooled_errors, 0.95))
        else:
            pooled_q80 = 0.10
            pooled_q95 = 0.20

        for step in range(1, max_step + 1):
            step_subset = m_subset[m_subset["step"] == step]
            step_errors = step_subset["log_abs_err"].dropna().to_numpy()

            if len(step_errors) >= 4:
                q80 = float(np.quantile(step_errors, 0.80))
                q95 = float(np.quantile(step_errors, 0.95))
                # Monotonicity check against 80%
                q95 = max(q95, q80)
                calibration_map[(model_name, step)] = {
                    "q_80": q80,
                    "q_95": q95,
                    "calibration": "per_step",
                    "n_samples": len(step_errors),
                }
            else:
                calibration_map[(model_name, step)] = {
                    "q_80": pooled_q80,
                    "q_95": pooled_q95,
                    "calibration": "pooled",
                    "n_samples": len(step_errors),
                }

    return calibration_map


def run_forecast(
    series_id: str,
    model_name: str,
    horizon: int = 8,
    calibration_map: dict[tuple[str, int], dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """Fit model on full history, forecast horizon steps, and apply calibrated intervals.

    Returns forecast_runs DataFrame conforming to BACKEND_SCHEMA.md.
    """
    series_meta = get_series(series_id)
    obs = get_observations(series_id)
    frequency = series_meta.get("frequency", "monthly")

    # Guard: check minimum observations (FR-8)
    min_obs = 52 if frequency == "weekly" else 24
    if len(obs) < min_obs:
        from src.exceptions import InsufficientHistory

        raise InsufficientHistory(
            f"Series '{series_id}' has {len(obs)} observations; minimum required is {min_obs}."
        )

    # Fit on full history
    series_data = pd.Series(
        obs["value"].values,
        index=pd.to_datetime(obs["date"]),
    )

    model = make_model(model_name, frequency=frequency)
    model.fit(series_data)
    point_forecasts = model.predict(steps=horizon)

    # Future dates
    last_date = pd.to_datetime(obs["date"].iloc[-1])
    freq_str = "MS" if frequency == "monthly" else "W"
    future_dates = pd.date_range(start=last_date + pd.DateOffset(months=1), periods=horizon, freq=freq_str)

    run_at_ts = datetime.now(timezone.utc).isoformat()
    snapshot_ver = int(series_meta.get("snapshot_version", 1))

    rows: list[dict[str, Any]] = []
    for step in range(1, horizon + 1):
        point = float(point_forecasts[step - 1])
        t_date = future_dates[step - 1].strftime("%Y-%m-%d")

        if calibration_map and (model_name, step) in calibration_map:
            cal = calibration_map[(model_name, step)]
            q80 = cal["q_80"]
            q95 = cal["q_95"]
            cal_mode = cal["calibration"]
        else:
            # Conservative initial default if uncalibrated
            q80 = 0.08 * (1.0 + 0.05 * step)
            q95 = 0.15 * (1.0 + 0.05 * step)
            cal_mode = "uncalibrated"

        lower_80 = max(0.01, point * np.exp(-q80))
        upper_80 = point * np.exp(q80)
        lower_95 = max(0.01, point * np.exp(-q95))
        upper_95 = point * np.exp(q95)

        rows.append(
            {
                "series_id": series_id,
                "model": model_name,
                "run_at": run_at_ts,
                "snapshot_version": snapshot_ver,
                "step": step,
                "target_date": t_date,
                "point": round(point, 2),
                "lower_80": round(lower_80, 2),
                "upper_80": round(upper_80, 2),
                "lower_95": round(lower_95, 2),
                "upper_95": round(upper_95, 2),
                "calibration": cal_mode,
            }
        )

    return pd.DataFrame(rows)

