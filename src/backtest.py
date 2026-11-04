"""Rolling-origin backtesting engine and evaluation scoring.

Implements TRD §3.2 & BACKEND_SCHEMA.md:
- Strict expanding window with zero lookahead data leakage.
- Standard metrics: MAE, RMSE, MAPE, MASE (vs seasonal-naive), PICP (80% and 95%).
- Baseline comparison gate.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from src.exceptions import InsufficientHistory, ModelFitError
from src.forecast import calibrate_intervals
from src.models import make_model
from src.series_store import get_observations, get_series

logger = logging.getLogger(__name__)


def run_backtest(
    series_id: str,
    model_names: list[str] | None = None,
    max_horizon: int = 12,
) -> pd.DataFrame:
    """Run rolling-origin expanding-window backtesting for a time series.

    Returns backtest_results DataFrame with calibrated prediction intervals.
    Raises InsufficientHistory if fewer than 4 origins can be constructed.
    """
    if model_names is None:
        model_names = ["naive", "seasonal_naive", "drift", "ets", "sarima", "prophet"]

    # Guarantee both naive baselines are always present (TRD §3.1)
    for baseline in ["naive", "seasonal_naive"]:
        if baseline not in model_names:
            model_names.append(baseline)

    series_meta = get_series(series_id)
    obs = get_observations(series_id)
    frequency = series_meta.get("frequency", "monthly")

    min_required = 52 if frequency == "weekly" else 24
    if len(obs) < min_required:
        raise InsufficientHistory(
            f"Series '{series_id}' has {len(obs)} observations; minimum required is {min_required}."
        )

    dates = pd.to_datetime(obs["date"])
    series_vals = pd.Series(obs["value"].values, index=dates)
    n_total = len(series_vals)

    # Evaluation zone: final 24 steps for monthly (or final 30% if n < 80), step spacing 4
    eval_zone_len = 24 if n_total >= 48 else max(16, n_total // 3)
    step_stride = 4 if frequency == "monthly" else 13

    eval_start_idx = n_total - eval_zone_len
    origin_indices = list(range(eval_start_idx, n_total - 1, step_stride))

    if len(origin_indices) < 4:
        # Step stride finer to ensure at least 4 origins
        origin_indices = list(range(eval_start_idx, n_total - 2, max(2, (n_total - eval_start_idx) // 5)))

    if len(origin_indices) < 4:
        raise InsufficientHistory(
            f"Series '{series_id}' cannot support ≥4 backtest origins (only {len(origin_indices)} found)."
        )

    records: list[dict[str, Any]] = []

    for origin_idx in origin_indices:
        # STRICT LEAKAGE PREVENTION: Train slice strictly before origin
        train_slice = series_vals.iloc[:origin_idx]
        origin_date = dates[origin_idx].strftime("%Y-%m-%d")

        avail_horizon = min(max_horizon, n_total - origin_idx)
        if avail_horizon < 1:
            continue

        for model_name in model_names:
            try:
                mod = make_model(model_name, frequency=frequency)
                mod.fit(train_slice)
                preds = mod.predict(avail_horizon)
            except Exception as e:
                logger.warning(
                    "Model %s failed at origin %s for %s: %s",
                    model_name,
                    origin_date,
                    series_id,
                    e,
                )
                continue

            for h in range(1, avail_horizon + 1):
                actual_val = float(series_vals.iloc[origin_idx + h - 1])
                pred_val = float(preds[h - 1])
                abs_err = abs(actual_val - pred_val)
                pct_err = abs_err / actual_val if actual_val > 0 else 0.0

                records.append(
                    {
                        "series_id": series_id,
                        "model": model_name,
                        "origin_date": origin_date,
                        "step": h,
                        "actual": actual_val,
                        "predicted": pred_val,
                        "abs_error": abs_err,
                        "pct_error": pct_err,
                    }
                )

    if not records:
        raise ModelFitError(f"All models failed during backtesting for {series_id}.")

    raw_backtest = pd.DataFrame(records)

    # Calibrate intervals from the collected empirical errors
    calib_map = calibrate_intervals(raw_backtest)

    # Attach calibrated intervals to backtest table
    lower_80_list: list[float] = []
    upper_80_list: list[float] = []
    lower_95_list: list[float] = []
    upper_95_list: list[float] = []

    for _, row in raw_backtest.iterrows():
        m_name = str(row["model"])
        st = int(row["step"])
        pred_pt = float(row["predicted"])

        cal = calib_map.get((m_name, st), {"q_80": 0.10, "q_95": 0.20})
        q80 = cal["q_80"]
        q95 = cal["q_95"]

        lower_80_list.append(round(max(0.01, pred_pt * np.exp(-q80)), 2))
        upper_80_list.append(round(pred_pt * np.exp(q80), 2))
        lower_95_list.append(round(max(0.01, pred_pt * np.exp(-q95)), 2))
        upper_95_list.append(round(pred_pt * np.exp(q95), 2))

    raw_backtest["lower_80"] = lower_80_list
    raw_backtest["upper_80"] = upper_80_list
    raw_backtest["lower_95"] = lower_95_list
    raw_backtest["upper_95"] = upper_95_list

    return raw_backtest


def score_models(backtest: pd.DataFrame) -> pd.DataFrame:
    """Aggregate backtest_results into model_scores table with MASE and PICP."""
    if backtest.empty:
        return pd.DataFrame()

    series_id = str(backtest["series_id"].iloc[0])
    models = backtest["model"].unique()

    # Find seasonal naive MAE for MASE computation
    s_naive_sub = backtest[backtest["model"] == "seasonal_naive"]
    s_naive_mae = float(s_naive_sub["abs_error"].mean()) if not s_naive_sub.empty else 1.0
    s_naive_mape = float(s_naive_sub["pct_error"].mean() * 100.0) if not s_naive_sub.empty else float("inf")

    scores: list[dict[str, Any]] = []

    for model_name in models:
        sub = backtest[backtest["model"] == model_name]
        n_origins = int(sub["origin_date"].nunique())

        mae = float(sub["abs_error"].mean())
        rmse = float(np.sqrt(np.mean((sub["actual"] - sub["predicted"]) ** 2)))
        mape = float(sub["pct_error"].mean() * 100.0)

        # MASE: mean absolute scaled error relative to seasonal-naive
        mase = float(mae / s_naive_mae) if s_naive_mae > 0 else 1.0

        # Empirical PICP (Prediction Interval Coverage Probability)
        hit_80 = ((sub["actual"] >= sub["lower_80"]) & (sub["actual"] <= sub["upper_80"])).mean() * 100.0
        hit_95 = ((sub["actual"] >= sub["lower_95"]) & (sub["actual"] <= sub["upper_95"])).mean() * 100.0

        # Baseline gate (FR-6): model must beat seasonal naive MAPE
        beats = (mape < s_naive_mape) if model_name != "seasonal_naive" else True

        scores.append(
            {
                "series_id": series_id,
                "model": model_name,
                "mae": round(mae, 2),
                "rmse": round(rmse, 2),
                "mape": round(mape, 2),
                "mase": round(mase, 3),
                "picp_80": round(float(hit_80), 1),
                "picp_95": round(float(hit_95), 1),
                "n_origins": n_origins,
                "beats_baseline": beats,
            }
        )

    score_df = pd.DataFrame(scores)
    # Rank by MAPE ascending
    score_df = score_df.sort_values("mape").reset_index(drop=True)
    return score_df

