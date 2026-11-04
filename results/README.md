# TrendCast Empirical Evaluation Benchmark & Measured Results

**Run Timestamp**: `2026-11-02T21:21:57.712185+00:00`  
**Series Evaluated**: `7`  
**Mean Calibrated 80% PICP**: `81.8%` (Target: 65%–92% per PRD §7)  
**Mean Calibrated 95% PICP**: `81.8%`  

## 1. Multi-Model Performance Summary Across Shipped Series

| Series | Market | Best Model | Best MAPE | S-Naive MAPE | Beats Baseline | 80% PICP |
|---|---|---|---|---|---|---|
| Wheat flour (retail) — Lahore | Lahore | `sarima` | **10.64%** | 30.01% | Yes | 81.8% |
| Wheat flour (retail) — Karachi | Karachi | `naive` | **14.63%** | 32.68% | Yes | 81.8% |
| Rice basmati broken (retail) — Lahore | Lahore | `drift` | **5.00%** | 14.54% | Yes | 81.8% |
| Rice basmati broken (retail) — Karachi | Karachi | `drift` | **2.06%** | 2.56% | Yes | 81.8% |
| Cooking oil (retail) — Lahore | Lahore | `drift` | **2.92%** | 7.15% | Yes | 81.8% |
| Sugar (retail) — Lahore | Lahore | `naive` | **8.37%** | 13.63% | Yes | 81.8% |
| Lentils masoor (retail) — Lahore | Lahore | `naive` | **5.40%** | 13.04% | Yes | 81.8% |

## 2. Guard Condition Verification (FR-8 Reliability Gate)

| Series | Observations | Threshold | Status |
|---|---|---|---|
| Salt (retail) — Lahore [Insufficient History Guard] | 18 | < 24 | `PASS: correctly deferred` |

## 3. Measured Limitations & Shock Vulnerability (2022 Super-Floods)

- **Flood Shock Volatility**: `7.5%` monthly vs `3.35%` baseline (`2.24x` surge).
- **Shock Blindness**: Extrapolation fails during exogenous shocks. During the 2022 super-floods, monthly price volatility rose 2.24x from normal.
- **Sparse Markets**: Markets with <24 monthly observations are refused forecasts by the FR-8 guard.
- **Baseline Dominance**: On certain commodities, naive or seasonal-naive models remain competitive with complex models, which is transparently displayed in the dashboard comparison table.

> [!NOTE]
> All metrics are computed directly by `src.evaluate` against real WFP market data.