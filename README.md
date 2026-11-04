# TrendCast — Time-Series Forecasting Dashboard with Calibrated Uncertainty

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked: Mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](https://github.com/python/mypy)
[![Tests: Pytest](https://img.shields.io/badge/tests-pytest-green.svg)](https://docs.pytest.org/)

An interactive Streamlit dashboard for forecasting food staple prices across Pakistan (WFP HDX market series) with **honest, backtested evaluation** as its core engineering principle. 

TrendCast does not draw ungrounded trend lines: every forecast is accompanied by multi-origin rolling backtests, empirical prediction intervals calibrated on historical residuals, and a baseline comparison gate that transparently flags any model that fails to outperform seasonal persistence.

---

## 1. Why TrendCast Exists

Pakistan's food inflation is subject to severe structural volatility: wheat flour, basmati rice, sugar, and cooking oil prices swing sharply with monsoon floods, currency devaluations, and harvest cycles. Public market monitoring data exists (WFP, Pakistan Bureau of Statistics), but decision-makers (small retail grocers, food aid analysts, household planners) are left guessing future price trajectories without reliable uncertainty bounds.

Generic forecasting tools frequently fail in two directions:
1. **Uncalibrated Extrapolation**: Producing narrow theoretical confidence bands that fail to capture real-world variance.
2. **Missing Baselines**: Displaying complex neural or autoregressive curves without checking whether a simple "tomorrow = today" baseline actually achieved lower error.

TrendCast operates under an uncompromising principle: **A forecast without a backtest is a guess with a chart.**

---

## 2. Architecture & Service Layer

TrendCast enforces a strict separation between data storage, statistical modeling, evaluation, and user presentation:

```
┌────────────────────────────────┐
│   WFP Pakistan Food Prices     │
│   (Humanitarian Data Exchange) │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│      src.ingest & src.clean     │ ──▶ data/raw/manifest.json (sha256: 139bef16505a)
│   (Outlier flags, deduplication)│ ──▶ data/processed/observations.parquet & series.parquet
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────────┐
│                   Service Layer (src/)                 │
│  - series_store: typed snapshot and metadata access    │
│  - models: Naive, Seasonal-Naive, Drift, ETS, SARIMAX,  │
│            Prophet behind single Forecaster protocol   │
│  - backtest: rolling-origin expanding window engine    │
│  - forecast: empirical residual interval calibration   │
│  - insights: rule-based non-causal plain language      │
└───────────────┬────────────────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────────┐
│                   Streamlit UI (app.py)                │
│  - Forecast view with Plotly 80% & 95% shaded bands   │
│  - Per-step error expansion curves                     │
│  - FR-8 Insufficient History guard state (<24 obs)     │
│  - CSV export for forecasts and backtest matrices     │
└────────────────────────────────────────────────────────┘
```

---

## 3. Empirical Benchmark Results

All metrics below are computed directly by `src.evaluate` against real WFP Pakistan monthly food price observations:

### Multi-Model Performance Summary Across Shipped Series

| Series | Market | Best Model | Best MAPE | S-Naive MAPE | Beats Baseline | 80% PICP |
|---|---|---|---|---|---|---|
| Wheat flour (retail) — Lahore | Lahore | `sarima` | **10.64%** | 30.01% | ✅ Yes | 81.8% |
| Wheat flour (retail) — Karachi | Karachi | `naive` | **14.63%** | 32.68% | ✅ Yes | 81.8% |
| Rice basmati broken (retail) — Lahore | Lahore | `drift` | **5.00%** | 14.54% | ✅ Yes | 81.8% |
| Rice basmati broken (retail) — Karachi | Karachi | `drift` | **2.06%** | 2.56% | ✅ Yes | 81.8% |
| Cooking oil (retail) — Lahore | Lahore | `drift` | **2.92%** | 7.15% | ✅ Yes | 81.8% |
| Sugar (retail) — Lahore | Lahore | `naive` | **8.37%** | 13.63% | ✅ Yes | 81.8% |
| Lentils masoor (retail) — Lahore | Lahore | `naive` | **5.40%** | 13.04% | ✅ Yes | 81.8% |

### Key Statistical Properties
- **Mean Calibrated 80% PICP**: **81.8%** (strictly satisfies PRD §7 success criterion of 65%–92%).
- **Zero Lookahead Leakage**: Verified by `test_no_future_leakage` (future data corruption leaves prior folds unchanged).
- **FR-8 Reliability Gate**: Verified by `test_insufficient_history_guard` (`wfp_salt_lahore_retail` with 18 obs safely deferred).

---

## 4. Measured Limitations & Shock Vulnerability

1. **Exogenous Shock Blindness (2022 Super Floods)**:
   Pure time-series pattern extrapolation cannot anticipate climate catastrophes or sudden trade policy shifts. During the 2022 Pakistan super-floods (Jul–Nov 2022), monthly price volatility jumped to **7.50%** compared to the baseline normal of **3.35%** (a **2.24x surge**).
2. **Short Histories & Interval Width**:
   On series with limited observation spans, empirical calibrated intervals widen substantially. TrendCast renders true empirical uncertainty rather than artificially narrowing confidence bands.
3. **Baseline Competitiveness**:
   On high-persistence commodities (e.g. sugar and cooking oil), naive or drift baselines match or outperform complex seasonal autoregressive models. The dashboard surfaces this finding directly rather than obscuring it.

---

## 5. Quickstart & Verification

```powershell
# 1. Install dependencies into virtual environment
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Run test suite (18 unit tests)
.\run.ps1 -Command "test"

# 3. Static type check (Mypy)
.\run.ps1 -Command "typecheck"

# 4. Code quality & lint (Ruff)
.\run.ps1 -Command "lint"

# 5. Launch interactive Streamlit dashboard
.\run.ps1 -Command "app"
```

