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
import redis as redis_client

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "IndexFundForecaster/1.0")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

_mem_cache: dict = {}


def _get_redis():
    try:
        r = redis_client.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        r.ping()
        return r
    except Exception:
        return None


def _cache_get(key: str) -> Optional[str]:
    r = _get_redis()
    if r:
        try:
            return r.get(key)
        except Exception:
            pass
    entry = _mem_cache.get(key)
    if entry and entry["expires"] > time.time():
        return entry["value"]
    return None


def _cache_set(key: str, value: str, ttl: int):
    r = _get_redis()
    if r:
        try:
            r.setex(key, ttl, value)
            return
        except Exception:
            pass
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
                _cache_set(f"price_history:{ticker}:{days}", json.dumps(serializable.to_dict()), 1800)
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
            _cache_set(cache_key, json.dumps(serializable.to_dict()), 1800)
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
        _cache_set(cache_key, json.dumps(serializable.to_dict()), 1800)
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

        result = {
            "current_price": getattr(info, "last_price", None),
            "volume": getattr(info, "last_volume", None),
            "market_cap": getattr(info, "market_cap", None),
            "week_52_high": slow_info.get("fiftyTwoWeekHigh") or getattr(info, "year_high", None),
            "week_52_low": slow_info.get("fiftyTwoWeekLow") or getattr(info, "year_low", None),
            # dividendYield from yfinance is a decimal (0.03 = 3%); cap at 25% to filter bad data
            "dividend_yield": slow_info.get("dividendYield") if slow_info.get("dividendYield") and 0 < slow_info.get("dividendYield") < 0.25 else None,
            "beta": slow_info.get("beta"),
            "pe_ratio": slow_info.get("trailingPE"),
            "expense_ratio": slow_info.get("expenseRatio"),
        }
        if result["current_price"]:
            _cache_set(cache_key, json.dumps(result), 300)
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
        _cache_set(cache_key, json.dumps(result), 300)
    except Exception as e:
        logger.error(f"Alpha Vantage quote fallback failed for {ticker}: {e}")

    return result


def fetch_macro_data() -> dict:
    cache_key = "macro_data"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    series_ids = {
        "FEDFUNDS": "fed_funds_rate",
        "CPIAUCSL": "cpi",
        "UNRATE": "unemployment",
        "T10Y2Y": "yield_curve",
        "GDP": "gdp",
        "VIXCLS": "vix",
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

    _cache_set(cache_key, json.dumps(result), 3600)
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

    _cache_set(cache_key, json.dumps(articles), 3600)
    return articles


def fetch_news(ticker: str, fund_name: str, days: int = 3) -> list:
    cache_key = f"news:{ticker}"
    cached = _cache_get(cache_key)
    if cached:
        return json.loads(cached)

    articles = []
    # Always try yfinance news first (free, no quota)
    articles = fetch_yf_news(ticker)

    # Supplement with NewsAPI if key available
    if NEWS_API_KEY:
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
            logger.warning(f"NewsAPI failed for {ticker}: {e}")

    # Deduplicate by title
    seen = set()
    unique = []
    for a in articles:
        title = a.get("title", "")
        if title and title not in seen:
            seen.add(title)
            unique.append(a)

    _cache_set(cache_key, json.dumps(unique[:25]), 3600)
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

    _cache_set(cache_key, json.dumps(posts), 7200)
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

    _cache_set(cache_key, json.dumps(result), 3600)
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
            logger.warning(f"AV News Sentiment quota hit for {ticker}")
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


def invalidate_cache():
    r = _get_redis()
    if r:
        try:
            keys = r.keys("*")
            if keys:
                r.delete(*keys)
            return
        except Exception:
            pass
    _mem_cache.clear()
