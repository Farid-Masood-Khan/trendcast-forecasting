"""TrendCast: Pakistan Food Commodities Time-Series Forecasting Dashboard.

Follows UI_UX_BRIEF.md & BACKEND_SCHEMA.md:
- Strictly calls typed service layer functions from src/
- Uses Plotly for uncertainty-first interactive charts
- Cached computations via @st.cache_data
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.backtest import run_backtest, score_models
from src.exceptions import InsufficientHistory
from src.forecast import calibrate_intervals, run_forecast
from src.insights import build_insights
from src.series_store import get_observations, get_series, list_series

st.set_page_config(
    page_title="TrendCast — Pakistan Food Commodities Forecasting",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Cached service layer calls
@st.cache_data
def cached_list_series() -> pd.DataFrame:
    return list_series()


@st.cache_data
def cached_get_series(series_id: str) -> dict[str, Any]:
    return get_series(series_id)


@st.cache_data
def cached_get_observations(series_id: str) -> pd.DataFrame:
    return get_observations(series_id)


@st.cache_data
def cached_run_backtest(series_id: str, max_horizon: int = 12) -> pd.DataFrame:
    return run_backtest(series_id, max_horizon=max_horizon)


@st.cache_data
def cached_run_forecast(series_id: str, model_name: str, horizon: int, backtest_df: pd.DataFrame) -> pd.DataFrame:
    calib = calibrate_intervals(backtest_df)
    return run_forecast(series_id, model_name=model_name, horizon=horizon, calibration_map=calib)


# Custom CSS for clean, professional typography and cards
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .badge-pass {
        background-color: #dcfce7;
        color: #166534;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85em;
    }
    .badge-warn {
        background-color: #fef3c7;
        color: #92400e;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85em;
    }
    .insight-box {
        background: #f0fdf4;
        border-left: 4px solid #22c55e;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def main() -> None:
    st.sidebar.title("📈 TrendCast")
    st.sidebar.caption("Pakistan Food Commodities Forecasting with Calibrated Uncertainty")

    nav_page = st.sidebar.radio(
        "Navigation",
        ["Forecast & Overview", "Backtest Explorer", "Data & Methodology"],
    )

    series_df = cached_list_series()
    series_options = {
        row["series_id"]: f"{row['display_name']} ({row['n_obs']} obs)"
        for _, row in series_df.iterrows()
    }

    selected_series_id = st.sidebar.selectbox(
        "Select Time Series",
        options=list(series_options.keys()),
        format_func=lambda x: series_options[x],
        index=0,
    )

    series_meta = cached_get_series(selected_series_id)
    n_obs = int(series_meta["n_obs"])

    # FR-8 Reliability Gate Check
    if n_obs < 24:
        render_insufficient_history(selected_series_id, series_meta)
        return

    # Normal Flow
    if nav_page == "Forecast & Overview":
        render_forecast_page(selected_series_id, series_meta)
    elif nav_page == "Backtest Explorer":
        render_backtest_page(selected_series_id, series_meta)
    elif nav_page == "Data & Methodology":
        render_methodology_page(series_df)


def render_insufficient_history(series_id: str, meta: dict[str, Any]) -> None:
    """Render the FR-8 guard state when a series has too few observations."""
    st.error("⚠️ Insufficient History for Reliable Forecasting (FR-8 Guard Active)")
    st.markdown(
        f"""
        **Series:** `{meta['display_name']}`
        **Observations available:** `{meta['n_obs']}` monthly periods (Threshold: ≥ 24 required).

        TrendCast enforces a hard statistical quality gate: series with fewer than 24 monthly observations
        cannot support honest rolling-origin cross-validation or calibrated residual intervals.
        Rather than drawing an uncalibrated forecast line, forecasting is strictly disabled for this series.
        """
    )

    obs = cached_get_observations(series_id)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=obs["date"],
        y=obs["value"],
        mode="lines+markers",
        line=dict(color="#64748b", width=2),
        name="Observed History",
    ))
    fig.update_layout(
        title=f"Historical Observations — {meta['display_name']}",
        xaxis_title="Date",
        yaxis_title=f"Price ({meta['unit']})",
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.info("💡 **Recommended alternative:** Switch to `wfp_wheat_flour_lahore_retail` or `wfp_rice_basmati_lahore_retail` in the sidebar to view full multi-origin backtests and calibrated forecasts.")


def render_forecast_page(series_id: str, meta: dict[str, Any]) -> None:
    # 1. Series Header Strip
    st.subheader(f"{meta['display_name']}")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.caption("Market")
        st.write(f"**{meta['market']}**")
    with col2:
        st.caption("Source")
        st.markdown(f"**[{meta['source']}]({meta['source_url']})**")
    with col3:
        st.caption("Frequency")
        st.write(f"**{meta['frequency'].title()}**")
    with col4:
        st.caption("Data as of")
        st.write(f"**{meta['last_obs']}**")
    with col5:
        st.caption("History Span")
        st.write(f"**{meta['n_obs']} months**")

    # Run backtest for this series
    with st.spinner("Computing rolling-origin backtest across models..."):
        try:
            bt_df = cached_run_backtest(series_id, max_horizon=12)
            scores_df = score_models(bt_df)
        except InsufficientHistory:
            st.error("Insufficient history to construct rolling backtest origins.")
            return

    # Best model recommendation
    best_model_name = str(scores_df.iloc[0]["model"])

    # Sidebar controls for forecasting
    st.sidebar.markdown("---")
    st.sidebar.subheader("Forecast Controls")

    horizon = st.sidebar.select_slider(
        "Forecast Horizon (months)",
        options=[4, 6, 8, 12],
        value=8,
    )

    model_options = ["Best by backtest (recommended)"] + list(scores_df["model"].unique())
    selected_option = st.sidebar.selectbox("Forecasting Model", model_options, index=0)

    chosen_model = best_model_name if selected_option == "Best by backtest (recommended)" else selected_option

    # Generate forecast
    fc_df = cached_run_forecast(series_id, chosen_model, horizon, bt_df)

    # 2. Insights Panel
    st.markdown("#### 💡 Empirical Insights")
    insights = build_insights(series_id, scores_df, fc_df, selected_model=chosen_model)
    st.markdown('<div class="insight-box">', unsafe_allow_html=True)
    for ins in insights:
        st.markdown(f"- {ins}")
    st.markdown("</div>", unsafe_allow_html=True)

    # 3. Model Accuracy Strip
    m_row = scores_df[scores_df["model"] == chosen_model].iloc[0]
    st.markdown(
        f"""
        > **Model Accuracy Audit (`{chosen_model}`):** Over held-out backtest origins, this method's estimates
        > were off by **±{m_row['mape']:.1f}% on average** (MAE: {m_row['mae']:.2f} {meta['unit']}, MASE: {m_row['mase']:.2f}).
        > Its calibrated 80% interval contained the true price **{m_row['picp_80']:.0f}% of the time**.
        """
    )

    if not m_row["beats_baseline"]:
        st.warning(f"⚠️ **Caution:** Selected model `{chosen_model}` had higher backtest error than the seasonal-naive baseline on this series.")

    # 4. Interactive Forecast Chart with Calibrated Bands
    obs = cached_get_observations(series_id)

    # History range filter
    hist_years = st.sidebar.select_slider(
        "Display History Window",
        options=[1, 2, 3, 5, 10, "All"],
        value=5,
    )
    if hist_years != "All":
        cutoff_dt = pd.to_datetime(obs["date"].iloc[-1]) - pd.DateOffset(years=int(hist_years))
        plot_obs = obs[pd.to_datetime(obs["date"]) >= cutoff_dt].copy()
    else:
        plot_obs = obs.copy()

    fig = go.Figure()

    # Outliers vs Normal
    plot_obs[plot_obs["quality"] == "observed"]
    outlier_pts = plot_obs[plot_obs["quality"] == "outlier_flag"]

    # History Line
    fig.add_trace(go.Scatter(
        x=plot_obs["date"],
        y=plot_obs["value"],
        mode="lines",
        line=dict(color="#1e293b", width=2.5),
        name="Historical Price",
        hovertemplate="%{x|%b %Y}: <b>%{y:.1f}</b> " + meta["unit"] + "<extra></extra>",
    ))

    # Flagged outliers
    if not outlier_pts.empty:
        fig.add_trace(go.Scatter(
            x=outlier_pts["date"],
            y=outlier_pts["value"],
            mode="markers",
            marker=dict(color="#ef4444", size=8, symbol="diamond"),
            name="Flagged Outlier (Kept)",
            hovertemplate="Flagged Outlier: %{x|%b %Y}: %{y:.1f} " + meta["unit"] + "<extra></extra>",
        ))

    # Forecast 95% Band (Lighter)
    fig.add_trace(go.Scatter(
        x=fc_df["target_date"].tolist() + fc_df["target_date"].tolist()[::-1],
        y=fc_df["upper_95"].tolist() + fc_df["lower_95"].tolist()[::-1],
        fill="toself",
        fillcolor="rgba(37, 99, 235, 0.12)",
        line=dict(color="rgba(255,255,255,0)"),
        hoverinfo="skip",
        name="95% Calibrated Interval",
    ))

    # Forecast 80% Band (Darker)
    fig.add_trace(go.Scatter(
        x=fc_df["target_date"].tolist() + fc_df["target_date"].tolist()[::-1],
        y=fc_df["upper_80"].tolist() + fc_df["lower_80"].tolist()[::-1],
        fill="toself",
        fillcolor="rgba(37, 99, 235, 0.25)",
        line=dict(color="rgba(255,255,255,0)"),
        hoverinfo="skip",
        name="80% Calibrated Interval",
    ))

    # Point Forecast Line (Dashed)
    # Connect last observation point to first forecast point
    last_hist_date = plot_obs["date"].iloc[-1]
    last_hist_val = plot_obs["value"].iloc[-1]

    fc_x = [last_hist_date] + fc_df["target_date"].tolist()
    fc_y = [last_hist_val] + fc_df["point"].tolist()

    fig.add_trace(go.Scatter(
        x=fc_x,
        y=fc_y,
        mode="lines+markers",
        line=dict(color="#2563eb", width=2.5, dash="dash"),
        name=f"Point Forecast ({chosen_model})",
        hovertemplate="%{x|%b %Y}: <b>%{y:.1f}</b> " + meta["unit"] + "<extra></extra>",
    ))

    # Shading 2022 super floods shock if visible in window
    flood_start = "2022-07-01"
    flood_end = "2022-11-01"
    if (plot_obs["date"] <= flood_start).any() and (plot_obs["date"] >= flood_end).any():
        fig.add_vrect(
            x0=flood_start,
            x1=flood_end,
            fillcolor="#fee2e2",
            opacity=0.4,
            layer="below",
            line_width=0,
            annotation_text="2022 Super Floods",
            annotation_position="top left",
        )

    # Vertical line at forecast origin
    fig.add_vline(
        x=last_hist_date,
        line_width=1.5,
        line_dash="dot",
        line_color="#64748b",
        annotation_text="Forecast Origin",
        annotation_position="bottom right",
    )

    fig.update_layout(
        title=f"Price Trajectory & {horizon}-Month Calibrated Outlook — {meta['display_name']}",
        xaxis_title="Date",
        yaxis_title=f"Price ({meta['unit']})",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40),
    )

    st.plotly_chart(fig, use_container_width=True)

    # 5. Model Comparison Table (FR-4 & FR-6)
    st.markdown("#### 📊 Model Comparison & Benchmark Gate")
    st.caption("Ranked by rolling-origin backtest Mean Absolute Percentage Error (MAPE). Baseline models are mandatory benchmarks.")

    display_table = scores_df.copy()
    display_table["beats_baseline"] = display_table["beats_baseline"].apply(
        lambda x: "✅ Beats Baseline" if x else "⚠️ Worse than Baseline"
    )
    st.dataframe(
        display_table.rename(
            columns={
                "model": "Model",
                "mae": f"MAE ({meta['unit']})",
                "rmse": f"RMSE ({meta['unit']})",
                "mape": "MAPE (%)",
                "mase": "MASE (vs S-Naive)",
                "picp_80": "80% Hit Rate",
                "picp_95": "95% Hit Rate",
                "n_origins": "Test Origins",
                "beats_baseline": "Benchmark Gate",
            }
        ),
        use_container_width=True,
    )

    # 6. CSV Export Buttons
    st.markdown("---")
    st.markdown("#### 📥 Data & Forecast Export (FR-9)")
    exp_col1, exp_col2 = st.columns(2)

    with exp_col1:
        fc_csv = io.StringIO()
        fc_csv.write(f"# TrendCast Forecast Export: {meta['display_name']}\n")
        fc_csv.write(f"# Source: {meta['source']} ({meta['source_url']})\n")
        fc_csv.write(f"# Model: {chosen_model} | Exported: {datetime.now().isoformat()}\n")
        fc_df.to_csv(fc_csv, index=False)
        st.download_button(
            label="Download Forecast Path (CSV)",
            data=fc_csv.getvalue(),
            file_name=f"{series_id}_{chosen_model}_forecast.csv",
            mime="text/csv",
        )

    with exp_col2:
        bt_csv = io.StringIO()
        bt_csv.write(f"# TrendCast Backtest Evaluation Table: {meta['display_name']}\n")
        bt_csv.write(f"# Source: {meta['source']} | Run Date: {datetime.now().isoformat()}\n")
        bt_df.to_csv(bt_csv, index=False)
        st.download_button(
            label="Download Backtest Results (CSV)",
            data=bt_csv.getvalue(),
            file_name=f"{series_id}_backtest_results.csv",
            mime="text/csv",
        )


def render_backtest_page(series_id: str, meta: dict[str, Any]) -> None:
    st.subheader(f"Backtest Explorer — {meta['display_name']}")
    st.markdown(
        "Inspect how each forecasting model behaves across distinct forecast horizons "
        "and rolling test origins. True statistical errors naturally expand as the prediction horizon widens."
    )

    with st.spinner("Loading backtest results..."):
        bt_df = cached_run_backtest(series_id, max_horizon=12)

    # Per-step error plot
    step_err = bt_df.groupby(["model", "step"])["pct_error"].mean().reset_index()
    step_err["mape"] = step_err["pct_error"] * 100.0

    fig = go.Figure()
    for m in step_err["model"].unique():
        sub = step_err[step_err["model"] == m]
        fig.add_trace(go.Scatter(
            x=sub["step"],
            y=sub["mape"],
            mode="lines+markers",
            name=m,
        ))

    fig.update_layout(
        title="Error Expansion Curve: MAPE vs. Horizon Step",
        xaxis_title="Forecast Horizon Step (Months Ahead)",
        yaxis_title="Mean Absolute Percentage Error (%)",
        template="plotly_white",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Origin by origin table
    with st.expander("🔍 View Origin-by-Origin Evaluation Folds"):
        st.dataframe(bt_df, use_container_width=True)


def render_methodology_page(series_df: pd.DataFrame) -> None:
    st.subheader("Data Catalogue & Methodology Documentation")

    st.markdown("### 1. Active Series Catalogue")
    st.dataframe(
        series_df[[
            "series_id", "display_name", "market", "commodity", "unit", "n_obs", "first_obs", "last_obs",
        ]],
        use_container_width=True,
    )

    st.markdown(
        """
        ### 2. Rolling-Origin Backtesting Architecture
        - **Evaluation Zone**: The most recent 24 monthly periods of each series form the evaluation window.
        - **Expanding Window**: At each origin date, models are fitted strictly on historical observations prior to the origin. No lookahead leakage occurs.
        - **Zero Lookahead Rule**: Automated unit tests verify that altering timestamps at or after an origin does not alter the training data or forecasts of that origin.

        ### 3. Residual Uncertainty Calibration
        - Standard model variance (e.g. Prophet or ARIMA parametric intervals) is notoriously overconfident on commodity series subject to macroeconomic shocks.
        - **Calibration Strategy**: TrendCast records historical $|\\ln(y / \\hat{y})|$ prediction errors for each step $h$. The empirical 80th and 95th quantiles define the interval half-widths.
        - **Non-Negativity**: Applying quantiles symmetrically in log-space guarantees price boundaries strictly remain positive ($> 0$).

        ### 4. Known Engineering Limitations
        - **Shock Blindness**: Pure time-series extrapolation cannot anticipate exogenous events such as catastrophic floods, border closures, or emergency government subsidies.
        - **Sparse History**: Series with $< 24$ clean monthly periods are barred from forward forecasting by the FR-8 guard.
        - **Baseline Dominance**: On several staple commodities, simple naive or seasonal-naive models remain competitive with complex autoregressive models, which TrendCast transparently highlights rather than hides.
        """
    )


if __name__ == "__main__":
    main()
