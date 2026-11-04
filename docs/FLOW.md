# FLOW — TrendCast User & Data Flows

## 1. Primary user flow: "Should I trust this forecast?"

```mermaid
flowchart TD
    A[Landing: series catalogue] --> B{Pick a series}
    B --> C[History view<br/>source, gaps, outliers shown]
    C --> D[Choose horizon: 4 / 6 / 8 / 12 steps]
    D --> E[Run / view backtest]
    E --> F{Model beats<br/>seasonal naive?}
    F -- No --> G[Badge shown:<br/>'worse than baseline']
    F -- Yes --> H[Ranked model table<br/>MAE · RMSE · MAPE · MASE · coverage]
    G --> H
    H --> I[Forecast view<br/>point + calibrated 80/95% intervals]
    I --> J[Insights panel<br/>plain-language summary quoting real errors]
    J --> K{Export?}
    K -- Yes --> L[Download forecast / backtest CSV<br/>with provenance header]
    K -- No --> M[Pick another series or compare markets]
```

## 2. Guard flow: insufficient or unreliable data

```mermaid
flowchart TD
    A[User selects a series] --> B{Enough clean history?<br/>≥24 monthly / ≥52 weekly obs}
    B -- No --> C[Insufficient-history state:<br/>show history + explain why<br/>no forecast is offered]
    B -- Yes --> D{Backtest origins ≥ 4?}
    D -- No --> E[Forecast shown with<br/>'low-confidence calibration' badge<br/>+ pooled-residual intervals]
    D -- Yes --> F[Standard forecast flow]
    C --> G[Suggest a related series<br/>with sufficient history]
```

## 3. Data flow: source → snapshot → screen

```mermaid
flowchart LR
    subgraph Offline["Offline (developer-run)"]
        S1[WFP price CSV<br/>via HDX] --> I[ingest.py<br/>raw copy + manifest:<br/>URL · hash · timestamp]
        S2[PBS SPI tables] --> I
        I --> CL[clean.py<br/>dedupe · align frequency<br/>flag missing / outliers]
        CL --> SN[(observations.parquet<br/>series.parquet<br/>snapshot vN)]
    end
    subgraph Online["Deployed app (read-only)"]
        SN --> SS[series_store]
        SS --> BT[backtest.py<br/>rolling-origin folds]
        SS --> FC[forecast.py<br/>fit on full history]
        BT --> CAL[interval calibration<br/>from backtest residuals]
        FC --> OUT[forecast result]
        CAL --> OUT
        BT --> INS[insights.py]
        OUT --> UI[Streamlit pages]
        INS --> UI
    end
```

## 4. Backtest fold flow (per series)

```mermaid
flowchart TD
    A[Series observations<br/>sorted, frequency-checked] --> B[Define evaluation zone:<br/>last 24 monthly / 52 weekly steps]
    B --> C[Origins every 4 / 13 steps]
    C --> D[For each origin:<br/>train = data strictly before origin]
    D --> E[Fit each model on train slice]
    E --> F[Forecast up to max horizon]
    F --> G[Score per step vs actuals:<br/>MAE · RMSE · MAPE · interval hit?]
    G --> H{More origins?}
    H -- Yes --> D
    H -- No --> I[Backtest result table<br/>one row per series·model·origin·step]
    I --> J[Aggregate views +<br/>residual pool for calibration]
```

**Leakage invariant (tested):** the only place an origin slices the series is `backtest.py`; a unit test inserts an extreme sentinel value after an origin and asserts that origin's metrics are unchanged.

## 5. Analyst flow: comparing models for a briefing

```mermaid
sequenceDiagram
    actor Analyst
    participant UI as Streamlit UI
    participant SS as series_store
    participant BT as backtest engine
    Analyst->>UI: Select series + "Compare models"
    UI->>SS: get_series(series_id)
    SS-->>UI: metadata + observations
    UI->>BT: run_backtest(series_id, all models)
    BT-->>UI: result table (cached by snapshot vN)
    UI-->>Analyst: ranked table + per-step error chart
    Analyst->>UI: Download CSV
    UI-->>Analyst: CSV with source, snapshot, run-date header
```

## 6. Refresh flow (stretch, FR-14)

Developer re-runs ingestion → new snapshot committed → app redeploys → footer "Data as of" updates → cached backtests invalidate automatically because the cache key includes the snapshot version.
