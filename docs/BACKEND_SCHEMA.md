# Backend Schema & Service Contracts — TrendCast

Streamlit app with no separate server: the "backend" is a **service layer** of pure, typed Python functions over parquet snapshots, plus Streamlit cache as the only runtime state. This document defines the data model and the function contracts the UI is allowed to call. The UI must never read parquet files or import model libraries directly.

## 1. Data model (parquet snapshots in `data/processed/`)

### 1.1 `series.parquet` — one row per forecastable series

| Field | Type | Notes |
|---|---|---|
| `series_id` | str (PK) | Stable slug, e.g. `wfp_wheat_flour_lahore_retail` |
| `display_name` | str | "Wheat flour (retail) — Lahore" |
| `commodity` | str | e.g. `wheat_flour`, `rice_basmati`, `sugar`, `oil_cooking` |
| `market` | str | City/market name; `national_avg` allowed |
| `source` | str | `WFP_HDX` \| `PBS_SPI` \| `PUBLIC_ENERGY` |
| `source_url` | str | Exact dataset/resource URL for provenance |
| `frequency` | str | `monthly` \| `weekly` \| `daily` |
| `unit` | str | As published, e.g. `PKR/kg` |
| `first_obs` / `last_obs` | date | Coverage of the cleaned series |
| `n_obs` | int | Clean observation count (drives FR-8 reliability gate) |
| `aggregation` | str | `none` \| `weekly_to_monthly_median` — how forecasting frequency was derived |
| `snapshot_version` | int | FK to manifest |

### 1.2 `observations.parquet` — one row per (series, date)

| Field | Type | Notes |
|---|---|---|
| `series_id` | str (FK) | |
| `date` | date | Period start |
| `value` | float | Observed price/level in `unit` |
| `quality` | str | `observed` \| `outlier_flag` (missing periods are *absent rows*, detected by frequency check — never fabricated rows) |

### 1.3 `manifest.json` — snapshot provenance

```json
{
  "snapshot_version": 3,
  "created_at": "2026-11-02T10:15:00+05:00",
  "sources": [
    {"source": "WFP_HDX", "url": "https://data.humdata.org/...", "retrieved_at": "2026-11-02", "sha256": "…", "rows": 18234}
  ]
}
```

### 1.4 Runtime result tables (in-memory / cache, exportable to CSV)

**`backtest_results`** — one row per (series, model, origin, step):

| Field | Type | Notes |
|---|---|---|
| `series_id`, `model` | str | `model` ∈ `naive`, `seasonal_naive`, `drift`, `ets`, `sarima`, `prophet` |
| `origin_date` | date | Forecast origin (train = strictly before this) |
| `step` | int | Horizon step, 1-based |
| `actual` / `predicted` | float | |
| `lower_80` / `upper_80` / `lower_95` / `upper_95` | float | Calibrated intervals (post-calibration values) |
| `abs_error`, `pct_error` | float | Derived at write time so UI and exports can never disagree |

**`forecast_runs`** — one row per (series, model, step) for the live forecast:

`series_id`, `model`, `run_at` (ISO ts), `snapshot_version`, `step`, `target_date`, `point`, `lower_80`, `upper_80`, `lower_95`, `upper_95`.

**`model_scores`** — aggregated view derived from `backtest_results`:
`series_id`, `model`, `mae`, `rmse`, `mape`, `mase` (vs seasonal-naive), `picp_80`, `picp_95`, `n_origins`, `beats_baseline` (bool, mape < seasonal-naive mape).

## 2. Service-layer function contracts

All functions are pure (same inputs → same outputs), raise typed errors, and live in `src/`. DataFrames below are pandas; column names are exactly the schema fields above.

### `series_store.py`

```python
def list_series(source: str | None = None) -> pd.DataFrame
    """All rows of series.parquet, optionally filtered by source."""

def get_series(series_id: str) -> dict
    """One series' metadata row as a dict. Raises SeriesNotFound."""

def get_observations(series_id: str, start: date | None = None,
                     end: date | None = None) -> pd.DataFrame
    """Observations sorted ascending by date. Never fills missing periods."""
```

### `models.py` — one interface for every forecaster

```python
class Forecaster(Protocol):
    name: str
    def fit(self, history: pd.Series) -> None: ...
    def predict(self, steps: int) -> np.ndarray: ...   # point forecasts only

def make_model(name: str, frequency: str) -> Forecaster
    """Factory. Seasonal period derived from frequency (12 monthly / 52 weekly).
       SARIMA order chosen inside fit() by AIC over the bounded grid in TRD §3.1."""
```

Models return **point forecasts only**. Intervals are the calibration layer's job — this separation is what makes honest coverage possible.

### `backtest.py`

```python
def run_backtest(series_id: str, model_names: list[str],
                 max_horizon: int = 12) -> pd.DataFrame
    """Rolling-origin evaluation per TRD §3.2.
       Returns backtest_results rows (intervals pre-calibration = model-naive
       symmetric placeholder is FORBIDDEN: intervals are filled by calibrate()
       before the table leaves this module).
       Raises InsufficientHistory if origins < 4 (caller decides the
       low-confidence path per FLOW §2)."""

def score_models(backtest: pd.DataFrame) -> pd.DataFrame
    """Aggregates backtest_results -> model_scores, incl. MASE and PICP."""
```

### `forecast.py`

```python
def calibrate_intervals(backtest: pd.DataFrame) -> dict[tuple[str, int], dict]
    """Per (model, step): empirical |residual| quantiles at 0.80 / 0.95.
       Falls back to pooled-across-steps quantiles, flagged
       {'calibration': 'pooled'} vs {'calibration': 'per_step'}."""

def run_forecast(series_id: str, model_name: str, horizon: int) -> pd.DataFrame
    """Fits on full history, applies calibration from the series' latest
       backtest. Returns forecast_runs rows."""
```

### `insights.py`

```python
def build_insights(series_id: str, scores: pd.DataFrame,
                   forecast: pd.DataFrame) -> list[str]
    """3-5 plain-language statements generated ONLY from computed facts
       (trend sign, seasonal consistency, MAPE, PICP, baseline verdict).
       No statement may assert a cause or a certainty."""
```

## 3. Caching model

| Layer | Mechanism | Key | Invalidation |
|---|---|---|---|
| Snapshot reads | `st.cache_data(ttl=None)` | `snapshot_version` | New committed snapshot (version bump) |
| Backtests | `st.cache_data` | `(series_id, snapshot_version, tuple(model_names), max_horizon)` | Snapshot bump or model config change (config hash in key) |
| Forecasts | `st.cache_data` | `(series_id, model, horizon, snapshot_version, backtest_key)` | Follows backtest key |
| Raw downloads | Files on disk (`data/raw/`) | filename + sha256 in manifest | Re-run of ingest only |

Rules: cache stores **result tables, never fitted model objects** (keeps memory bounded and results serialisable/exportable). Every cached result carries its `snapshot_version` so the UI can display provenance and refuse to mix versions.

## 4. Error taxonomy

| Error | Raised when | UI behaviour |
|---|---|---|
| `SeriesNotFound` | Unknown `series_id` | Catalogue fallback + message |
| `InsufficientHistory` | Below FR-8 thresholds or <4 backtest origins | Guard-flow states in UI brief |
| `ModelFitError` | A model fails on a fold (e.g. SARIMA non-convergence) | Model marked failed for that fold; if it fails >50% of folds, it's excluded and the exclusion is *shown* in the comparison table, not silent |
| `StaleSnapshot` | Snapshot older than 45 days at runtime | Staleness banner |

## 5. Testing contracts

- `test_backtest.py::test_no_future_leakage` — sentinel-value test per FLOW §4.
- `test_backtest.py::test_baseline_present` — every backtest output contains both naive baselines.
- `test_clean.py` — dedupe, frequency, and outlier-flag invariants on a fixed fixture.
- Contract test: `score_models(run_backtest(fixture))` must produce `beats_baseline` consistent with a hand-computed fixture result.
