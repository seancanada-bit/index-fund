import os
import logging
import anthropic
from macro import FUND_NAMES

logger = logging.getLogger(__name__)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# Horizon scoring weights
# ---------------------------------------------------------------------------
# 7D weights are adaptive — loaded fresh each forecast run from self_improver
WEIGHTS_30D = {"technical": 0.30, "macro": 0.45, "sentiment": 0.25}
WEIGHTS_1Y  = {"fundamental": 0.40, "macro": 0.35, "technical": 0.25}
WEIGHTS_5Y  = {"fundamental": 0.55, "macro": 0.25, "technical": 0.20}

_DEFAULT_WEIGHTS_7D = {"technical": 0.55, "sentiment": 0.30, "macro": 0.15}


def _load_weights_7d() -> dict:
    """Load adaptive 7-day weights; fall back to defaults on any error."""
    try:
        from self_improver import load_weights
        w = load_weights()
        return {
            "technical": w.get("technical", _DEFAULT_WEIGHTS_7D["technical"]),
            "macro":     w.get("macro",     _DEFAULT_WEIGHTS_7D["macro"]),
            "sentiment": w.get("sentiment", _DEFAULT_WEIGHTS_7D["sentiment"]),
        }
    except Exception:
        return _DEFAULT_WEIGHTS_7D


def _confidence_level(tech: float, macro: float, sentiment: float) -> str:
    scores = [tech, macro, sentiment]
    spread = max(scores) - min(scores)
    if spread <= 15:
        return "high"
    pairs = [abs(tech - macro), abs(tech - sentiment), abs(macro - sentiment)]
    if any(p <= 20 for p in pairs):
        return "medium"
    return "low"


def _normalize_across_funds(values: list, higher_is_better: bool = True) -> list:
    """Convert raw metric values to 0-100 scores via percentile rank.
    Funds with None receive 50 (median fallback).
    """
    valid = [(i, v) for i, v in enumerate(values) if v is not None]
    n = len(values)
    if len(valid) < 2:
        return [50.0] * n
    n_valid = len(valid)
    sorted_valid = sorted(valid, key=lambda x: x[1], reverse=higher_is_better)
    rank_map = {idx: rank for rank, (idx, _) in enumerate(sorted_valid)}
    result = []
    for i, v in enumerate(values):
        if v is None:
            result.append(50.0)
        else:
            rank = rank_map[i]
            result.append(round((1 - rank / max(n_valid - 1, 1)) * 100, 2))
    return result


def _fundamental_scores_1y(long_metrics_list: list) -> list:
    """1Y fundamental: CAGR(40%) + Sharpe(30%) + MaxDD(20%) + Expense(10%)."""
    cagr   = _normalize_across_funds([m.get("cagr_1y")         for m in long_metrics_list])
    sharpe = _normalize_across_funds([m.get("sharpe_1y")       for m in long_metrics_list])
    mdd    = _normalize_across_funds([m.get("max_drawdown_1y") for m in long_metrics_list], higher_is_better=False)
    exp    = _normalize_across_funds([m.get("expense_ratio")   for m in long_metrics_list], higher_is_better=False)
    return [round(cagr[i]*0.40 + sharpe[i]*0.30 + mdd[i]*0.20 + exp[i]*0.10, 2) for i in range(len(long_metrics_list))]


def _fundamental_scores_5y(long_metrics_list: list, div_yields: list) -> list:
    """5Y fundamental: CAGR(35%) + Sharpe(25%) + MaxDD(20%) + Expense(15%) + Yield(5%)."""
    cagr   = _normalize_across_funds([m.get("cagr_5y")         for m in long_metrics_list])
    sharpe = _normalize_across_funds([m.get("sharpe_5y")       for m in long_metrics_list])
    mdd    = _normalize_across_funds([m.get("max_drawdown_5y") for m in long_metrics_list], higher_is_better=False)
    exp    = _normalize_across_funds([m.get("expense_ratio")   for m in long_metrics_list], higher_is_better=False)
    div    = _normalize_across_funds(div_yields)
    return [round(cagr[i]*0.35 + sharpe[i]*0.25 + mdd[i]*0.20 + exp[i]*0.15 + div[i]*0.05, 2) for i in range(len(long_metrics_list))]


def _build_key_signals(tech: dict, macro: dict, sentiment: dict) -> list:
    signals = []
    if tech.get("golden_cross"):
        signals.append({"label": "Golden cross detected", "direction": "bullish"})
    if tech.get("death_cross"):
        signals.append({"label": "Death cross detected", "direction": "bearish"})
    if tech.get("price_above_sma200"):
        signals.append({"label": "Price above 200-day SMA", "direction": "bullish"})
    else:
        signals.append({"label": "Price below 200-day SMA", "direction": "bearish"})
    rsi = tech.get("rsi", 50)
    if rsi < 35:
        signals.append({"label": f"RSI oversold ({rsi:.1f})", "direction": "bullish"})
    elif rsi > 70:
        signals.append({"label": f"RSI overbought ({rsi:.1f})", "direction": "bearish"})
    if tech.get("volume_ratio", 1.0) > 1.3:
        signals.append({"label": "Above-average volume surge", "direction": "bullish"})
    mom5 = tech.get("momentum_5d", 0)
    if mom5 > 2:
        signals.append({"label": f"5-day momentum +{mom5:.1f}%", "direction": "bullish"})
    elif mom5 < -2:
        signals.append({"label": f"5-day momentum {mom5:.1f}%", "direction": "bearish"})
    pos = tech.get("week_52_position")
    if pos is not None:
        if pos > 0.90:
            signals.append({"label": f"Near 52-week high ({pos*100:.0f}th %ile)", "direction": "bullish"})
        elif pos < 0.10:
            signals.append({"label": f"Near 52-week low ({pos*100:.0f}th %ile)", "direction": "neutral"})
    fg = macro.get("fear_greed_score")
    fg_rating = macro.get("fear_greed_rating")
    if fg is not None:
        direction = "bearish" if fg <= 30 else ("bullish" if fg >= 65 else "neutral")
        signals.append({"label": f"Fear & Greed: {fg:.0f} ({fg_rating})", "direction": direction})
    for sig in macro.get("triggered_signals", [])[:2]:
        signals.append({"label": sig["signal"], "direction": sig["direction"]})
    for theme in sentiment.get("key_themes", [])[:2]:
        signals.append({"label": theme, "direction": sentiment.get("sentiment", "neutral")})
    return signals[:9]


def _generate_rationale(ticker: str, fund_name: str, composite_score: float,
                         tech: dict, macro: dict, sentiment: dict) -> str:
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        fg_info = ""
        if macro.get("fear_greed_score") is not None:
            fg_info = f"Fear & Greed Index: {macro['fear_greed_score']:.0f} ({macro.get('fear_greed_rating', 'neutral')})"
        signal_summary = (
            f"Ticker: {ticker} ({fund_name})\n"
            f"7-Day Composite Score: {composite_score:.1f}/100\n"
            f"Technical Score: {tech.get('technical_score', 50):.1f} "
            f"(RSI: {tech.get('rsi', 50):.1f}, MACD: {'positive' if tech.get('macd', 0) > 0 else 'negative'}, "
            f"Above 200-SMA: {tech.get('price_above_sma200', False)}, "
            f"52-wk position: {tech.get('week_52_position', 'N/A')})\n"
            f"Macro Score: {macro.get('macro_score', 50):.1f} "
            f"(VIX: {macro.get('vix', 'N/A')}, Yield Curve: {macro.get('yield_curve', 'N/A')}, {fg_info})\n"
            f"Sentiment Score: {sentiment.get('final_sentiment_score', 50):.1f} "
            f"({sentiment.get('sentiment', 'neutral')}, source: {sentiment.get('data_source', 'keyword')})\n"
            f"Key Themes: {', '.join(sentiment.get('key_themes', [])) or 'None'}\n"
            f"Risk Flags: {', '.join(sentiment.get('risk_flags', [])) or 'None'}"
        )
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            messages=[{"role": "user", "content": f"Generate a 2-paragraph outlook for {ticker} ({fund_name}) based on:\n{signal_summary}"}],
            system=(
                "You are a financial analyst writing a brief weekly outlook. "
                "Write in plain English for a general audience. "
                "Do not make promises or guarantees. Always note this is not financial advice. "
                "Keep each paragraph to 2-3 sentences. Reference specific signals."
            ),
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.debug(f"Rationale generation skipped for {ticker}: {type(e).__name__}")
        sentiment_text = sentiment.get("rationale", "")
        return (
            f"{ticker} shows a 7-day composite score of {composite_score:.0f}/100 based on technical, "
            f"macro, and sentiment analysis. {sentiment_text} "
            f"This is for informational purposes only and not financial advice."
        )


def rank_funds(all_fund_data: list) -> list:
    if not all_fund_data:
        return []

    long_metrics_list = [f.get("long_metrics") or {} for f in all_fund_data]
    div_yields = [f.get("dividend_yield") or 0.0 for f in all_fund_data]

    fund_scores_1y = _fundamental_scores_1y(long_metrics_list)
    fund_scores_5y = _fundamental_scores_5y(long_metrics_list, div_yields)

    for i, fund in enumerate(all_fund_data):
        tech      = fund["technical"].get("technical_score", 50)
        macro_s   = fund["macro"].get("macro_score", 50)
        sentiment = fund["sentiment"].get("final_sentiment_score", 50)
        fund_1y   = fund_scores_1y[i]
        fund_5y   = fund_scores_5y[i]

        w = _load_weights_7d()
        fund["score_7d"]  = round(tech*w["technical"] + sentiment*w["sentiment"] + macro_s*w["macro"], 2)
        w = WEIGHTS_30D
        fund["score_30d"] = round(tech*w["technical"] + macro_s*w["macro"] + sentiment*w["sentiment"], 2)
        w = WEIGHTS_1Y
        fund["score_1y"]  = round(fund_1y*w["fundamental"] + macro_s*w["macro"] + tech*w["technical"], 2)
        w = WEIGHTS_5Y
        fund["score_5y"]  = round(fund_5y*w["fundamental"] + macro_s*w["macro"] + tech*w["technical"], 2)

        fund["fundamental_score_1y"] = fund_1y
        fund["fundamental_score_5y"] = fund_5y
        fund["composite_score"] = fund["score_7d"]
        fund["confidence_level"] = _confidence_level(tech, macro_s, sentiment)
        fund["key_signals"] = _build_key_signals(fund["technical"], fund["macro"], fund["sentiment"])

    for horizon, key in [("7d", "score_7d"), ("30d", "score_30d"), ("1y", "score_1y"), ("5y", "score_5y")]:
        h_sorted = sorted(all_fund_data, key=lambda x: x[key], reverse=True)
        for rank_i, f in enumerate(h_sorted):
            f[f"rank_{horizon}"] = rank_i + 1

    ranked = sorted(all_fund_data, key=lambda x: x["score_7d"], reverse=True)
    for i, fund in enumerate(ranked):
        fund["rank"] = i + 1

    for fund in ranked[:3]:
        fund["ai_rationale"] = _generate_rationale(
            ticker=fund["ticker"],
            fund_name=FUND_NAMES.get(fund["ticker"], fund["ticker"]),
            composite_score=fund["composite_score"],
            tech=fund["technical"],
            macro=fund["macro"],
            sentiment=fund["sentiment"],
        )

    return ranked
