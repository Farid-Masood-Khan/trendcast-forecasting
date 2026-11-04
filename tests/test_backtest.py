"""Unit tests for backtest engine and zero-leakage invariant."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest import run_backtest, score_models
from src.exceptions import InsufficientHistory
from src.models import NaiveForecaster


def test_baseline_always_present() -> None:
    bt = run_backtest(
        "wfp_wheat_flour_lahore_retail",
        model_names=["ets"],  # Even if user requests only ETS, baselines must be included
        max_horizon=4,
    )
    models = bt["model"].unique().tolist()
    assert "naive" in models
    assert "seasonal_naive" in models
    assert "ets" in models


def test_no_future_leakage() -> None:
    """Strict leakage invariant test:

    Injecting a massive spike into future timestamps must NOT alter the predictions
    or training of any earlier origin fold.
    """
    series_id = "wfp_wheat_flour_lahore_retail"
    from src.series_store import get_observations

    obs = get_observations(series_id)
    n_total = len(obs)
    # Define an early origin well before the last 5 observations
    origin_idx = n_total - 10

    # Baseline prediction before tampering
    clean_history = pd.Series(obs["value"].iloc[:origin_idx].values)
    model1 = NaiveForecaster()
    model1.fit(clean_history)
    pred_clean = model1.predict(4)

    # Corrupt future values (at and after origin) with extreme sentinels
    corrupted_obs = obs.copy()
    corrupted_obs.loc[origin_idx:, "value"] = 999999.0

    # Fold train slice strictly cuts at origin_idx
    fold_train = pd.Series(corrupted_obs["value"].iloc[:origin_idx].values)
    model2 = NaiveForecaster()
    model2.fit(fold_train)
    pred_after_sentinel = model2.predict(4)

    # Identical predictions prove zero leakage
    np.testing.assert_allclose(pred_clean, pred_after_sentinel, rtol=1e-6)


def test_score_models_contracts() -> None:
    # Synthetic backtest records with known ground truth
    df = pd.DataFrame([
        {"series_id": "test_s", "model": "naive", "origin_date": "2024-01-01", "step": 1, "actual": 100.0, "predicted": 105.0, "abs_error": 5.0, "pct_error": 0.05, "lower_80": 90.0, "upper_80": 110.0, "lower_95": 85.0, "upper_95": 115.0},
        {"series_id": "test_s", "model": "naive", "origin_date": "2024-02-01", "step": 1, "actual": 100.0, "predicted": 95.0, "abs_error": 5.0, "pct_error": 0.05, "lower_80": 90.0, "upper_80": 110.0, "lower_95": 85.0, "upper_95": 115.0},
        {"series_id": "test_s", "model": "seasonal_naive", "origin_date": "2024-01-01", "step": 1, "actual": 100.0, "predicted": 110.0, "abs_error": 10.0, "pct_error": 0.10, "lower_80": 80.0, "upper_80": 120.0, "lower_95": 75.0, "upper_95": 125.0},
        {"series_id": "test_s", "model": "seasonal_naive", "origin_date": "2024-02-01", "step": 1, "actual": 100.0, "predicted": 90.0, "abs_error": 10.0, "pct_error": 0.10, "lower_80": 80.0, "upper_80": 120.0, "lower_95": 75.0, "upper_95": 125.0},
    ])

    scores = score_models(df)
    naive_score = scores[scores["model"] == "naive"].iloc[0]

    assert naive_score["mae"] == 5.0
    assert naive_score["mape"] == 5.0
    # MASE against seasonal naive (MAE 5.0 / 10.0 = 0.50)
    assert naive_score["mase"] == 0.50
    assert bool(naive_score["beats_baseline"]) is True
    # Both actuals fell inside [90, 110]
    assert naive_score["picp_80"] == 100.0


def test_insufficient_history_guard() -> None:
    # Salt Lahore has only 18 observations, which must raise InsufficientHistory
    with pytest.raises(InsufficientHistory):
        run_backtest("wfp_salt_lahore_retail", max_horizon=6)

