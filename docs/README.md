# TrendCast — Time-Series Forecasting Dashboard

An interactive Streamlit dashboard for forecasting real-world time series that matter to Pakistan — food commodity prices and energy demand — with **honest, backtested evaluation** as its headline feature. TrendCast doesn't just show a forecast line; it shows how wrong that forecast is likely to be, proven against held-out history before you trust it.

## Why it matters

Pakistan's food inflation is a recurring crisis: wheat flour, rice, sugar, and cooking oil prices swing sharply with harvests, imports, floods, and exchange-rate shocks, and households, small retailers, and aid planners usually find out late. Public price data exists (Pakistan Bureau of Statistics, WFP market monitoring), but it sits in spreadsheets nobody can act on. TrendCast turns that raw data into a short-horizon forecast **with measured error bars**, so a small business owner deciding how much stock to buy, or an analyst briefing on food security, can see both the expected price path and how much confidence it deserves.

The design principle: **a forecast without a backtest is a guess with a chart.** Every number this dashboard shows is accompanied by the error the same method made on the recent past.

## Features

- **Series explorer** — pick a commodity/market (e.g. wheat flour retail price, Lahore; basmati rice, Karachi) or an energy-demand series and view its history with missing-data and outlier annotations.
- **Model comparison** — Prophet, ARIMA/SARIMA (statsmodels), and ETS run side-by-side against **naive and seasonal-naive baselines**. A model that can't beat "tomorrow = today" is labelled as such.
- **Rolling-origin backtesting** — expanding-window evaluation across multiple forecast origins; reports MAE, RMSE, MAPE, and prediction-interval coverage per model, per horizon step.
- **Forecasts with honest intervals** — point forecast plus 80%/95% intervals whose width is calibrated against backtest residuals, not just model-internal variance.
- **Plain-language insights panel** — auto-generated statements like "Wheat flour rose in 9 of the last 12 Ramzan periods; the model expects a further 3–5% rise over the next 4 weeks, but its 4-week error over the past year averaged ±6%, so treat this as directional."
- **Data provenance** — every chart states its source, last update, and any cleaning applied. No silent imputation.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| App / UI | Streamlit | Single-developer speed; native fit for data apps |
| Data wrangling | pandas, NumPy | Standard, auditable transformations |
| Forecasting | Prophet, statsmodels (SARIMAX, ETS) | Complementary inductive biases; both pip-installable |
| Baselines | Custom (naive, seasonal naive, drift) | The honesty benchmark every model must beat |
| Charts | Plotly | Interactive intervals, hover provenance |
| Caching | `st.cache_data` + parquet snapshots | Fast reloads; reproducible runs |
| Deployment | Streamlit Community Cloud (fallback: Hugging Face Spaces) | Free, public link for CV/portfolio |

## Data sources (with fallbacks)

1. **WFP VAM food price data for Pakistan** via Humanitarian Data Exchange (HDX) — monthly retail prices by market and commodity. Primary source.
2. **Pakistan Bureau of Statistics (PBS)** — weekly SPI (Sensitive Price Indicator) commodity prices. Secondary/cross-check.
3. **Energy demand fallback** — a well-known public hourly energy-consumption dataset (e.g. PJM hourly energy consumption, Kaggle) if a Pakistan grid series can't be obtained in clean form; clearly labelled as a methods demonstrator, not Pakistan data.

## Planned repo structure

```
trendcast/
├── README.md
├── PRD.md  TRD.md  FLOW.md  UI_UX_BRIEF.md  BACKEND_SCHEMA.md  IMPLEMENTATION_PLAN.md
├── app.py                  # Streamlit entry point (thin; delegates to services)
├── requirements.txt
├── data/
│   ├── raw/                # untouched downloads (gitignored except samples)
│   └── processed/          # parquet snapshots actually loaded by the app
├── src/
│   ├── ingest.py           # download + provenance logging
│   ├── clean.py            # dedupe, frequency alignment, outlier flags
│   ├── series_store.py     # series metadata + observation access
│   ├── models.py           # Prophet / SARIMAX / ETS / baselines behind one interface
│   ├── backtest.py         # rolling-origin evaluation engine
│   ├── forecast.py         # forecast runs + interval calibration
│   └── insights.py         # plain-language insight generation
└── tests/
    ├── test_backtest.py    # leakage checks: no future data in any fold
    └── test_clean.py
```

## CV bullets this project earns when built

- Built **TrendCast**, a Streamlit forecasting dashboard for Pakistani food-price series (WFP/PBS data) comparing Prophet, SARIMA, and ETS against naive baselines using rolling-origin backtests (MAE/RMSE/MAPE + interval coverage), deployed publicly with full methodology documentation.
- Designed an evaluation-first forecasting pipeline: interval widths calibrated from backtest residuals, per-horizon error reporting, and automated leakage tests — models that fail to beat a seasonal-naive baseline are flagged in the UI rather than hidden.
- Shipped end-to-end solo: data ingestion with provenance logging, service-layer architecture, Plotly visualisations with uncertainty-first chart standards, and a documented Limitations section quantifying where the forecasts break down (shock periods, sparse markets).
