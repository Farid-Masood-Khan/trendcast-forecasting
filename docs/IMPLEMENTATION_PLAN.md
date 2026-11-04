# Implementation Plan — TrendCast (solo build, ~2–3 weeks part-time)

Assumption: ~1.5–2 focused hours/day. Each phase ends at a **Definition of Done** gate — do not start the next phase with the previous gate red. The order is deliberate: **evaluation infrastructure before models, models before UI polish.** A forecasting app built UI-first ends up hiding its errors; this plan makes that structurally impossible.

## Phase 0 — Repo & docs (Day 1)
- Init repo with the seven design docs committed first; `requirements.txt` with pinned versions; clean-venv install test (Prophet's `cmdstanpy` chain is the known breakage point — solve it *today*, not at deploy time).
- **DoD:** `pip install -r requirements.txt` succeeds in a fresh venv; `streamlit hello` runs; docs in repo.

## Phase 1 — Data pipeline (Days 2–4)
- Download WFP Pakistan price CSV from HDX; inspect real columns/units/markets by hand before writing the cleaner.
- Implement `ingest.py` (raw copy + manifest with hash) and `clean.py` (dedupe, frequency alignment, outlier flags) per TRD §2.
- Select the MVP series set: 5–8 series with the longest clean histories (expect wheat flour, rice basmati/iriz, sugar, cooking oil across 2–3 major markets).
- `test_clean.py` on a hand-checked fixture.
- **DoD:** `series.parquet` + `observations.parquet` exist; every MVP series has ≥36 monthly observations; spot-checked values match the source CSV exactly for 10 random points; snapshot footer data renders in a throwaway Streamlit page.

## Phase 2 — Baselines + backtest engine (Days 5–8) ← the heart of the project
- Implement `models.py` baselines (naive, seasonal-naive, drift) and the `Forecaster` interface.
- Implement `backtest.py` rolling-origin engine + `score_models` (MAE/RMSE/MAPE/MASE/PICP).
- Write the leakage sentinel test **before** trusting any number the engine produces.
- Sanity-check by hand: for one series, compute one fold's MAPE manually in a notebook and match the engine.
- **DoD:** backtest table for all MVP series with baselines only; leakage test green; hand-check matches; baseline MAPEs are plausible (if seasonal-naive MAPE looks absurd, the data or the engine is wrong — stop and find out which).

## Phase 3 — Real models + calibration (Days 9–12)
- Add ETS, SARIMA (bounded AIC grid), Prophet behind the same interface.
- Implement `calibrate_intervals` (per-step empirical quantiles, pooled fallback) and PICP reporting.
- Produce the first full model comparison across all MVP series. **Expect and welcome bad news**: document which models lose to baseline, where, and by how much — this becomes Limitations material, not a problem to hide.
- **DoD:** full `model_scores` for all series; every "80%" interval has a measured PICP; at least the calibration fallback path exercised on one sparse series.

## Phase 4 — UI (Days 13–17)
- Build pages in UI_UX_BRIEF order: Forecast page (header strip → insights → chart → accuracy strip → controls → model table → downloads), Backtest explorer, Data & methodology.
- Implement `insights.py` rule-based statements.
- Implement all guard states: insufficient history, low-confidence calibration, worse-than-baseline badge, stale snapshot banner.
- Chart standards pass: bands always on, gaps shown, provenance footer on every figure.
- **DoD:** a non-technical tester (friend/family) can open the app, pick wheat flour, and correctly state "what it might cost in 6 weeks and how much to trust that" in their own words. If they can't, the insights layer gets another iteration before anything else ships.

## Phase 5 — Deploy, document, harden (Days 18–21)
- Deploy to Streamlit Community Cloud from `main`; if Prophet deps fail there, switch to HF Spaces (same repo) — decision point, not a rewrite.
- Write the repo's **Limitations section** (also surfaced in-app) from real findings (template below).
- Final README pass: screenshots of a real forecast + real backtest table; live link at the top.
- Freeze a `v1.0` tag; record the snapshot version shipped.
- **DoD:** public URL live and loads < 3 s; README, docs, Limitations all in repo; CV bullets from README.md are now literally true.

## Milestones

| Milestone | Day | Evidence |
|---|---|---|
| M1: Data you can trust | 4 | Snapshots + manifest + spot-check log |
| M2: Honest engine | 8 | Leakage test green, baseline table |
| M3: Full comparison | 12 | `model_scores` across all series |
| M4: Usable product | 17 | Non-technical tester passes the comprehension check |
| M5: Shipped portfolio piece | 21 | Live URL + v1.0 tag |

## Data-source risks & fallbacks

| Risk | Likelihood | Fallback |
|---|---|---|
| WFP HDX resource URL changes / CSV schema shifts | Medium | Manifest hash detects it; pin the working snapshot — the app never depends on the live URL. Re-map columns in `clean.py` only |
| PBS SPI data only in PDF/HTML tables, messy to parse | High | Treat PBS as cross-check only; WFP alone is sufficient for MVP. Do not burn Phase 1 days scraping PBS |
| Chosen market/commodity has short or gappy history | Medium | Series-selection rule: rank candidates by clean length, pick the best 5–8 — the catalogue is chosen by the data, not by preference |
| Prophet fails to install on Streamlit Cloud | Medium | HF Spaces fallback; last resort: drop Prophet from the deployed set (SARIMA/ETS/baselines still make a complete, honest app) and note it in Limitations |
| No clean Pakistan energy series obtainable | High | Energy domain stays a labelled stretch goal on a public hourly dataset, or is dropped — food prices alone are a complete project |
| Backtests show all models ≈ baseline on most series | Real possibility | **Not a failure.** The headline becomes "on Pakistani food prices, simple baselines are hard to beat — here's the evidence", which is a more impressive research finding than a fake win. The UI and Limitations are already designed to say this |

## Planned Limitations section (to be finalised with real numbers in Phase 5)

The shipped repo will carry a Limitations section covering, at minimum:
1. **Shock blindness** — extrapolation cannot foresee floods, export bans, administered price changes, or currency crashes; measured error during the 2022 flood period will be reported separately to quantify this.
2. **Short histories** — monthly series of 5–10 years give wide calibrated intervals; the dashboard shows their true width rather than narrowing them cosmetically.
3. **Baseline competitiveness** — per-series statement of where no model beat seasonal-naive.
4. **Data caveats** — WFP market coverage is not nationally representative; prices are market-level, not household transaction prices; flagged outliers are retained and their influence is visible.
5. **No causal interpretation** — forecasts are pattern extrapolations; the app makes no claim about why prices move.
6. **Deliberate exclusions** — no neural forecasters, no external regressors (rainfall, exchange rate) in v1; both are named future work with the validation bar they would have to clear.
