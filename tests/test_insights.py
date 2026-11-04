"""Unit tests for rule-based insights generation."""

from __future__ import annotations

import pandas as pd

from src.insights import build_insights


def test_build_insights_structure_and_non_causality() -> None:
    # Synthetic scores where model beats baseline
    scores_winning = pd.DataFrame([
        {"series_id": "wfp_wheat_flour_lahore_retail", "model": "sarima", "mae": 5.0, "mape": 6.2, "mase": 0.5, "picp_80": 80.0, "picp_95": 95.0, "beats_baseline": True},
        {"series_id": "wfp_wheat_flour_lahore_retail", "model": "seasonal_naive", "mae": 10.0, "mape": 12.0, "mase": 1.0, "picp_80": 80.0, "picp_95": 95.0, "beats_baseline": True},
    ])
    forecast = pd.DataFrame([
        {"series_id": "wfp_wheat_flour_lahore_retail", "step": 1, "point": 100.0, "lower_80": 90.0, "upper_80": 110.0},
        {"series_id": "wfp_wheat_flour_lahore_retail", "step": 2, "point": 102.0, "lower_80": 91.0, "upper_80": 112.0},
    ])

    insights = build_insights("wfp_wheat_flour_lahore_retail", scores_winning, forecast)
    assert 3 <= len(insights) <= 5

    forbidden_phrases = ["because of", "caused by", "due to floods", "due to inflation", "will definitely"]
    for text in insights:
        for phrase in forbidden_phrases:
            assert phrase not in text.lower(), f"Forbidden causal phrase found: '{phrase}' in '{text}'"


def test_build_insights_baseline_warning_when_losing() -> None:
    # Model with higher error than seasonal-naive
    scores_losing = pd.DataFrame([
        {"series_id": "wfp_wheat_flour_lahore_retail", "model": "ets", "mae": 15.0, "mape": 18.0, "mase": 1.5, "picp_80": 70.0, "picp_95": 90.0, "beats_baseline": False},
        {"series_id": "wfp_wheat_flour_lahore_retail", "model": "seasonal_naive", "mae": 10.0, "mape": 12.0, "mase": 1.0, "picp_80": 80.0, "picp_95": 95.0, "beats_baseline": True},
    ])
    forecast = pd.DataFrame([
        {"series_id": "wfp_wheat_flour_lahore_retail", "step": 1, "point": 100.0, "lower_80": 90.0, "upper_80": 110.0},
    ])

    insights = build_insights("wfp_wheat_flour_lahore_retail", scores_losing, forecast, selected_model="ets")
    assert any("warning" in ins.lower() or "baseline" in ins.lower() for ins in insights)

