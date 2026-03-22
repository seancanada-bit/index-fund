"""
Simple rolling backtest: uses 60 days of price history to test how often
the momentum signal (price vs 10-day MA) correctly predicted the direction
of the following 5-trading-day return. Gives an honest accuracy score.
"""
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


def compute_backtest(df: pd.DataFrame, n_periods: int = 8) -> dict:
    if df is None or len(df) < 30:
        return {"accuracy": None, "windows_tested": 0, "results": [], "avg_correct_return": None}

    close = df["Close"].squeeze() if "Close" in df.columns else df.iloc[:, 3].squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = close.dropna()
    results = []
    hits = 0
    total = 0
    correct_returns = []
    wrong_returns = []

    # Roll through the last n_periods × 5-day windows
    for i in range(n_periods, 0, -1):
        window_end = len(close) - (i - 1) * 5
        window_start = window_end - 5

        if window_start < 15 or window_end >= len(close):
            continue

        # Signal at window_start: price vs 10-day moving average
        lookback = close.iloc[:window_start]
        if len(lookback) < 10:
            continue

        ma10 = float(lookback.rolling(10).mean().iloc[-1])
        price_at_signal = float(lookback.iloc[-1])
        signal_strength = (price_at_signal - ma10) / ma10  # % above/below MA

        # Actual 5-day return
        start_price = float(close.iloc[window_start])
        end_price = float(close.iloc[min(window_end, len(close) - 1)])
        actual_return = (end_price - start_price) / start_price * 100

        predicted_up = signal_strength > 0
        actually_up = actual_return > 0
        correct = predicted_up == actually_up

        if correct:
            hits += 1
            correct_returns.append(actual_return)
        else:
            wrong_returns.append(actual_return)
        total += 1

        results.append({
            "period_end": str(close.index[min(window_end, len(close) - 1)])[:10],
            "signal": "↑" if predicted_up else "↓",
            "actual_return_pct": round(actual_return, 2),
            "correct": correct,
        })

    accuracy = round(hits / total * 100, 1) if total > 0 else None
    avg_correct = round(float(np.mean(correct_returns)), 2) if correct_returns else None

    return {
        "accuracy": accuracy,
        "windows_tested": total,
        "results": results,
        "avg_correct_return": avg_correct,
    }
