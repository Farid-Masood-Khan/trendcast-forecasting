# UI/UX Brief — TrendCast Dashboard

## Design intent

TrendCast is a trust product disguised as a chart product. Every layout decision serves one question in the user's head: **"How much should I believe this number?"** Uncertainty is not a footnote or a settings toggle — it is rendered at the same visual weight as the forecast itself. If a design choice makes the forecast look more confident than the backtest justifies, the design is wrong.

Audience split: a non-technical primary user (retailer/household) who reads the top of the page, and an analyst/reviewer who reads everything. The layout serves both by layering: **answer first, evidence below, methodology last** — nothing important hidden, nothing technical forced.

## Page structure (single app, sidebar navigation)

### Page 1 — Forecast (default landing)

Top-to-bottom order is fixed and deliberate:

1. **Series header strip** — series name ("Wheat flour (retail, avg) — Lahore"), source badge ("WFP via HDX"), data-as-of date, frequency. Provenance is visible before any number.
2. **Insights panel** (see below) — 3–5 plain-language statements. This is the first content a non-technical user reads.
3. **Forecast chart** — history (solid), point forecast (dashed), 80% band (darker), 95% band (lighter). History and forecast visually separated by a vertical "today" rule.
4. **"How accurate has this been?" strip** — the selected model's backtest MAPE and interval coverage in one line of text plus small numbers: e.g. *"Over the past 2 years, this method's forecasts for this series were off by ±6% on average (MAPE 6.1%). Its 80% range contained the real price 74% of the time."*
5. **Controls row** (see Controls).
6. **Model comparison table** — all models ranked by backtest MAPE, with MASE and coverage columns; baseline rows always present; rows worse than seasonal-naive carry the badge `⚠ worse than baseline`.
7. **Download buttons** — forecast CSV, backtest CSV.

### Page 2 — Backtest explorer

- Per-step error chart (error vs horizon step, per model) — shows error *growing* with horizon, which is the honest shape of forecasting.
- Origin-by-origin table (expandable): each fold's train end date, and per-step errors.
- Metric definitions in plain language next to the numbers ("MAPE: average % the forecast missed by").

### Page 3 — Data & methodology

- Series catalogue table with observation counts, gaps, snapshot version.
- The full methodology text (backtest design, calibration method), the Limitations section, and links to sources.

## Controls

| Control | Type | Behaviour |
|---|---|---|
| Series picker | Sidebar selectbox, grouped by commodity → market | Changing series resets model selection to "best by backtest" |
| Horizon | Segmented control: 4 / 6 / 8 / 12 steps | Re-renders forecast + per-step errors; default 8 |
| Model toggle | Radio: "Best by backtest (recommended)" / each model by name / "Compare all" | Default is the backtest winner — the app has an opinion and shows its reasoning |
| Interval display | Toggle: 80% / 95% / both | Default both |
| Show history window | Slider: 1 / 2 / 3 / 5 years | Chart only; never affects computation |

No control may silently change evaluation results: horizon and model changes recompute or re-slice from the same stored backtest table, and the UI says which.

## Chart standards

- **One y-axis, always.** No dual axes, no truncated axes on price charts (axis starts at a round number ≤ 90% of the data minimum, and the chart notes it if it doesn't start at 0 — for prices it normally won't, and that's stated, not hidden).
- **Intervals are bands, never error-bar whiskers** on the main chart; whiskers imply precision the data doesn't have.
- History = solid dark line; forecast = dashed line in a distinct hue; bands = same hue, two opacities. Colourblind-safe palette (Okabe–Ito); colour is never the only encoding — forecast segments are also dashed.
- Missing data appears as **gaps in the line**, never interpolated visually. Outlier-flagged points get a marker and a tooltip ("flagged as outlier — kept in data, see methodology").
- Every chart carries a footer line: source, snapshot date, and (on forecast charts) the model's backtest MAPE. A screenshot of any chart must be self-explanatory out of context.
- Tooltips show exact values with units (PKR/kg etc.) and dates in `Mon YYYY` format.

## Displaying uncertainty honestly (non-negotiable rules)

1. The forecast line is **never shown without its interval band** on the same chart.
2. Interval width comes from backtest calibration (TRD §3.3); if coverage in backtests was poor, the strip on Page 1 says so in words, not just numbers.
3. Language discipline: the UI says "expected range", "the model estimates", never "the price will be". Insights templates are worded accordingly.
4. When all models lose to the baseline, the insights panel leads with that fact: *"No model beat the simple baseline on this series recently — treat any forecast here as weak evidence."*
5. Shock periods inside the history (e.g. mid-2022 flood months) are shaded and labelled, so users see the regime where extrapolation failed before.

## Key states

| State | Presentation |
|---|---|
| Loading / computing backtest | Progress note naming what's happening ("Backtesting 5 models × 5 origins…"), results cached afterwards |
| Insufficient history (FR-8) | History chart shown; forecast area replaced by an explanation card + suggested alternative series |
| Low-confidence calibration | Amber badge on forecast chart + one sentence explaining pooled-residual intervals |
| Model worse than baseline | Badge in comparison table; if it's the selected model, a warning line above the chart |
| Stale snapshot (>45 days) | Banner: "Data as of {date}. Prices may have moved since." |
| Empty catalogue filter | Plain empty state with a reset action |

## Accessibility & tone

- Minimum body text 14px equivalent; all badges also carry text labels (not colour-only).
- Plain-English insights: no unexplained acronyms (MAPE is always expanded on first use per page).
- Tone: calm and factual. No hype words ("powerful AI predicts…"), no false modesty either — where the model did well, the numbers say so.
