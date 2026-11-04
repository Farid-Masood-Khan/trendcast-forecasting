# PRD — TrendCast Time-Series Forecasting Dashboard

## 1. Problem

Decision-makers who depend on Pakistani food prices — small retailers setting purchase quantities, flour-mill and grocery operators, NGO/food-security analysts, researchers, and ordinary households budgeting through inflation — have access to historical price data (PBS, WFP) but no accessible tool that answers the only question that matters: **"What is this likely to cost in the next few weeks, and how much should I trust that estimate?"**

Existing options fail in two directions:
- Raw government/NGO spreadsheets: accurate data, zero interpretation, no forecast.
- Generic forecasting demos: attractive charts, no evaluation — a single trend line with no evidence the method works on this data at all.

TrendCast exists in the gap: real local data, real forecasts, and **published proof of how accurate those forecasts have recently been**.

## 2. Target users

| User | Job to be done | What TrendCast must give them |
|---|---|---|
| Small business owner / retailer (primary) | Decide stock quantities and pricing for the next 2–8 weeks | A price outlook in rupees with an honest range, in plain language, in under a minute |
| Food-security / NGO analyst | Brief on expected price pressure by commodity and market | Backtested model comparison, downloadable results, provenance for every figure |
| Researcher / student | Reproduce or extend a forecasting study on South Asian price data | Documented methodology, open data pipeline, per-horizon error tables |
| Portfolio reviewer (professor/employer) | Judge the builder's engineering and statistical judgement | Evaluation-first design, leakage tests, Limitations section, clean architecture |

## 3. Goals

1. Forecast the selected series 4–12 weeks (or 3–6 months for monthly series) ahead with calibrated uncertainty intervals.
2. Evaluate every model by rolling-origin backtest before its forecast is shown; surface the results, never bury them.
3. Make the output understandable to a non-statistician without lying to them: plain-language insights that quote real error magnitudes.
4. Keep the whole pipeline reproducible: pinned data snapshots, logged provenance, documented cleaning rules.

## 4. Non-goals

- **No trading/financial advice.** Food prices and demand, not securities. No buy/sell recommendations.
- **No real-time/streaming data.** Sources update weekly/monthly; the app is a snapshot tool and says so.
- **No causal claims.** The dashboard never claims *why* a price will move; it extrapolates patterns and says that is what it is doing.
- **No user accounts, no saved personal data.** Public read-only tool.
- **No deep-learning models in MVP.** LSTM/Transformer forecasting is explicitly out of scope until classical baselines are beaten and documented (see TRD rationale).

## 5. User stories

1. As a retailer, I pick "Wheat flour, Lahore" and a 6-week horizon, and I see the expected price path, the likely range, and a sentence telling me how accurate this model was over the last year — so I can decide how much stock to buy.
2. As an analyst, I compare Prophet vs SARIMA vs ETS vs seasonal-naive on the same series and see, per horizon step, which model actually performed best in backtests — so my briefing cites evidence, not defaults.
3. As an analyst, I download the backtest results table (CSV) with the data source and run date attached — so my numbers are auditable.
4. As a researcher, I open the methodology view and see the exact backtest design (origins, window, metrics, interval calibration) — so I can reproduce or critique it.
5. As any user, when a series has too little clean history, the app tells me forecasting isn't reliable here instead of drawing a confident line — so I'm never misled.
6. As a reviewer, I read the Limitations section and see named failure modes (2022 flood period, administered-price changes) with their measured error impact.

## 6. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | Series catalogue: browse/search series by commodity, market, source; each entry shows date range, frequency, observation count, last update | MVP |
| FR-2 | History view: line chart with missing points and flagged outliers visible (not silently removed), source + cleaning notes attached | MVP |
| FR-3 | Model set: Prophet, SARIMA (auto order selection within bounded grid), ETS, naive, seasonal-naive — behind a single interface | MVP |
| FR-4 | Rolling-origin backtest engine: ≥4 origins, expanding window, per-step and aggregate MAE/RMSE/MAPE, interval coverage (PICP) at 80%/95% | MVP |
| FR-5 | Forecast view: point forecast + 80%/95% intervals, horizon selectable (4/6/8/12 steps), intervals calibrated on backtest residuals | MVP |
| FR-6 | Baseline gate: any model whose backtest MAPE is worse than seasonal-naive is badged "worse than baseline — shown for comparison" | MVP |
| FR-7 | Insights panel: 3–5 generated statements quoting direction, seasonal patterns, and the model's recent error range in plain language | MVP |
| FR-8 | Reliability gate: series with <24 clean observations (monthly) or <52 (weekly) show a "insufficient history" state instead of a forecast | MVP |
| FR-9 | Export: backtest table and forecast table downloadable as CSV with provenance header | MVP |
| FR-10 | Methodology page in-app: backtest design, metric definitions, interval calibration, known limitations | MVP |
| FR-11 | Multi-series overlay: compare the same commodity across 2–3 markets | Stretch |
| FR-12 | Event annotations: mark known shocks (2022 floods, Ramzan periods, import bans) on history and exclude/include toggle in backtest | Stretch |
| FR-13 | Energy-demand series (hourly→daily) with day-ahead style evaluation as a second domain | Stretch |
| FR-14 | Scheduled data refresh (weekly job updating processed snapshots) | Stretch |

## 7. Success metrics

**Product/quality metrics (measured in-app, visible in the repo):**
- Every displayed forecast has a completed backtest behind it — 100% coverage, no exceptions.
- Interval calibration: empirical coverage of the "80%" interval across backtests falls within 65–92% on the shipped series set (i.e. intervals are honest, not decorative).
- At least one non-trivial model beats seasonal-naive on a majority of shipped series — or the dashboard says, per series, that none did.
- Zero data-leakage defects: automated tests prove no fold trains on data at or after its origin.

**Portfolio metrics (the builder's own):**
- Public deployment link live; README + all six design docs in repo.
- A reviewer can go from landing page to a backtested forecast in ≤3 clicks and ≤60 seconds.

## 8. Scope summary

**MVP:** PBS/WFP food-price series (5–8 series), 5 models incl. baselines, backtesting, calibrated forecasts, insights, exports, methodology + limitations pages.
**Stretch:** multi-market overlay, shock annotations, energy domain, scheduled refresh, a "what changed since last run" diff view.
