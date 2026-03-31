#!/usr/bin/env python3
"""
Standalone forecast generator — replaces the always-on FastAPI server.
Runs via GitHub Actions cron every 4 hours:
  1. Fetches all market data (yfinance, FRED, news, sentiment, etc.)
  2. Ranks all funds
  3. Logs predictions to MySQL (if configured)
  4. Runs self-improvement cycle (evaluate past predictions, adjust weights)
  5. Writes static JSON files to output_dir/
"""
import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import (
    fetch_price_history, fetch_price_history_extended, fetch_realtime_quote,
    fetch_macro_data, fetch_news, fetch_reddit_sentiment, fetch_fear_greed,
    fetch_google_trends, fetch_stocktwits, fetch_av_news_sentiment,
    fetch_cboe_put_call, fetch_treasury_yield_curve,
    prefetch_price_history_batch,
)
from technical import compute_technicals, compute_long_horizon_metrics, compute_investment_scenarios
from macro import score_macro_environment, FUND_NAMES, FUND_CURRENCY
from sentiment import analyze_sentiment
from scorer import rank_funds
from backtest import compute_backtest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TICKERS = [
    # US broad market & themes
    "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "ARKK", "GLD", "TLT",
    "EFA", "EEM", "VNQ", "XLF", "XLK", "XLE", "SCHD", "VIG", "BND", "IAU", "PDBC",
    # US sector ETFs
    "XLV", "XLU", "XLP", "XLY", "XLI",
    # Canadian funds
    "XIU.TO", "XIC.TO", "VCN.TO", "HXT.TO",
    "XEQT.TO", "XGRO.TO", "VGRO.TO", "VBAL.TO",
    "ZSP.TO", "XDV.TO", "ZLB.TO",
    "XEF.TO",
    "ZAG.TO", "XBB.TO",
    "ZEB.TO", "XFN.TO",
    "XRE.TO",
    "TEC.TO",
    "ZGD.TO",
    "ZQQ.TO", "VGG.TO", "XUS.TO", "ZUQ.TO",
]

OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "..", "output"))


def build_forecast() -> dict:
    """Build the full forecast — same logic as main.py build_forecast_sync()."""
    logger.info("Building forecast for all tickers...")

    source_status = {
        "yfinance": "ok", "alpha_vantage": "ok", "fred": "ok",
        "news_api": "ok", "reddit": "ok", "claude_api": "ok",
        "finbert": "ok", "fear_greed": "ok", "google_trends": "ok",
    }

    # Batch prefetch all price histories
    try:
        prefetch_price_history_batch(TICKERS, days=60)
    except Exception as e:
        logger.warning(f"Batch prefetch failed, will fall back to individual fetches: {e}")

    # Fetch shared data once
    macro_data = {}
    try:
        macro_data = fetch_macro_data()
        if not macro_data:
            source_status["fred"] = "error"
    except Exception as e:
        logger.error(f"Macro data fetch failed: {e}")
        source_status["fred"] = "error"

    fear_greed = {"score": 50.0, "rating": "neutral", "available": False}
    try:
        fear_greed = fetch_fear_greed()
        if not fear_greed.get("available"):
            source_status["fear_greed"] = "degraded"
    except Exception as e:
        logger.warning(f"Fear & Greed fetch failed: {e}")
        source_status["fear_greed"] = "error"

    cboe_pcr = {"available": False}
    try:
        cboe_pcr = fetch_cboe_put_call()
    except Exception as e:
        logger.warning(f"CBOE P/C fetch failed: {e}")

    treasury_curve = {"available": False}
    try:
        treasury_curve = fetch_treasury_yield_curve()
    except Exception as e:
        logger.warning(f"Treasury yield curve fetch failed: {e}")

    all_fund_data = []

    for ticker in TICKERS:
        fund_name = FUND_NAMES.get(ticker, ticker)
        logger.info(f"Processing {ticker}...")
        try:
            df = fetch_price_history(ticker, days=60)
            if df is None or len(df) == 0:
                source_status["yfinance"] = "degraded"
                logger.warning(f"No price data for {ticker}")
                continue

            quote = fetch_realtime_quote(ticker)
            technicals = compute_technicals(df, quote=quote)

            long_df = fetch_price_history_extended(ticker, years=5)
            long_metrics = compute_long_horizon_metrics(
                long_df, expense_ratio=quote.get("expense_ratio")
            )
            investment_scenarios = compute_investment_scenarios(
                long_df, current_price=quote.get("current_price"),
                expense_ratio=quote.get("expense_ratio")
            )
            macro = score_macro_environment(
                ticker, macro_data,
                fear_greed=fear_greed,
                cboe_pcr=cboe_pcr,
                treasury_curve=treasury_curve,
                quote=quote,
            )

            news = []
            try:
                news = fetch_news(ticker, fund_name)
            except Exception as e:
                logger.warning(f"News fetch failed for {ticker}: {e}")
                source_status["news_api"] = "degraded"

            reddit_posts = []

            google_trends = {"score": 50, "trend_direction": 0, "available": False}
            try:
                google_trends = fetch_google_trends(ticker)
                if not google_trends.get("available"):
                    source_status["google_trends"] = "degraded"
            except Exception as e:
                logger.debug(f"Google Trends failed for {ticker}: {e}")
                source_status["google_trends"] = "degraded"

            stocktwits = {}
            try:
                stocktwits = fetch_stocktwits(ticker)
            except Exception as e:
                logger.warning(f"StockTwits failed for {ticker}: {e}")

            av_news = {}
            try:
                av_news = fetch_av_news_sentiment(ticker)
            except Exception as e:
                logger.warning(f"AV News Sentiment failed for {ticker}: {e}")

            sentiment = analyze_sentiment(
                ticker, news, reddit_posts,
                google_trends=google_trends,
                stocktwits=stocktwits,
                av_news=av_news,
            )
            if "keyword_fallback" in sentiment.get("data_source", ""):
                source_status["claude_api"] = "degraded"

            backtest = compute_backtest(df)

            price_history = []
            close_col = df["Close"] if "Close" in df.columns else df.iloc[:, 3]
            close_series = close_col.squeeze()
            for date, price_val in close_series.tail(20).items():
                price_history.append({
                    "date": str(date)[:10],
                    "close": round(float(price_val), 2),
                })

            all_fund_data.append({
                "ticker": ticker,
                "fund_name": fund_name,
                "technical": technicals,
                "macro": macro,
                "sentiment": sentiment,
                "backtest": backtest,
                "current_price": quote.get("current_price"),
                "market_cap": quote.get("market_cap"),
                "volume": quote.get("volume"),
                "dividend_yield": quote.get("dividend_yield"),
                "beta": quote.get("beta"),
                "pe_ratio": quote.get("pe_ratio"),
                "expense_ratio": quote.get("expense_ratio"),
                "return_1d": round(technicals.get("momentum_1d", 0), 3),
                "return_5d": round(technicals.get("momentum_5d", 0), 3),
                "return_1m": round(technicals.get("momentum_1m", 0), 3),
                "long_metrics": long_metrics,
                "investment_scenarios": investment_scenarios,
                "google_trends_score": google_trends.get("score") if google_trends.get("available") else None,
                "google_trends_direction": google_trends.get("trend_direction"),
                "price_history": price_history,
                "currency": FUND_CURRENCY.get(ticker, "USD"),
                "ai_rationale": None,
                "key_signals": [],
                "rank": 0,
                "composite_score": 0,
                "confidence_level": "low",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            })

        except Exception as e:
            logger.error(f"Failed to process {ticker}: {e}", exc_info=True)

    ranked = rank_funds(all_fund_data)
    now = datetime.now(timezone.utc)

    result = {
        "funds": ranked,
        "last_updated": now.isoformat(),
        "data_source_status": source_status,
        "total_funds": len(ranked),
        "fear_greed": fear_greed,
    }

    logger.info(f"Forecast complete: {len(ranked)} funds ranked.")
    return result


def run_self_improvement():
    """Evaluate past predictions and adjust weights."""
    try:
        from self_improver import run_self_improvement as _run
        _run()
        logger.info("Self-improvement cycle complete.")
    except Exception as e:
        logger.error(f"Self-improvement error: {e}", exc_info=True)


def generate_supplementary_json() -> dict:
    """Generate track-record, model-insights, and predictions-status JSON."""
    from prediction_store import get_track_record_stats, get_predictions_status, get_weight_history
    from self_improver import load_weights

    track_record = {}
    try:
        track_record = get_track_record_stats()
    except Exception as e:
        logger.warning(f"track_record generation failed: {e}")
        track_record = {"available": False, "error": str(e)}

    predictions_status = {}
    try:
        predictions_status = get_predictions_status()
    except Exception as e:
        logger.warning(f"predictions_status generation failed: {e}")
        predictions_status = {"total_logged": 0, "days_until_first_eval": None, "top_picks_in_flight": []}

    model_insights = {}
    try:
        model_insights = {
            "current_weights": load_weights(),
            "weight_history": get_weight_history(limit=20),
        }
    except Exception as e:
        logger.warning(f"model_insights generation failed: {e}")
        model_insights = {"current_weights": None, "weight_history": []}

    return {
        "track_record": track_record,
        "predictions_status": predictions_status,
        "model_insights": model_insights,
    }


def write_json(data: dict, filename: str, output_dir: str):
    """Write a dict to a JSON file."""
    path = os.path.join(output_dir, filename)
    with open(path, "w") as f:
        json.dump(data, f, default=str, separators=(",", ":"))
    size_kb = os.path.getsize(path) / 1024
    logger.info(f"Wrote {filename} ({size_kb:.1f} KB)")


def main():
    output_dir = OUTPUT_DIR
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_dir}")

    # 1. Build forecast
    forecast = build_forecast()
    fund_count = len(forecast.get("funds", []))

    if fund_count == 0:
        logger.error("No funds in forecast — aborting to preserve existing data.")
        sys.exit(1)

    # 2. Log predictions to DB (once per day)
    try:
        from prediction_store import log_predictions
        log_predictions(forecast["funds"])
    except Exception as e:
        logger.warning(f"log_predictions failed: {e}")

    # 3. Run self-improvement (evaluate outcomes, adjust weights)
    run_self_improvement()

    # 4. Write all static JSON files
    write_json(forecast, "snapshot.json", output_dir)

    supplementary = generate_supplementary_json()
    write_json(supplementary["track_record"], "track-record.json", output_dir)
    write_json(supplementary["predictions_status"], "predictions-status.json", output_dir)
    write_json(supplementary["model_insights"], "model-insights.json", output_dir)

    meta = {
        "last_updated": forecast["last_updated"],
        "data_source_status": forecast["data_source_status"],
        "tracked_tickers": TICKERS,
        "fund_count": fund_count,
    }
    write_json(meta, "meta.json", output_dir)

    logger.info(f"All static files written. {fund_count} funds.")


if __name__ == "__main__":
    main()
