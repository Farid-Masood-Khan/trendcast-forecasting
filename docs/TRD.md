# TRD — TrendCast Time-Series Forecasting Dashboard

## 1. Architecture overview

Single Streamlit application with a strict **service layer**: the UI (`app.py` + page modules) never touches raw data or model code directly; it calls typed service functions (contracts in `BACKEND_SCHEMA.md`). This keeps every computation testable outside Streamlit and makes the evaluation logic auditable — the point of the project.

```
┌────────────┐   ┌──────────────────┐   ┌─────────────────────┐
│  Sources   │──▶│  Ingest + Clean  │──▶│  Processed snapshots │
│ PBS / WFP  │   │ (offline script) │   │  (parquet + manifest)│
│ (HDX CSVs) │   └──────────────────┘   └──────────┬──────────┘
└────────────┘                                     │ read-only
                              ┌────────────────────▼───────────────────┐
                              │           Service layer (src/)          │
                              │ series_store · models · backtest ·      │
                              │ forecast · insights                     │
                              └────────────────────┬───────────────────┘
                                                   │ typed results
                              ┌────────────────────▼───────────────────┐
                              │        Streamlit UI (app.py)            │
                              │ catalogue · history · backtest ·        │
                              │ forecast · methodology                  │
                              └─────────────────────────────────────────┘
```

Ingestion is an **offline, manual/scheduled step**, not a request-path operation: the deployed app reads committed parquet snapshots. This guarantees the app is fast, the exact data behind every chart is versioned, and a source going down never breaks the demo.

## 2. Data pipeline

1. **Ingest** (`src/ingest.py`): download WFP Pakistan price CSV from HDX (dataset: *WFP food prices for Pakistan*, resource CSV) and, where obtainable, PBS SPI weekly prices. Write raw files untouched to `data/raw/` with a `manifest.json` entry: source URL, retrieval timestamp, file hash, row count.
2. **Clean** (`src/clean.py`): standardise column names; parse dates; convert prices to PKR per standard unit as published (no silent unit conversion — flag inconsistencies); deduplicate on (series, date); sort; attach quality flags per observation: `observed`, `missing` (gap in the expected frequency), `outlier_flag` (|z-score of log-differences| > 4, flagged, **never deleted**).
3. **Frequency policy**: monthly series stay monthly; weekly SPI series are kept weekly for history view but aggregated to monthly (median) for forecasting in MVP, to keep horizons comparable. Aggregation rule is recorded in the series metadata.
4. **Snapshot**: write `data/processed/observations.parquet` and `series.parquet`; bump snapshot version in the manifest. The app displays the snapshot date everywhere ("Data as of …").

## 3. Forecasting methodology

### 3.1 Model set (one interface: fit(history) → predict(steps))

| Model | Implementation | Role |
|---|---|---|
| Naive | last observed value | Sanity floor |
| Seasonal naive | value from one seasonal period ago (12 monthly / 52 weekly) | **The gate**: models must beat this to be recommended |
| Drift | last value + average historical change × step | Cheap trend baseline |
| ETS | statsmodels `ExponentialSmoothing` (trend + seasonal, damped trend variant in grid) | Classical smoother |
| SARIMA | statsmodels `SARIMAX`, order selected by AIC over a bounded grid (p,d,q ≤ 2, seasonal P,D,Q ≤ 1, s = frequency) | Classical ARIMA family |
| Prophet | `prophet` with yearly seasonality; weekly seasonality only for weekly series; no external regressors in MVP | Handles multiple seasonality + holidays-ish patterns |

No neural models in MVP by design: on short monthly series (often 60–120 points) they cannot be honestly validated, and including them would contradict the project's evaluation-first claim. This decision is documented in the repo's Limitations section as a deliberate scope call.

### 3.2 Backtesting design (the core of the project)

- **Scheme**: rolling-origin evaluation with an **expanding window**. The final 24 steps (monthly) / 52 steps (weekly) of each series are the evaluation zone. Origins are placed every 4 steps (monthly) / 13 steps (weekly) across that zone, giving ≥5 origins.
- **At each origin**: train on data strictly before the origin, forecast up to the max horizon (12 monthly steps), score each horizon step against actuals.
- **Hard rule**: a fold may never see data at or after its origin. Enforced by construction (single slicing point in `backtest.py`) and by unit tests that inject a sentinel future value and assert metrics don't change.
- **Metrics per model, per horizon step, and aggregated**: MAE, RMSE, MAPE (with a guard: MAPE reported only where actuals > 0, always true for prices; sMAPE kept as backup), and MASE against seasonal-naive (MASE < 1 = beats baseline — the single most interpretable number in the UI).
- **Reporting**: results stored as a tidy table (contract in `BACKEND_SCHEMA.md`) — one row per (series, model, origin, step). The UI aggregates; the raw table is downloadable (FR-9).

### 3.3 Interval estimation and calibration

Model-native intervals (Prophet's, SARIMAX's) are **not trusted directly** — on short, shock-prone series they are typically too narrow. Instead:

1. Collect backtest residuals per horizon step across origins.
2. Calibrated interval half-width at step *h* = empirical quantile of |residuals at *h*| for the target level (80% → 0.80 quantile, 95% → 0.95), applied symmetrically around the point forecast (log-scale for prices to keep lower bounds positive).
3. Report **PICP** (prediction interval coverage probability) from the backtest: if the "80%" interval only covered 55% of actuals, the UI says exactly that next to the forecast.
4. Fallback: if a series has too few origins for stable quantiles, widen using pooled residuals across steps and badge the forecast "low-confidence calibration".

### 3.4 Insights generation

Rule-based, from computed facts only (no LLM, nothing invented):
- Trend statement from the drift of the last 6 observations vs the forecast direction.
- Seasonality statement when a calendar pattern (e.g. Ramzan/Eid months, harvest months) shows a consistent sign in ≥70% of historical instances.
- Confidence statement quoting the model's aggregate backtest MAPE and interval coverage in plain words ("over the past year this method's 4-week-ahead estimates were off by about ±6% on average").

## 4. Tech choices and rationale

| Choice | Rationale | Rejected alternative |
|---|---|---|
| Streamlit | One developer, data-native widgets, free hosting | Dash/Flask+React — 3× the build time for identical analytical value |
| statsmodels SARIMAX/ETS | Transparent, citable, deterministic | pmdarima auto_arima — extra dependency; bounded manual grid is more auditable for a portfolio piece |
| Prophet | Different inductive bias (additive seasonality), well-known to reviewers | NeuralProphet — immature, heavier |
| Parquet snapshots | Versioned, fast, typed; the demo can never break from a live-source outage | Live API calls per request — slow, fragile, unreproducible |
| Plotly | Interval bands + hover provenance in one figure object | Matplotlib — static, weaker interval UX |

## 5. Performance requirements

- Cold load of the app with committed snapshots: < 3 s to interactive.
- Selecting a series and rendering history: < 1 s (pure reads from parquet).
- Full backtest for one series (all models, all origins): < 20 s on Streamlit Cloud's free tier; results cached by (series_id, snapshot_version, model_config_hash) via `st.cache_data`, so repeat views are instant.
- Forecast generation after backtest: < 5 s (models refit on full history once, cached identically).
- Memory: processed dataset < 50 MB parquet; app must stay within free-tier limits (~1 GB).

## 6. Deployment

- **Primary**: Streamlit Community Cloud, deployed from the GitHub repo's `main` branch; `requirements.txt` pinned (prophet's build is the known risk — pin `prophet`, `cmdstanpy` chain and test the exact pins in a clean venv before first deploy).
- **Fallback**: Hugging Face Spaces (Streamlit SDK) with the same repo — used if Prophet's native deps fail on Streamlit Cloud.
- **Config**: no secrets required (all data is public). Snapshot version and "data as of" date rendered in the footer of every page.
- **Refresh flow**: developer runs `python -m src.ingest` locally → new parquet + manifest committed → cloud app redeploys automatically.
