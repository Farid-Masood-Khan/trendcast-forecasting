"""Unit tests for Forecaster implementations."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.exceptions import ModelFitError
from src.models import (
    DriftForecaster,
    ETSForecaster,
    NaiveForecaster,
    ProphetForecaster,
    SARIMAXForecaster,
    SeasonalNaiveForecaster,
    make_model,
)


def test_naive_forecaster() -> None:
    mod = NaiveForecaster()
    with pytest.raises(ModelFitError):
        mod.predict(3)

    mod.fit(pd.Series([10.0, 15.0, 22.0]))
    preds = mod.predict(4)
    assert len(preds) == 4
    np.testing.assert_allclose(preds, [22.0, 22.0, 22.0, 22.0])


def test_seasonal_naive_forecaster() -> None:
    mod = SeasonalNaiveForecaster(seasonal_periods=4)
    # Series of 2 full cycles
    mod.fit(pd.Series([1.0, 2.0, 3.0, 4.0, 10.0, 20.0, 30.0, 40.0]))
    preds = mod.predict(6)
    assert len(preds) == 6
    # Should repeat the last cycle: [10, 20, 30, 40, 10, 20]
    np.testing.assert_allclose(preds, [10.0, 20.0, 30.0, 40.0, 10.0, 20.0])


def test_drift_forecaster() -> None:
    mod = DriftForecaster()
    # 0 to 10 in 2 steps: slope = (10 - 0) / 2 = 5.0
    mod.fit(pd.Series([0.0, 5.0, 10.0]))
    preds = mod.predict(3)
    np.testing.assert_allclose(preds, [15.0, 20.0, 25.0])


def test_ets_forecaster() -> None:
    mod = ETSForecaster(seasonal_periods=12)
    s = pd.Series(np.linspace(10, 50, 36) + np.sin(np.linspace(0, 6 * np.pi, 36)))
    mod.fit(s)
    preds = mod.predict(6)
    assert len(preds) == 6
    assert (preds > 0).all()


def test_sarimax_forecaster() -> None:
    mod = SARIMAXForecaster(seasonal_periods=12)
    s = pd.Series(np.linspace(20, 60, 40))
    mod.fit(s)
    preds = mod.predict(5)
    assert len(preds) == 5
    assert (preds > 0).all()


def test_prophet_forecaster() -> None:
    mod = ProphetForecaster(frequency="monthly")
    idx = pd.date_range("2020-01-01", periods=30, freq="MS")
    s = pd.Series(np.linspace(50, 100, 30), index=idx)
    mod.fit(s)
    preds = mod.predict(4)
    assert len(preds) == 4
    assert (preds > 0).all()


def test_make_model_factory() -> None:
    m = make_model("sarima")
    assert isinstance(m, SARIMAXForecaster)
    with pytest.raises(ValueError):
        make_model("nonexistent_model")

