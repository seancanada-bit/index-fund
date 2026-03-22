import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if not np.isnan(val) else 50.0


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _macd(series: pd.Series):
    ema12 = _ema(series, 12)
    ema26 = _ema(series, 26)
    macd_line = ema12 - ema26
    signal_line = _ema(macd_line, 9)
    histogram = macd_line - signal_line
    return (
        float(macd_line.iloc[-1]),
        float(signal_line.iloc[-1]),
        float(histogram.iloc[-1]),
        histogram,
    )


def _bollinger(series: pd.Series, period: int = 20, std_dev: int = 2):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    price = series.iloc[-1]
    upper_val = upper.iloc[-1]
    lower_val = lower.iloc[-1]
    if upper_val == lower_val:
        return 0.5
    percent_b = (price - lower_val) / (upper_val - lower_val)
    return float(np.clip(percent_b, -0.5, 1.5))


def _sma(series: pd.Series, period: int) -> float:
    if len(series) < period:
        return float(series.mean())
    return float(series.rolling(period).mean().iloc[-1])


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    price = close.iloc[-1]
    return float(atr / price * 100) if price > 0 else 0.0


def _stochastic(df: pd.DataFrame, period: int = 14):
    low_min = df["Low"].rolling(period).min()
    high_max = df["High"].rolling(period).max()
    denom = high_max - low_min
    k = 100 * (df["Close"] - low_min) / denom.replace(0, np.nan)
    d = k.rolling(3).mean()
    return (float(k.iloc[-1]) if not np.isnan(k.iloc[-1]) else 50.0,
            float(d.iloc[-1]) if not np.isnan(d.iloc[-1]) else 50.0)


def _week52_position(price: float, high_52: float | None, low_52: float | None) -> float | None:
    """Position within 52-week range: 0 = at low, 1 = at high."""
    if high_52 is None or low_52 is None or high_52 == low_52:
        return None
    pos = (price - low_52) / (high_52 - low_52)
    return round(float(np.clip(pos, 0, 1)), 3)


def compute_technicals(df: pd.DataFrame, quote: dict = None) -> dict:
    if df is None or len(df) < 30:
        return _empty_technicals()

    df = df.copy()
    df.columns = [c.capitalize() if c.lower() in ("open", "high", "low", "close", "volume") else c
                  for c in df.columns]
    if "Adj close" in df.columns:
        df["Close"] = df["Adj close"]

    close = df["Close"].squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    rsi = _rsi(close)
    macd_val, signal_val, hist_val, hist_series = _macd(close)
    bb_pct = _bollinger(close)
    sma50 = _sma(close, 50)
    sma200 = _sma(close, 200)
    price = float(close.iloc[-1])

    price_above_sma50 = price > sma50
    price_above_sma200 = price > sma200

    # Golden/death cross
    golden_cross = False
    death_cross = False
    if len(close) >= 210:
        sma50_series = close.rolling(50).mean()
        sma200_series = close.rolling(200).mean()
        recent_50 = sma50_series.iloc[-10:]
        recent_200 = sma200_series.iloc[-10:]
        diff = recent_50 - recent_200
        if len(diff) >= 2:
            sign_changes = (diff.iloc[:-1].values * diff.iloc[1:].values) < 0
            for i, changed in enumerate(sign_changes):
                if changed:
                    if diff.iloc[i + 1] > 0:
                        golden_cross = True
                    else:
                        death_cross = True

    # Volume ratio
    volume_ratio = 1.0
    if "Volume" in df.columns:
        vol = df["Volume"].squeeze()
        if isinstance(vol, pd.DataFrame):
            vol = vol.iloc[:, 0]
        if len(vol) >= 30:
            avg5 = float(vol.iloc[-5:].mean())
            avg30 = float(vol.iloc[-30:].mean())
            volume_ratio = avg5 / avg30 if avg30 > 0 else 1.0

    def pct_change(days):
        if len(close) > days:
            old = float(close.iloc[-(days + 1)])
            curr = float(close.iloc[-1])
            return (curr - old) / old * 100 if old > 0 else 0.0
        return 0.0

    mom1 = pct_change(1)
    mom5 = pct_change(5)
    mom20 = pct_change(20)
    mom1m = pct_change(21)   # ~1 calendar month

    atr_pct = _atr(df)
    stoch_k, stoch_d = _stochastic(df)

    # 52-week position from quote
    week_52_high = quote.get("week_52_high") if quote else None
    week_52_low = quote.get("week_52_low") if quote else None
    week_52_position = _week52_position(price, week_52_high, week_52_low)

    # Histogram trend
    hist_increasing = False
    if len(hist_series) >= 3:
        recent_hist = hist_series.dropna().iloc[-3:]
        if len(recent_hist) >= 2:
            hist_increasing = float(recent_hist.iloc[-1]) > float(recent_hist.iloc[-2])

    # --- Technical score ---
    # RSI base
    if rsi < 40:
        score = 70.0
    elif rsi > 70:
        score = 30.0
    else:
        score = 50.0

    if macd_val > 0 and hist_increasing:
        score += 15
    if price_above_sma50:
        score += 10
    if price_above_sma200:
        score += 10
    if golden_cross:
        score += 15
    if death_cross:
        score -= 15
    if volume_ratio > 1.2:
        score += 10
    if mom5 > 0:
        score += 10
    if 0.2 <= bb_pct <= 0.8:
        score += 5

    # 52-week position bonus: near 52-wk high with momentum = strength
    if week_52_position is not None:
        if week_52_position > 0.85 and mom20 > 0:
            score += 8   # Near 52-wk high with uptrend
        elif week_52_position < 0.15:
            score += 5   # Near 52-wk low = potential reversal / oversold

    technical_score = float(np.clip(score, 0, 100))

    return {
        "rsi": round(rsi, 2),
        "macd": round(macd_val, 4),
        "macd_signal": round(signal_val, 4),
        "macd_histogram": round(hist_val, 4),
        "bb_percent_b": round(bb_pct, 4),
        "sma_50": round(sma50, 2),
        "sma_200": round(sma200, 2),
        "price_above_sma50": price_above_sma50,
        "price_above_sma200": price_above_sma200,
        "golden_cross": golden_cross,
        "death_cross": death_cross,
        "volume_ratio": round(volume_ratio, 3),
        "momentum_1d": round(mom1, 3),
        "momentum_5d": round(mom5, 3),
        "momentum_20d": round(mom20, 3),
        "momentum_1m": round(mom1m, 3),
        "atr_pct": round(atr_pct, 3),
        "stoch_k": round(stoch_k, 2),
        "stoch_d": round(stoch_d, 2),
        "week_52_high": round(week_52_high, 2) if week_52_high else None,
        "week_52_low": round(week_52_low, 2) if week_52_low else None,
        "week_52_position": week_52_position,
        "technical_score": round(technical_score, 2),
    }


def _empty_technicals() -> dict:
    return {
        "rsi": 50.0, "macd": 0.0, "macd_signal": 0.0, "macd_histogram": 0.0,
        "bb_percent_b": 0.5, "sma_50": 0.0, "sma_200": 0.0,
        "price_above_sma50": False, "price_above_sma200": False,
        "golden_cross": False, "death_cross": False,
        "volume_ratio": 1.0, "momentum_1d": 0.0, "momentum_5d": 0.0, "momentum_20d": 0.0,
        "atr_pct": 0.0, "stoch_k": 50.0, "stoch_d": 50.0,
        "week_52_high": None, "week_52_low": None, "week_52_position": None,
        "momentum_1m": 0.0,
        "technical_score": 50.0,
    }


def compute_investment_scenarios(df_long, current_price, expense_ratio=None) -> dict | None:
    """Historical growth and projected range for an investment in this fund."""
    if df_long is None or len(df_long) < 20:
        return None
    try:
        df_long = df_long.copy()
        df_long.columns = [c.capitalize() if c.lower() in ("open","high","low","close","volume") else c
                           for c in df_long.columns]
        close_col = df_long["Close"] if "Close" in df_long.columns else df_long.iloc[:, 3]
        close = close_col.squeeze().dropna().astype(float)

        if current_price is None or current_price <= 0:
            current_price = float(close.iloc[-1])

        # Historical: how much would $1 invested N days ago be worth today?
        historical = {}
        for label, days in {"1m": 21, "3m": 63, "6m": 126, "1y": 252, "3y": 756, "5y": 1260}.items():
            if len(close) >= days:
                past = float(close.iloc[-days])
                if past > 0:
                    historical[label] = round(((current_price / past) - 1) * 100, 2)

        # Volatility
        returns = close.pct_change().dropna()
        ann_vol = float(returns.tail(252).std() * 252 ** 0.5) if len(returns) >= 252 else float(returns.std() * 252 ** 0.5)

        # CAGR — prefer longer window
        def _cagr(days, years):
            if len(close) >= days:
                p = float(close.iloc[-days])
                if p > 0:
                    return (current_price / p) ** (1 / years) - 1
            return None

        base_rate = _cagr(1260, 5) or _cagr(756, 3) or _cagr(252, 1) or 0.07
        net_rate = base_rate - (expense_ratio or 0.001)

        # Forward projections: multipliers on $1
        projections = {}
        for label, years in {"6m": 0.5, "1y": 1, "3y": 3, "5y": 5, "10y": 10}.items():
            base = (1 + net_rate) ** years
            bull = (1 + net_rate + ann_vol) ** years
            bear = max((1 + net_rate - ann_vol) ** years, 0.01)
            projections[label] = {
                "base": round(base, 4),
                "bull": round(bull, 4),
                "bear": round(bear, 4),
            }

        return {
            "historical": historical,
            "projections": projections,
            "base_annual_rate": round(net_rate * 100, 2),
            "annual_volatility": round(ann_vol * 100, 2),
        }
    except Exception as e:
        logger.warning(f"Investment scenarios failed: {e}")
        return None


def compute_long_horizon_metrics(df: pd.DataFrame, expense_ratio: float = None) -> dict:
    """Compute CAGR, Sharpe, max drawdown from multi-year daily price history.

    Returns a flat dict compatible with LongHorizonMetrics model.
    Uses risk-free rate of 4.5% annualised for Sharpe calculation.
    """
    if df is None or len(df) < 50:
        return {}

    try:
        df = df.copy()
        df.columns = [c.capitalize() if c.lower() in ("open", "high", "low", "close", "volume") else c
                      for c in df.columns]
        close_col = df["Close"] if "Close" in df.columns else df.iloc[:, 3]
        close = close_col.squeeze().dropna().astype(float)

        if len(close) < 50:
            return {}

        daily_returns = close.pct_change().dropna()

        def _cagr(n_years: float):
            n_days = int(n_years * 252)
            if len(close) < n_days + 1:
                return None
            start = float(close.iloc[-(n_days + 1)])
            end = float(close.iloc[-1])
            if start <= 0:
                return None
            return round(((end / start) ** (1 / n_years) - 1) * 100, 2)

        def _sharpe(n_years: float, risk_free_annual: float = 0.045):
            n_days = int(n_years * 252)
            if len(daily_returns) < n_days:
                return None
            rets = daily_returns.iloc[-n_days:]
            rf_daily = risk_free_annual / 252
            excess = rets - rf_daily
            std = float(excess.std())
            if std == 0:
                return None
            return round(float((excess.mean() / std) * (252 ** 0.5)), 3)

        def _max_drawdown(n_years: float):
            n_days = int(n_years * 252)
            if len(close) < n_days:
                return None
            prices = close.iloc[-n_days:]
            rolling_max = prices.cummax()
            dd = (prices - rolling_max) / rolling_max
            return round(float(dd.min() * 100), 2)

        def _ann_vol(n_years: float):
            n_days = int(n_years * 252)
            if len(daily_returns) < n_days:
                return None
            return round(float(daily_returns.iloc[-n_days:].std() * (252 ** 0.5) * 100), 2)

        return {
            "cagr_1y": _cagr(1),
            "cagr_3y": _cagr(3),
            "cagr_5y": _cagr(5),
            "sharpe_1y": _sharpe(1),
            "sharpe_5y": _sharpe(5),
            "max_drawdown_1y": _max_drawdown(1),
            "max_drawdown_5y": _max_drawdown(5),
            "annualized_vol_1y": _ann_vol(1),
            "annualized_vol_5y": _ann_vol(5),
            "expense_ratio": expense_ratio,
        }
    except Exception as e:
        logger.warning(f"Long horizon metrics computation failed: {e}")
        return {}
