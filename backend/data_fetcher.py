import os
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
import pandas as pd
import yfinance as yf
import requests
import praw
logger = logging.getLogger(__name__)

ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "IndexFundForecaster/1.0")

_mem_cache: dict = {}


def _cache_get(key: str) -> Optional[str]:
    entry = _mem_cache.get(key)
    if entry and entry["expires"] > time.time():
        return entry["value"]
    return None


def _cache_set(key: str, value: str, ttl: int):
    _mem_cache[key] = {"value": value, "expires": time.time() + ttl}


def _normalize_yf_df(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex columns returned by yfinance >= 0.2.50."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def prefetch_price_history_batch(tickers: list, days: int = 60):
    """
    Download price history for all tickers in a single yfinance call,
    then store each individually in cache. Dramatically faster than
    fetching one ticker at a time.
    """
    # Only fetch tickers that aren't already cached
    uncached = [t for t in tickers if not _cache_get(f"price_history:{t}:{days}")]
    if not uncached:
        logger.info("All price histories already cached — skipping batch fetch.")
        return

    logger.info(f"Batch fetching price history for {len(uncached)} tickers...")
    end = datetime.now()
    start = end - timedelta(days=days + 10)

    try:
        df_all = yf.download(
            uncached,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
            group_by="ticker",
            threads=True,
        )
        if df_all is None or df_all.empty:
            logger.warning("Batch download returned empty DataFrame.")
            return

        for ticker in uncached:
            try:
                # Single-ticker download has flat columns; multi-ticker has MultiIndex
                if len(uncached) == 1:
                    df = df_all.copy()
                else:
                    if ticker not in df_all.columns.get_level_values(0):
                        logger.warning(f"Batch: {ticker} not in result columns.")
                        continue
                    df = df_all[ticker].copy()

                df = _normalize_yf_df(df)
                df.dropna(how="all", inplace=True)
                if len(df) == 0:
                    continue

                df = df.tail(days)
                serializable = df.copy()
                serializable.index = serializable.index.strftime("%Y-%m-%d")
                _cache_set(f"price_history:{ticker}:{days}", json.dumps(serializable.to_dict()), 14400)  # 4h
            except Exception as e:
                logger.warning(f"Batch cache store failed for {ticker}: {e}")

        logger.info(f"Batch price fetch complete for {len(uncached)} tickers.")
    except Exception as e:
        logger.warning(f"Batch price history fetch failed: {e}")


def fetch_price_history(ticker: str, days: int = 60) -> pd.DataFrame:
    cache_key = f"price_history:{ticker}:{days}"
    cached = _cache_get(cache_key)
    if cached:
        data = json.loads(cached)
        df = pd.DataFrame(data)
        df.index = pd.to_datetime(df.index)
        return df

    try:
        end = datetime.now()
        start = end - timedelta(days=days + 10)
        df = yf.download(ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"),
                         auto_adjust=True, progress=False, group_by="column")
        df = _normalize_yf_df(df)
        if df is not None and len(df) > 0:
            df = df.tail(days)
            serializable = df.copy()
            serializable.index = serializable.index.strftime("%Y-%m-%d")
            _cache_set(cache_key, json.dumps(serializable.to_dict()), 14400)  # 4h
            return df
    except Exception as e:
        logger.warning(f"yfinance failed for {ticker}: {e}")

    # Fallback: Alpha Vantage
    try:
        url = (
            f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED"
            f"&symbol={ticker}&outputsize=compact&apikey={ALPHA_VANTAGE_KEY}"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        resp_json = resp.json()
        raw = resp_json.get("Time Series (Daily)", {})
        if not raw:
            logger.warning(f"Alpha Vantage returned no data for {ticker}: {list(resp_json.keys())}")
            return pd.DataFrame()
        rows = []
        for date_str, vals in sorted(raw.items())[-days:]:
            close_key = "5. adjusted close" if "5. adjusted close" in vals else "4. close"
            rows.append({
                "Date": date_str,
                "Open": float(vals.get("1. open", 0)),
                "High": float(vals.get("2. high", 0)),
                "Low": float(vals.get("3. low", 0)),
                "Close": float(vals.get(close_key, 0)),
                "Volume": float(vals.get("6. volume", vals.get("5. volume", 0))),
            })
        df = pd.DataFrame(rows).set_index("Date")
        df.index = pd.to_datetime(df.index)
        serializable = df.copy()
        serializable.index = serializable.index.strftime("%Y-%m-%d")
        _cache_set(cache_key, json.dumps(serializable.to_dict()), 14400)  # 4h
        return df
    except Exception as e:
        logger.error(f"Alpha Vantage fallback failed for {ticker}: {e}")
        return pd.DataFrame()


def fetch_realtime_quote(ticker: str) -> dict:
    cache_key = f"quote:{ticker}"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    result = {}
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        slow_info = {}
        try:
            slow_info = t.info or {}
        except Exception:
            pass

        # AUM flow: compare current totalAssets vs 7-day cached baseline
        total_assets = slow_info.get("totalAssets")
        aum_flow_pct = None
        if total_assets and total_assets > 0:
            baseline_key = f"aum_baseline:{ticker}"
            baseline_raw = _cache_get(baseline_key)
            if baseline_raw:
                baseline_val = float(baseline_raw)
                if baseline_val > 0:
                    aum_flow_pct = round((total_assets - baseline_val) / baseline_val * 100, 2)
            else:
                _cache_set(baseline_key, str(total_assets), 604800)  # 7-day baseline

        result = {
            "current_price": getattr(info, "last_price", None),
            "volume": getattr(info, "last_volume", None),
            "market_cap": getattr(info, "market_cap", None),
            "week_52_high": slow_info.get("fiftyTwoWeekHigh") or getattr(info, "year_high", None),
            "week_52_low": slow_info.get("fiftyTwoWeekLow") or getattr(info, "year_low", None),
            "dividend_yield": slow_info.get("dividendYield") if slow_info.get("dividendYield") and 0 < slow_info.get("dividendYield") < 0.25 else None,
            "beta": slow_info.get("beta"),
            "pe_ratio": slow_info.get("trailingPE"),
            "expense_ratio": slow_info.get("expenseRatio"),
            "total_assets": total_assets,
            "aum_flow_7d_pct": aum_flow_pct,
        }
        if result["current_price"]:
            _cache_set(cache_key, json.dumps(result), 7200)  # 2h — avoid refetch on every hourly build
            return result
    except Exception as e:
        logger.warning(f"yfinance quote failed for {ticker}: {e}")

    # Fallback: Alpha Vantage GLOBAL_QUOTE
    try:
        url = (
            f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE"
            f"&symbol={ticker}&apikey={ALPHA_VANTAGE_KEY}"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        q = resp.json().get("Global Quote", {})
        result = {
            "current_price": float(q.get("05. price", 0)) or None,
            "volume": float(q.get("06. volume", 0)) or None,
            "market_cap": None,
            "week_52_high": None, "week_52_low": None,
            "dividend_yield": None, "beta": None, "pe_ratio": None,
        }
        _cache_set(cache_key, json.dumps(result), 3600)  # 1h
    except Exception as e:
        logger.error(f"Alpha Vantage quote fallback failed for {ticker}: {e}")

    return result


def fetch_macro_data() -> dict:
    cache_key = "macro_data"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    series_ids = {
        # US macro
        "FEDFUNDS": "fed_funds_rate",
        "CPIAUCSL": "cpi",
        "UNRATE": "unemployment",
        "T10Y2Y": "yield_curve",
        "GDP": "gdp",
        "VIXCLS": "vix",
        # Credit spreads — best leading indicator of risk-off
        "BAMLH0A0HYM2": "hy_oas",         # ICE BofA HY OAS
        "BAMLH0A1HYBB": "bb_spread",       # BB spread
        # Leading indicators
        "ICSA": "initial_claims",           # Weekly initial jobless claims
        # Canadian macro (for .TO tickers)
        "CPALTT01CAM657N": "ca_cpi",
        "LRUNTTTTCAM156S": "ca_unemployment",
        "IRSTCB01CAM156N": "ca_rate",
    }

    result = {}
    for series_id, key in series_ids.items():
        try:
            url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
                f"&sort_order=desc&limit=6"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            obs = resp.json().get("observations", [])
            valid = [o for o in obs if o.get("value") not in (".", None, "")]
            if valid:
                result[key] = {
                    "latest": float(valid[0]["value"]),
                    "previous": float(valid[1]["value"]) if len(valid) > 1 else None,
                    "3m_ago": float(valid[3]["value"]) if len(valid) > 3 else None,
                    "date": valid[0]["date"],
                }
        except Exception as e:
            logger.warning(f"FRED fetch failed for {series_id}: {e}")
            result[key] = None

    _cache_set(cache_key, json.dumps(result), 21600)
    return result


def fetch_fear_greed() -> dict:
    """Fetch CNN Fear & Greed Index — free, no API key needed."""
    cache_key = "fear_greed"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    result = {"score": 50.0, "rating": "neutral", "available": False}
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        fg = data.get("fear_and_greed", {})
        result = {
            "score": round(float(fg.get("score", 50)), 1),
            "rating": fg.get("rating", "neutral"),
            "available": True,
        }
        logger.info(f"Fear & Greed: {result['score']} ({result['rating']})")
    except Exception as e:
        logger.warning(f"Fear & Greed fetch failed: {e}")

    _cache_set(cache_key, json.dumps(result), 21600)  # 6h — index only shifts slowly
    return result


def fetch_cboe_put_call() -> dict:
    """Fetch CBOE equity put/call ratio — free, no key, strong institutional sentiment signal."""
    cache_key = "cboe_put_call"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    result = {"available": False, "equity_pcr": None, "signal": "neutral"}
    try:
        # Try historical data page first (the CDN endpoint started returning 403)
        urls = [
            "https://cdn.cboe.com/api/global/us_indices/daily_prices/PCR_History.csv",
            "https://www.cboe.com/us/options/market_statistics/daily/?mkt=cone&dt=",
        ]
        resp = None
        for url in urls:
            try:
                resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                if "," in resp.text and len(resp.text) > 100:
                    break
            except Exception:
                resp = None
                continue
        if resp is None:
            raise ValueError("All CBOE endpoints failed")
        lines = [l for l in resp.text.strip().split("\n") if l.strip()]
        # Header: Date, Total, Index, Exchange, Equity
        last = lines[-1].split(",")
        if len(last) >= 5:
            equity_pcr = float(last[4])
            total_pcr = float(last[1])
            # Equity P/C >0.85: heavy hedging = institutional fear (bearish)
            # Equity P/C <0.55: complacency = overbought warning (contrarian bearish)
            if equity_pcr > 0.85:
                signal = "bearish"
            elif equity_pcr < 0.55:
                signal = "complacent"
            else:
                signal = "neutral"
            result = {
                "available": True,
                "equity_pcr": round(equity_pcr, 3),
                "total_pcr": round(total_pcr, 3),
                "signal": signal,
                "date": last[0].strip(),
            }
            logger.info(f"CBOE equity P/C: {equity_pcr:.3f} ({signal})")
    except Exception as e:
        logger.warning(f"CBOE P/C fetch failed: {e}")

    _cache_set(cache_key, json.dumps(result), 86400)  # 24h — published once per trading day
    return result


def fetch_treasury_yield_curve() -> dict:
    """Full US Treasury yield curve — free, no key. Provides 3m-10Y spread (best recession signal)."""
    cache_key = "treasury_yield_curve"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    result = {"available": False}
    try:
        year = datetime.now().year
        url = (
            f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            f"daily-treasury-rates.csv/{year}/all"
            f"?type=daily_treasury_yield_curve&field_tdr_date_value={year}&submit"
        )
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        lines = [l for l in resp.text.strip().split("\n") if l.strip()]
        header = [h.strip().strip('"') for h in lines[0].split(",")]
        last = [v.strip().strip('"') for v in lines[-1].split(",")]

        def get_col(name):
            try:
                return float(last[header.index(name)]) if last[header.index(name)] else None
            except (ValueError, IndexError):
                return None

        m3 = get_col("3 Mo")
        y2 = get_col("2 Yr")
        y5 = get_col("5 Yr")
        y10 = get_col("10 Yr")
        y30 = get_col("30 Yr")

        if y10 is not None and m3 is not None:
            spread_10y_3m = round(y10 - m3, 3)
            result = {
                "available": True,
                "date": last[0],
                "3m": m3, "2y": y2, "5y": y5, "10y": y10, "30y": y30,
                "spread_10y_2y": round(y10 - y2, 3) if y2 else None,
                "spread_10y_3m": spread_10y_3m,  # Fed's preferred recession indicator
                "spread_30y_5y": round(y30 - y5, 3) if y30 and y5 else None,
                "inverted_3m_10y": spread_10y_3m < 0,
                "inverted_2y_10y": (round(y10 - y2, 3) < 0) if y2 else None,
            }
            logger.info(f"Treasury curve: 10Y={y10}% 3m={m3}% spread={spread_10y_3m:+.3f}%")
    except Exception as e:
        logger.warning(f"Treasury yield curve fetch failed: {e}")

    _cache_set(cache_key, json.dumps(result), 86400)  # 24h — published once per trading day
    return result


def fetch_yf_news(ticker: str) -> list:
    """Fetch news via yfinance — no API key needed."""
    cache_key = f"yf_news:{ticker}"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    articles = []
    try:
        t = yf.Ticker(ticker)
        news_items = t.news or []
        for item in news_items[:15]:
            pub_time = item.get("providerPublishTime", 0)
            pub_iso = datetime.utcfromtimestamp(pub_time).isoformat() + "Z" if pub_time else ""
            articles.append({
                "title": item.get("title", ""),
                "description": item.get("summary", ""),
                "source": item.get("publisher", "yfinance"),
                "publishedAt": pub_iso,
                "url": item.get("link", ""),
            })
    except Exception as e:
        logger.warning(f"yfinance news failed for {ticker}: {e}")

    _cache_set(cache_key, json.dumps(articles), 43200)  # 12h — news headlines don't change fast
    return articles


def fetch_news(ticker: str, fund_name: str, days: int = 3) -> list:
    cache_key = f"news:{ticker}"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    articles = []
    # Always try yfinance news first (free, no quota)
    articles = fetch_yf_news(ticker)

    # Supplement with NewsAPI if key available — skip .TO tickers (poor coverage) to preserve quota
    if NEWS_API_KEY and not ticker.endswith(".TO"):
        try:
            from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            query = f"{ticker} OR {fund_name}"
            url = (
                f"https://newsapi.org/v2/everything?q={requests.utils.quote(query)}"
                f"&from={from_date}&sortBy=publishedAt&pageSize=20&language=en"
                f"&apiKey={NEWS_API_KEY}"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            raw_articles = resp.json().get("articles", [])
            for a in raw_articles[:20]:
                articles.append({
                    "title": a.get("title", ""),
                    "description": a.get("description", ""),
                    "source": a.get("source", {}).get("name", ""),
                    "publishedAt": a.get("publishedAt", ""),
                    "url": a.get("url", ""),
                })
        except Exception as e:
            logger.debug(f"NewsAPI failed for {ticker}: {e}")

    # Deduplicate by title
    seen = set()
    unique = []
    for a in articles:
        title = a.get("title", "")
        if title and title not in seen:
            seen.add(title)
            unique.append(a)

    _cache_set(cache_key, json.dumps(unique[:25]), 86400)  # 24h — keeps NewsAPI well under 100 req/day
    return unique[:25]


def fetch_google_trends(ticker: str) -> dict:
    """Fetch Google Trends search interest — free, no key needed."""
    cache_key = f"trends:{ticker}"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    result = {"score": 50.0, "trend_direction": 0, "available": False}
    try:
        from pytrends.request import TrendReq
        time.sleep(1.0)  # Rate limiting — required by pytrends
        pt = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
        pt.build_payload([ticker], timeframe="now 7-d", geo="US")
        df = pt.interest_over_time()
        if df is not None and not df.empty and ticker in df.columns:
            values = df[ticker].values.astype(float)
            avg = float(values.mean())
            # Trend: compare last 3 periods vs first 4
            recent = float(values[-3:].mean()) if len(values) >= 3 else avg
            older = float(values[:4].mean()) if len(values) >= 4 else avg
            if older > 0:
                direction = 1 if recent > older * 1.1 else (-1 if recent < older * 0.9 else 0)
            else:
                direction = 0
            result = {"score": round(avg, 1), "trend_direction": direction, "available": True}
    except Exception as e:
        logger.debug(f"Google Trends failed for {ticker} (expected on cloud IPs): {e}")

    _cache_set(cache_key, json.dumps(result), 86400)  # Cache 24h — trends change slowly
    return result


def fetch_price_history_extended(ticker: str, years: int = 5) -> "pd.DataFrame":
    """Fetch multi-year daily price history for long-horizon metrics. Cached 24h."""
    cache_key = f"price_long:{ticker}:{years}y"
    cached = _cache_get(cache_key)
    if cached:
        data = json.loads(cached)
        df = pd.DataFrame(data)
        df.index = pd.to_datetime(df.index)
        return df

    try:
        period = f"{years}y"
        df = yf.download(ticker, period=period, auto_adjust=True, progress=False, group_by="column")
        df = _normalize_yf_df(df)
        if df is not None and len(df) > 50:
            serializable = df.copy()
            serializable.index = serializable.index.strftime("%Y-%m-%d")
            _cache_set(cache_key, json.dumps(serializable.to_dict()), 86400)  # 24h
            return df
    except Exception as e:
        logger.warning(f"Extended price fetch failed for {ticker}: {e}")

    return pd.DataFrame()


def fetch_reddit_sentiment(ticker: str) -> list:
    cache_key = f"reddit:{ticker}"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    posts = []
    try:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
        )
        # Broader subreddit coverage — Canadian tickers get CA-specific subs
        is_canadian = ticker.endswith(".TO")
        if is_canadian:
            subreddits = ["investing", "ETFs", "PersonalFinanceCanada", "CanadianInvestor", "CanadaFinance"]
        else:
            subreddits = ["investing", "stocks", "ETFs", "Bogleheads", "personalfinance"]

        # Use base ticker for search (strip .TO suffix)
        search_term = ticker.replace(".TO", "")
        cutoff = datetime.now() - timedelta(hours=48)

        for sub_name in subreddits:
            try:
                sub = reddit.subreddit(sub_name)
                for post in sub.search(search_term, sort="hot", time_filter="week", limit=15):
                    created = datetime.utcfromtimestamp(post.created_utc)
                    if created >= cutoff:
                        posts.append({
                            "title": post.title,
                            "score": post.score,
                            "num_comments": post.num_comments,
                            "subreddit": sub_name,
                            "created_utc": post.created_utc,
                        })
            except Exception as e:
                logger.warning(f"Reddit subreddit {sub_name} failed for {ticker}: {e}")

        posts = sorted(posts, key=lambda x: x["score"], reverse=True)[:20]
    except Exception as e:
        logger.warning(f"Reddit PRAW failed for {ticker}: {e}")

    _cache_set(cache_key, json.dumps(posts), 43200)  # 12h — Reddit discussions don't shift hourly
    return posts


def fetch_stocktwits(ticker: str) -> dict:
    """
    Fetch StockTwits bullish/bearish message counts — free, no API key needed.
    Users self-tag posts as Bullish/Bearish making this a clean sentiment signal.
    """
    cache_key = f"stocktwits:{ticker}"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    # StockTwits uses plain ticker symbols — strip .TO for Canadian funds
    st_ticker = ticker.replace(".TO", "").replace(".", "-")
    result = {"bullish": 0, "bearish": 0, "total": 0, "bull_ratio": 0.5, "available": False}

    try:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{st_ticker}.json"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; IndexFundForecaster/2.0)"}
        resp = requests.get(url, headers=headers, timeout=8)

        if resp.status_code == 200:
            data = resp.json()
            messages = data.get("messages", [])
            bull = sum(
                1 for m in messages
                if (m.get("entities") or {}).get("sentiment") and
                   m["entities"]["sentiment"].get("basic") == "Bullish"
            )
            bear = sum(
                1 for m in messages
                if (m.get("entities") or {}).get("sentiment") and
                   m["entities"]["sentiment"].get("basic") == "Bearish"
            )
            total = bull + bear
            result = {
                "bullish": bull,
                "bearish": bear,
                "total": total,
                "bull_ratio": round(bull / total, 3) if total > 0 else 0.5,
                "available": total >= 3,   # Only trust if at least 3 tagged messages
            }
            logger.info(f"StockTwits {ticker}: {bull} bull / {bear} bear ({total} tagged)")
        elif resp.status_code == 429:
            logger.warning(f"StockTwits rate limited for {ticker}")
        else:
            logger.debug(f"StockTwits {resp.status_code} for {ticker}")
    except Exception as e:
        logger.warning(f"StockTwits fetch failed for {ticker}: {e}")

    _cache_set(cache_key, json.dumps(result), 21600)  # 6h — crowd sentiment shifts slowly
    return result


def fetch_av_news_sentiment(ticker: str) -> dict:
    """
    Fetch Alpha Vantage News Sentiment endpoint — 25 calls/day on free tier.
    Cached 24h per ticker to preserve quota. Skips Canadian .TO tickers (poor AV coverage).
    """
    if not ALPHA_VANTAGE_KEY:
        return {"available": False}
    if ticker.endswith(".TO"):
        return {"available": False}

    cache_key = f"av_news_sentiment:{ticker}"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    result = {"available": False}
    try:
        url = (
            f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT"
            f"&tickers={ticker}&apikey={ALPHA_VANTAGE_KEY}&limit=50"
        )
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Detect rate-limit / info messages
        if "Information" in data or "Note" in data:
            logger.debug(f"AV News Sentiment quota hit for {ticker}")
            _cache_set(cache_key, json.dumps(result), 3600)   # Short cache — retry later
            return result

        feed = data.get("feed", [])
        if not feed:
            _cache_set(cache_key, json.dumps(result), 86400)
            return result

        # Extract per-ticker sentiment; weight by relevance score
        scores, weights = [], []
        for article in feed[:50]:
            for ts in article.get("ticker_sentiment", []):
                if ts.get("ticker") == ticker:
                    try:
                        score = float(ts["ticker_sentiment_score"])
                        relevance = float(ts.get("relevance_score", 0))
                        if relevance >= 0.1:
                            scores.append(score * 100)    # Scale -100 → +100
                            weights.append(relevance)
                    except (ValueError, TypeError, KeyError):
                        pass

        if scores:
            weighted_avg = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
            result = {
                "available": True,
                "score": round(weighted_avg, 2),
                "article_count": len(scores),
                "label": data.get("overall_sentiment_label", "Neutral"),
            }
            logger.info(f"AV News Sentiment {ticker}: {result['score']:.1f} ({len(scores)} articles)")

    except Exception as e:
        logger.warning(f"AV News Sentiment failed for {ticker}: {e}")

    _cache_set(cache_key, json.dumps(result), 86400)    # 24h cache — preserve daily quota
    return result


def fetch_cot_positioning() -> dict:
    """Fetch CFTC Commitments of Traders — institutional positioning in index/currency futures."""
    cache_key = "cot_positioning"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    result = {"available": False}
    try:
        # CFTC Disaggregated Futures-Only report (latest week)
        year = datetime.now().year
        url = f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()

        import zipfile
        import io
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            fname = z.namelist()[0]
            raw = z.read(fname).decode("utf-8", errors="replace")

        lines = raw.strip().split("\n")
        header = [h.strip().strip('"') for h in lines[0].split(",")]

        # Find key columns
        name_idx = next((i for i, h in enumerate(header) if "Market" in h and "Name" in h), 0)
        # Asset Manager/Institutional longs and shorts
        am_long_idx = next((i for i, h in enumerate(header) if "Asset Mgr" in h and "Long" in h and "All" not in h), None)
        am_short_idx = next((i for i, h in enumerate(header) if "Asset Mgr" in h and "Short" in h and "All" not in h), None)
        # Leveraged Funds (hedge funds) longs and shorts
        lf_long_idx = next((i for i, h in enumerate(header) if "Lev" in h and "Long" in h and "All" not in h), None)
        lf_short_idx = next((i for i, h in enumerate(header) if "Lev" in h and "Short" in h and "All" not in h), None)

        if am_long_idx is None:
            raise ValueError("Could not find Asset Manager columns in COT report")

        # Parse target markets
        targets = {
            "S&P 500": "sp500",
            "E-MINI S&P": "sp500",
            "NASDAQ": "nasdaq",
            "RUSSELL": "russell",
            "CANADIAN DOLLAR": "cad",
        }
        positions = {}

        for line in lines[1:]:
            fields = [f.strip().strip('"') for f in line.split(",")]
            if len(fields) <= max(am_long_idx, am_short_idx, lf_long_idx or 0, lf_short_idx or 0):
                continue
            name = fields[name_idx].upper()
            for pattern, key in targets.items():
                if pattern in name and key not in positions:
                    try:
                        am_net = int(fields[am_long_idx]) - int(fields[am_short_idx])
                        lf_net = 0
                        if lf_long_idx and lf_short_idx:
                            lf_net = int(fields[lf_long_idx]) - int(fields[lf_short_idx])
                        positions[key] = {
                            "asset_mgr_net": am_net,
                            "leveraged_net": lf_net,
                        }
                    except (ValueError, IndexError):
                        pass

        if positions:
            result = {"available": True, "positions": positions}
            logger.info(f"COT positioning loaded: {list(positions.keys())}")

    except Exception as e:
        logger.warning(f"COT fetch failed: {e}")

    _cache_set(cache_key, json.dumps(result), 86400)  # 24h — published weekly on Friday
    return result


def fetch_boc_data() -> dict:
    """Fetch Bank of Canada data — USD/CAD rate and policy rate. No API key needed."""
    cache_key = "boc_data"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    result = {"available": False}
    try:
        # USD/CAD exchange rate
        url = "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=10"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        obs = data.get("observations", [])
        if obs:
            latest_fx = float(obs[-1]["FXUSDCAD"]["v"])
            prev_fx = float(obs[-2]["FXUSDCAD"]["v"]) if len(obs) > 1 else None
            week_ago_fx = float(obs[-5]["FXUSDCAD"]["v"]) if len(obs) > 4 else None
            result["usd_cad"] = round(latest_fx, 4)
            result["usd_cad_prev"] = round(prev_fx, 4) if prev_fx else None
            result["usd_cad_1w_ago"] = round(week_ago_fx, 4) if week_ago_fx else None
            result["cad_trend"] = "weakening" if prev_fx and latest_fx > prev_fx else "strengthening"
            result["available"] = True
            logger.info(f"BoC USD/CAD: {latest_fx:.4f} (CAD {result['cad_trend']})")
    except Exception as e:
        logger.warning(f"BoC data fetch failed: {e}")

    _cache_set(cache_key, json.dumps(result), 21600)  # 6h
    return result


def fetch_aaii_sentiment() -> dict:
    """Fetch AAII Investor Sentiment Survey — classic contrarian indicator."""
    cache_key = "aaii_sentiment"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    result = {"available": False}
    try:
        # AAII publishes XML/JSON on their site; try scraping the summary page
        url = "https://www.aaii.com/sentimentsurvey/sent_results"
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })
        resp.raise_for_status()
        text = resp.text

        # Parse percentages from page — look for patterns like "Bullish 25.4%"
        import re
        bull_match = re.search(r'Bullish\s*[\s:]*(\d+\.?\d*)\s*%', text)
        bear_match = re.search(r'Bearish\s*[\s:]*(\d+\.?\d*)\s*%', text)
        neut_match = re.search(r'Neutral\s*[\s:]*(\d+\.?\d*)\s*%', text)

        if bull_match and bear_match:
            bull = float(bull_match.group(1))
            bear = float(bear_match.group(1))
            neutral = float(neut_match.group(1)) if neut_match else 100 - bull - bear
            spread = bull - bear

            if spread < -15:
                signal = "extreme_bearish"
            elif spread < 0:
                signal = "bearish"
            elif spread > 20:
                signal = "extreme_bullish"
            else:
                signal = "neutral"

            result = {
                "available": True,
                "bullish": round(bull, 1),
                "bearish": round(bear, 1),
                "neutral": round(neutral, 1),
                "bull_bear_spread": round(spread, 1),
                "signal": signal,
            }
            logger.info(f"AAII Sentiment: Bull={bull:.1f}% Bear={bear:.1f}% Spread={spread:+.1f}%")
    except Exception as e:
        logger.debug(f"AAII sentiment fetch failed: {e}")

    _cache_set(cache_key, json.dumps(result), 86400)  # 24h — published weekly
    return result


def invalidate_cache():
    _mem_cache.clear()
