"""Forecasting models behind a single unified interface.

Every model implements the Forecaster protocol:
- fit(history: pd.Series) -> None
- predict(steps: int) -> np.ndarray (point forecasts only)

Calibrated uncertainty intervals are applied downstream in src.forecast.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

from src.exceptions import ModelFitError

logger = logging.getLogger(__name__)


@runtime_checkable
class Forecaster(Protocol):
    """Protocol defining the single interface for all forecasting models."""

    name: str

    def fit(self, history: pd.Series) -> None:
        """Fit model parameters on historical time-series observations."""
        ...

    def predict(self, steps: int) -> np.ndarray:
        """Generate point forecasts for `steps` periods ahead."""
        ...


class NaiveForecaster:
    """Naive baseline: repeats the last observed historical value."""

    def __init__(self) -> None:
        self.name = "naive"
        self._last_val: float | None = None

    def fit(self, history: pd.Series) -> None:
        clean = history.dropna()
        if len(clean) == 0:
            raise ModelFitError("Cannot fit NaiveForecaster on empty history.")
        self._last_val = float(clean.iloc[-1])

    def predict(self, steps: int) -> np.ndarray:
        if self._last_val is None:
            raise ModelFitError("NaiveForecaster must be fit before predict.")
        return np.full(steps, self._last_val, dtype=float)


class SeasonalNaiveForecaster:
    """Seasonal naive baseline: repeats the value from one full seasonal cycle ago."""

    def __init__(self, seasonal_periods: int = 12) -> None:
        self.name = "seasonal_naive"
        self.seasonal_periods = seasonal_periods
        self._history_vals: np.ndarray | None = None

    def fit(self, history: pd.Series) -> None:
        clean = history.dropna()
        if len(clean) == 0:
            raise ModelFitError("Cannot fit SeasonalNaiveForecaster on empty history.")
        self._history_vals = clean.to_numpy(dtype=float)

    def predict(self, steps: int) -> np.ndarray:
        if self._history_vals is None:
            raise ModelFitError("SeasonalNaiveForecaster must be fit before predict.")

        n = len(self._history_vals)
        s = self.seasonal_periods
        if n < s:
            # Fall back to repeating the last observation
            return np.full(steps, self._history_vals[-1], dtype=float)

        preds = np.zeros(steps, dtype=float)
        for h in range(steps):
            lag_idx = n - s + (h % s)
            preds[h] = self._history_vals[lag_idx]
        return preds


class DriftForecaster:
    """Drift baseline: extrapolates the historical line between first and last value."""

    def __init__(self) -> None:
        self.name = "drift"
        self._last_val: float | None = None
        self._slope: float = 0.0

    def fit(self, history: pd.Series) -> None:
        clean = history.dropna()
        n = len(clean)
        if n < 2:
            raise ModelFitError("DriftForecaster requires at least 2 observations.")
        y_first = float(clean.iloc[0])
        y_last = float(clean.iloc[-1])
        self._last_val = y_last
        self._slope = (y_last - y_first) / float(n - 1)

    def predict(self, steps: int) -> np.ndarray:
        if self._last_val is None:
            raise ModelFitError("DriftForecaster must be fit before predict.")
        h = np.arange(1, steps + 1, dtype=float)
        preds = self._last_val + (h * self._slope)
        # Prices cannot be negative
        return np.maximum(preds, 0.01)


class ETSForecaster:
    """Exponential Smoothing (Holt-Winters) with automated trend and seasonal handling."""

    def __init__(self, seasonal_periods: int = 12) -> None:
        self.name = "ets"
        self.seasonal_periods = seasonal_periods
        self._fitted_model: Any = None
        self._fallback_val: float | None = None

    def fit(self, history: pd.Series) -> None:
        clean = pd.Series(history.dropna().to_numpy(), dtype=float)
        n = len(clean)
        if n < 4:
            raise ModelFitError("ETSForecaster requires at least 4 observations.")

        self._fallback_val = float(clean.iloc[-1])

        # Attempt full trend + seasonal if history has at least 2 full cycles
        can_season = n >= (2 * self.seasonal_periods)

        candidate_configs = []
        if can_season:
            candidate_configs.append({"trend": "add", "seasonal": "add", "seasonal_periods": self.seasonal_periods})
            candidate_configs.append({"trend": "add", "damped_trend": True, "seasonal": "add", "seasonal_periods": self.seasonal_periods})
        candidate_configs.append({"trend": "add", "seasonal": None, "seasonal_periods": None})
        candidate_configs.append({"trend": None, "seasonal": None, "seasonal_periods": None})

        best_model = None
        best_aic = float("inf")

        for cfg in candidate_configs:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model = ExponentialSmoothing(
                        clean,
                        trend=cfg["trend"],
                        damped_trend=cfg.get("damped_trend", False),
                        seasonal=cfg["seasonal"],
                        seasonal_periods=cfg["seasonal_periods"],
                        initialization_method="estimated",
                    ).fit()
                    aic = getattr(model, "aic", float("inf"))
                    if np.isfinite(aic) and aic < best_aic:
                        best_aic = aic
                        best_model = model
            except Exception:
                continue

        if best_model is None:
            # Fallback to simple exponential smoothing
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    best_model = ExponentialSmoothing(clean).fit()
            except Exception as e:
                raise ModelFitError(f"ETS fitting failed completely: {e}") from e

        self._fitted_model = best_model

    def predict(self, steps: int) -> np.ndarray:
        if self._fitted_model is None:
            if self._fallback_val is not None:
                return np.full(steps, self._fallback_val, dtype=float)
            raise ModelFitError("ETSForecaster must be fit before predict.")
        try:
            forecasts = self._fitted_model.forecast(steps)
            arr = np.asarray(forecasts, dtype=float)
            return np.maximum(arr, 0.01)
        except Exception as e:
            logger.warning("ETS forecast error: %s; using fallback", e)
            return np.full(steps, self._fallback_val or 0.01, dtype=float)


class SARIMAXForecaster:
    """SARIMA model with bounded AIC grid search across candidate orders."""

    def __init__(self, seasonal_periods: int = 12) -> None:
        self.name = "sarima"
        self.seasonal_periods = seasonal_periods
        self._fitted_model: Any = None
        self._last_val: float | None = None

    def fit(self, history: pd.Series) -> None:
        clean = pd.Series(history.dropna().to_numpy(), dtype=float)
        n = len(clean)
        if n < 8:
            raise ModelFitError("SARIMAXForecaster requires at least 8 observations.")

        self._last_val = float(clean.iloc[-1])
        s = self.seasonal_periods if n >= (2 * self.seasonal_periods) else 0

        # Bounded grid of parsimonious orders per TRD §3.1
        candidate_orders = [
            ((1, 1, 0), (0, 0, 0, 0)),
            ((0, 1, 1), (0, 0, 0, 0)),
            ((1, 1, 1), (0, 0, 0, 0)),
            ((2, 1, 0), (0, 0, 0, 0)),
            ((0, 1, 2), (0, 0, 0, 0)),
        ]
        if s > 0:
            candidate_orders.extend([
                ((1, 1, 0), (1, 0, 0, s)),
                ((0, 1, 1), (0, 1, 0, s)),
                ((1, 1, 1), (0, 1, 0, s)),
                ((1, 1, 0), (0, 1, 1, s)),
            ])

        best_fit = None
        best_aic = float("inf")

        for order, sorder in candidate_orders:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    mod = SARIMAX(
                        clean,
                        order=order,
                        seasonal_order=sorder,
                        enforce_stationarity=False,
                        enforce_invertibility=False,
                    )
                    res = mod.fit(disp=False, maxiter=50)
                    if res.aic < best_aic:
                        best_aic = res.aic
                        best_fit = res
            except Exception:
                continue

        if best_fit is None:
            # Fallback to minimal random walk with drift
            try:
                mod = SARIMAX(clean, order=(0, 1, 0), trend="c")
                best_fit = mod.fit(disp=False, maxiter=30)
            except Exception as e:
                raise ModelFitError(f"SARIMAX failed to converge: {e}") from e

        self._fitted_model = best_fit

    def predict(self, steps: int) -> np.ndarray:
        if self._fitted_model is None:
            if self._last_val is not None:
                return np.full(steps, self._last_val, dtype=float)
            raise ModelFitError("SARIMAXForecaster must be fit before predict.")
        try:
            forecasts = self._fitted_model.forecast(steps)
            arr = np.asarray(forecasts, dtype=float)
            return np.maximum(arr, 0.01)
        except Exception as e:
            logger.warning("SARIMAX forecast error: %s; using fallback", e)
            return np.full(steps, self._last_val or 0.01, dtype=float)


class ProphetForecaster:
    """Prophet forecaster with yearly seasonality."""

    def __init__(self, frequency: str = "monthly") -> None:
        self.name = "prophet"
        self.frequency = frequency
        self._fitted_model: Any = None
        self._last_val: float | None = None

    def fit(self, history: pd.Series) -> None:
        try:
            from prophet import Prophet
        except ImportError as e:
            raise ModelFitError(f"Prophet is not installed: {e}") from e

        clean = history.dropna()
        n = len(clean)
        if n < 8:
            raise ModelFitError("Prophet requires at least 8 observations.")

        self._last_val = float(clean.iloc[-1])

        # Prepare DataFrame with ds and y
        if isinstance(clean.index, pd.DatetimeIndex):
            ds = clean.index
        else:
            try:
                ds = pd.to_datetime(clean.index)
            except Exception:
                ds = pd.date_range(end="2026-08-01", periods=n, freq="MS")

        df_train = pd.DataFrame({"ds": ds, "y": clean.values.astype(float)})

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
            logging.getLogger("prophet").setLevel(logging.WARNING)

            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
            )
            try:
                model.fit(df_train)
                self._fitted_model = model
            except Exception as e:
                raise ModelFitError(f"Prophet fit failed: {e}") from e

    def predict(self, steps: int) -> np.ndarray:
        if self._fitted_model is None:
            if self._last_val is not None:
                return np.full(steps, self._last_val, dtype=float)
            raise ModelFitError("ProphetForecaster must be fit before predict.")

        freq = "MS" if self.frequency == "monthly" else "W"
        future = self._fitted_model.make_future_dataframe(periods=steps, freq=freq, include_history=False)
        forecast_df = self._fitted_model.predict(future)
        yhat = forecast_df["yhat"].to_numpy(dtype=float)
        return np.maximum(yhat, 0.01)


def make_model(name: str, frequency: str = "monthly") -> Forecaster:
    """Factory to instantiate forecaster by name and frequency."""
    s_periods = 12 if frequency == "monthly" else 52

    match name.lower():
        case "naive":
            return NaiveForecaster()
        case "seasonal_naive":
            return SeasonalNaiveForecaster(seasonal_periods=s_periods)
        case "drift":
            return DriftForecaster()
        case "ets":
            return ETSForecaster(seasonal_periods=s_periods)
        case "sarima":
            return SARIMAXForecaster(seasonal_periods=s_periods)
        case "prophet":
            return ProphetForecaster(frequency=frequency)
        case _:
            raise ValueError(
                f"Unknown model name '{name}'. Allowed: naive, seasonal_naive, drift, ets, sarima, prophet."
            )

