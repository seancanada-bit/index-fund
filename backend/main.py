import os
import logging
import threading
import warnings
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager
import asyncio
import json

# Suppress asyncio DeprecationWarning on Python 3.14 (harmless, fixed in future FastAPI/APScheduler)
warnings.filterwarnings("ignore", message=".*iscoroutinefunction.*", category=DeprecationWarning)

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from models import (ForecastResponse, FundForecast, TechnicalSignals,
                    MacroSignals, SentimentResult, PricePoint, BacktestResult,
                    LongHorizonMetrics, InvestmentScenarios)
from data_fetcher import (
    fetch_price_history, fetch_price_history_extended, fetch_realtime_quote, fetch_macro_data,
    fetch_news, fetch_reddit_sentiment, fetch_fear_greed, fetch_google_trends,
    fetch_stocktwits, fetch_av_news_sentiment,
    prefetch_price_history_batch, invalidate_cache, _cache_get, _cache_set
)
from technical import compute_technicals, compute_long_horizon_metrics, compute_investment_scenarios
from macro import score_macro_environment, FUND_NAMES, FUND_CURRENCY
from sentiment import analyze_sentiment
from scorer import rank_funds
from backtest import compute_backtest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TICKERS = [
    # US funds
    "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "ARKK", "GLD", "TLT",
    "EFA", "EEM", "VNQ", "XLF", "XLK", "XLE", "SCHD", "VIG", "BND", "IAU", "PDBC",
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
]

# Use BackgroundScheduler (runs in a thread, not async) so it never blocks the event loop
scheduler = BackgroundScheduler()
_forecast_cache_key = "full_forecast"
_last_updated: Optional[datetime] = None
_data_source_status: dict = {}
_prev_ranks: dict = {}        # {ticker: rank} from last completed forecast cycle
_last_log_date: Optional[str] = None  # "YYYY-MM-DD" — log predictions once per day only
_build_lock = threading.Lock()        # Prevents concurrent forecast builds


def build_forecast_sync() -> dict:
    """Synchronous forecast build — runs in a background thread via APScheduler.
    Uses a lock to prevent concurrent builds from wasting resources."""
    global _last_updated, _data_source_status, _prev_ranks, _last_log_date

    if not _build_lock.acquire(blocking=False):
        logger.info("Forecast build already in progress — returning cached result.")
        cached = _cache_get(_forecast_cache_key)
        if cached:
            return json.loads(cached)
        # Wait for the running build to finish then return its result
        with _build_lock:
            cached = _cache_get(_forecast_cache_key)
            return json.loads(cached) if cached else {}

    try:
        logger.info("Building forecast for all tickers...")

        source_status = {
            "yfinance": "ok", "alpha_vantage": "ok", "fred": "ok",
            "news_api": "ok", "reddit": "ok", "claude_api": "ok",
            "finbert": "ok", "fear_greed": "ok", "google_trends": "ok",
        }

        # Batch prefetch all price histories in one yfinance call (much faster than one-by-one)
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

                # Long-horizon metrics (5Y price history, cached 24h)
                long_df = fetch_price_history_extended(ticker, years=5)
                long_metrics = compute_long_horizon_metrics(
                    long_df, expense_ratio=quote.get("expense_ratio")
                )
                investment_scenarios = compute_investment_scenarios(
                    long_df, current_price=quote.get("current_price"),
                    expense_ratio=quote.get("expense_ratio")
                )
                macro = score_macro_environment(ticker, macro_data, fear_greed=fear_greed)

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
                    logger.debug(f"Google Trends failed for {ticker} (expected on cloud IPs): {e}")
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

                # Price history sparkline (last 20 days)
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
        _last_updated = datetime.now(timezone.utc)
        _data_source_status = source_status

        # Snapshot this forecast once per day for self-improvement tracking
        try:
            from prediction_store import log_predictions
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if _last_log_date != today_str:
                log_predictions(ranked)
                _last_log_date = today_str
                logger.info(f"Daily predictions logged ({today_str}).")
            else:
                logger.info("Predictions already logged today — skipping.")
        except Exception as e:
            logger.warning(f"log_predictions failed: {e}")

        # Triple Lock alert check — compare ranks against previous cycle
        try:
            from alerter import check_and_alert
            fired = check_and_alert(ranked, _prev_ranks)
            if fired:
                logger.info(f"Alerts fired for: {fired}")
        except Exception as e:
            logger.warning(f"check_and_alert failed: {e}")

        # Update prev_ranks for next cycle
        _prev_ranks = {f["ticker"]: f["rank"] for f in ranked}

        result = {
            "funds": ranked,
            "last_updated": _last_updated.isoformat(),
            "data_source_status": source_status,
            "total_funds": len(ranked),
            "fear_greed": fear_greed,
        }

        _cache_set(_forecast_cache_key, json.dumps(result, default=str), 14400)  # 4h — matches scheduler
        logger.info(f"Forecast complete: {len(ranked)} funds ranked.")
        return result

    finally:
        _build_lock.release()


def _parse_forecast(raw: dict) -> ForecastResponse:
    funds = []
    for f in raw.get("funds", []):
        t = f["technical"]
        m = f["macro"]
        s = f["sentiment"]
        b = f.get("backtest") or {}

        lm_raw = f.get("long_metrics") or {}
        funds.append(FundForecast(
            ticker=f["ticker"],
            fund_name=f["fund_name"],
            composite_score=f["composite_score"],
            confidence_level=f["confidence_level"],
            rank=f["rank"],
            score_7d=f.get("score_7d"),
            score_30d=f.get("score_30d"),
            score_1y=f.get("score_1y"),
            score_5y=f.get("score_5y"),
            rank_7d=f.get("rank_7d"),
            rank_30d=f.get("rank_30d"),
            rank_1y=f.get("rank_1y"),
            rank_5y=f.get("rank_5y"),
            fundamental_score_1y=f.get("fundamental_score_1y"),
            fundamental_score_5y=f.get("fundamental_score_5y"),
            technical=TechnicalSignals(**t),
            macro=MacroSignals(**m),
            sentiment=SentimentResult(**s),
            backtest=BacktestResult(**b) if b else None,
            long_metrics=LongHorizonMetrics(**lm_raw) if lm_raw else None,
            investment_scenarios=InvestmentScenarios(**f["investment_scenarios"]) if f.get("investment_scenarios") else None,
            currency=f.get("currency", "USD"),
            current_price=f.get("current_price"),
            market_cap=f.get("market_cap"),
            volume=f.get("volume"),
            dividend_yield=f.get("dividend_yield"),
            beta=f.get("beta"),
            pe_ratio=f.get("pe_ratio"),
            expense_ratio=f.get("expense_ratio"),
            return_5d=f.get("return_5d"),
            return_1d=f.get("return_1d"),
            return_1m=f.get("return_1m"),
            google_trends_score=f.get("google_trends_score"),
            google_trends_direction=f.get("google_trends_direction"),
            price_history=[PricePoint(**p) for p in f.get("price_history", [])],
            ai_rationale=f.get("ai_rationale"),
            key_signals=f.get("key_signals", []),
            last_updated=raw.get("last_updated"),
        ))

    return ForecastResponse(
        funds=funds,
        last_updated=raw["last_updated"],
        data_source_status=raw["data_source_status"],
        total_funds=raw["total_funds"],
        fear_greed=raw.get("fear_greed"),
    )


def _self_improvement_job():
    """Wrapper so APScheduler can call the sync function safely."""
    try:
        from self_improver import run_self_improvement
        run_self_improvement()
    except Exception as e:
        logger.error(f"Self-improvement job error: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # BackgroundScheduler runs in a dedicated thread — never blocks the event loop
    scheduler.add_job(build_forecast_sync, "interval", hours=4, id="forecast_refresh",
                      next_run_time=datetime.now(timezone.utc))
    scheduler.add_job(_self_improvement_job, "interval", hours=24, id="self_improve")
    scheduler.start()
    logger.info("Scheduler started. Initial forecast building in background thread.")
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Index Fund Forecaster API",
    description="AI-powered 7-day index fund ranking and outlook",
    version="2.0.0",
    lifespan=lifespan,
)

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/status")
async def get_status():
    cached = _cache_get(_forecast_cache_key)
    if cached:
        return {"ready": True, "last_updated": _last_updated.isoformat() if _last_updated else None}
    return {"ready": False, "message": "Forecast is still building, check back in ~60 seconds"}


@app.get("/api/meta")
async def meta():
    return {
        "last_updated": _last_updated.isoformat() if _last_updated else None,
        "data_source_status": _data_source_status,
        "tracked_tickers": TICKERS,
    }


@app.get("/api/forecast", response_model=ForecastResponse)
async def get_forecast():
    cached = _cache_get(_forecast_cache_key)
    if cached:
        try:
            raw = json.loads(cached)
            return _parse_forecast(raw)
        except Exception as e:
            logger.warning(f"Cache parse failed: {e}")

    # Not ready yet — build synchronously in a thread so event loop stays free
    raw = await asyncio.to_thread(build_forecast_sync)
    return _parse_forecast(raw)


@app.get("/api/fund/{ticker}")
async def get_fund(ticker: str):
    ticker = ticker.upper()
    if ticker not in TICKERS:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not tracked")

    cached = _cache_get(_forecast_cache_key)
    if cached:
        try:
            raw = json.loads(cached)
            for f in raw.get("funds", []):
                if f["ticker"] == ticker:
                    return f
        except Exception:
            pass

    raise HTTPException(status_code=503, detail="Forecast not yet available. Try /api/forecast first.")


@app.get("/api/refresh")
async def refresh(background_tasks: BackgroundTasks):
    invalidate_cache()
    background_tasks.add_task(asyncio.to_thread, build_forecast_sync)
    return {"status": "refresh_triggered", "message": "Cache invalidated. Rebuild in progress."}


@app.get("/api/track-record")
async def track_record():
    """Aggregate accuracy statistics for past predictions."""
    try:
        from prediction_store import get_track_record_stats
        return get_track_record_stats()
    except Exception as e:
        logger.error(f"track_record error: {e}")
        return {"available": False, "error": str(e)}


@app.get("/api/predictions-status")
async def predictions_status():
    """In-flight prediction count, days-to-first-result, and current top picks."""
    try:
        from prediction_store import get_predictions_status
        return get_predictions_status()
    except Exception as e:
        logger.error(f"predictions_status error: {e}")
        return {"total_logged": 0, "days_until_first_eval": None, "top_picks_in_flight": [], "error": str(e)}


@app.get("/api/model-insights")
async def model_insights():
    """Current adaptive weights and recent weight-change history."""
    try:
        from prediction_store import get_weight_history
        from self_improver import load_weights
        return {
            "current_weights": load_weights(),
            "weight_history":  get_weight_history(limit=20),
        }
    except Exception as e:
        logger.error(f"model_insights error: {e}")
        return {"current_weights": None, "weight_history": [], "error": str(e)}
