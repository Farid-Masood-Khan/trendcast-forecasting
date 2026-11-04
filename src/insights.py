"""Rule-based insight generator from empirical forecast and backtest facts.

Strictly adheres to TRD §3.4 and UI_UX_BRIEF.md:
- Purely factual: direction, drift, seasonality sign, backtest error magnitude, interval coverage.
- Strictly non-causal: no assertions of 'why' prices moved or will move.
"""

from __future__ import annotations

import pandas as pd

from src.series_store import get_observations, get_series


def build_insights(
    series_id: str,
    scores: pd.DataFrame,
    forecast: pd.DataFrame,
    selected_model: str | None = None,
) -> list[str]:
    """Generate 3-5 plain-language statements from computed facts only."""
    insights: list[str] = []

    obs = get_observations(series_id)
    series_meta = get_series(series_id)
    unit = series_meta.get("unit", "PKR/KG")

    if scores.empty or forecast.empty or obs.empty:
        return ["Insufficient data available to generate insights."]

    if selected_model is None:
        selected_model = str(scores.iloc[0]["model"])

    m_score = scores[scores["model"] == selected_model]
    if m_score.empty:
        m_score = scores.iloc[0:1]
        selected_model = str(m_score["model"].iloc[0])

    mape = float(m_score["mape"].iloc[0])
    picp_80 = float(m_score["picp_80"].iloc[0])
    beats_baseline = bool(m_score["beats_baseline"].iloc[0])

    # 1. Baseline & Reliability statement
    all_lose = bool((scores[scores["model"] != "seasonal_naive"]["beats_baseline"] == False).all())  # noqa: E712
    if all_lose:
        insights.append(
            "Baseline alert: No statistical model outperformed the seasonal-naive baseline on this "
            "series during recent backtests. Treat any forward forecast as weak evidence."
        )
    elif not beats_baseline:
        insights.append(
            f"Model warning: Selected model '{selected_model}' had higher backtest error (MAPE {mape:.1f}%) "
            f"than the simple seasonal-naive baseline. Consider using the top-ranked model instead."
        )
    else:
        insights.append(
            f"Baseline verified: Model '{selected_model}' outperformed the seasonal-naive benchmark with an "
            f"average backtest MAPE of {mape:.1f}% across held-out test origins."
        )

    # 2. Historical drift vs Forecast direction
    last_val = float(obs["value"].iloc[-1])
    n_lookback = min(6, len(obs))
    prev_val = float(obs["value"].iloc[-n_lookback])
    recent_change_pct = ((last_val - prev_val) / prev_val) * 100.0 if prev_val > 0 else 0.0

    forecast_end_val = float(forecast["point"].iloc[-1])
    forecast_horizon = len(forecast)
    forecast_change_pct = ((forecast_end_val - last_val) / last_val) * 100.0 if last_val > 0 else 0.0

    dir_past = "rose" if recent_change_pct > 1.0 else ("fell" if recent_change_pct < -1.0 else "held steady")
    dir_future = "an upward" if forecast_change_pct > 1.5 else ("a downward" if forecast_change_pct < -1.5 else "a relatively flat")

    insights.append(
        f"Trend outlook: Over the past {n_lookback} months, prices {dir_past} by {abs(recent_change_pct):.1f}%. "
        f"Over the next {forecast_horizon} months, the model estimates {dir_future} path from {last_val:.1f} {unit} "
        f"to approximately {forecast_end_val:.1f} {unit} ({forecast_change_pct:+.1f}%)."
    )

    # 3. Honest uncertainty and error magnitude
    f_step_final = forecast.iloc[-1]
    low_80 = float(f_step_final["lower_80"])
    up_80 = float(f_step_final["upper_80"])

    insights.append(
        f"Calibrated uncertainty: At month {forecast_horizon}, the calibrated 80% range is {low_80:.1f} to {up_80:.1f} {unit}. "
        f"In historical backtests, this 80% interval contained the real price {picp_80:.0f}% of the time."
    )

    # 4. Seasonal pattern consistency
    obs_df = obs.copy()
    obs_df["dt"] = pd.to_datetime(obs_df["date"])
    obs_df["month"] = obs_df["dt"].dt.month
    obs_df["val"] = obs_df["value"].astype(float)
    obs_df["diff"] = obs_df["val"].diff()

    month_counts = obs_df.groupby("month")["diff"].agg(
        total="count",
        pos=lambda x: (x > 0).sum(),
        neg=lambda x: (x < 0).sum(),
    )
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    strong_season = []
    for m in range(1, 13):
        if m in month_counts.index:
            row = month_counts.loc[m]
            if row["total"] >= 5:
                pos_ratio = row["pos"] / row["total"]
                neg_ratio = row["neg"] / row["total"]
                if pos_ratio >= 0.70:
                    strong_season.append(f"{month_names[m-1]} (rose in {row['pos']}/{row['total']} observed years)")
                elif neg_ratio >= 0.70:
                    strong_season.append(f"{month_names[m-1]} (fell in {row['neg']}/{row['total']} observed years)")

    if strong_season:
        insights.append(
            f"Seasonal recurrence: Consistent historical patterns (>=70% sign agreement) observed in: "
            f"{', '.join(strong_season[:2])}."
        )
    else:
        insights.append(
            "Seasonal recurrence: No single calendar month exhibited a dominant directional movement "
            "(>=70% historical consistency) for this commodity."
        )

    return insights

