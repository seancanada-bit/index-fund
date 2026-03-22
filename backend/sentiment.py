import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

BULLISH_WORDS = {
    "surge", "surged", "surging", "beat", "beats", "rally", "rallied", "rallying",
    "upgrade", "upgraded", "strong", "strength", "growth", "grew", "gain", "gains",
    "outperform", "bullish", "record", "high", "boom", "booming", "positive",
    "upside", "buy", "opportunity", "recover", "recovered", "recovery", "momentum",
    "breakout", "inflow", "inflows", "robust", "accelerate", "accelerating",
}

BEARISH_WORDS = {
    "crash", "crashed", "crashing", "miss", "missed", "downgrade", "downgraded",
    "weak", "weakness", "recession", "sell-off", "selloff", "decline", "declined",
    "drop", "dropped", "fall", "fell", "risk", "bearish", "concern", "concerns",
    "volatile", "volatility", "uncertainty", "pressure", "loss", "losses",
    "inflation", "stagflation", "slowdown", "cut", "outflow", "outflows", "slump",
}

# FinBERT lazy-loaded pipeline
_finbert_pipeline = None
_finbert_attempted = False


def _get_finbert():
    global _finbert_pipeline, _finbert_attempted
    if _finbert_attempted:
        return _finbert_pipeline
    _finbert_attempted = True
    try:
        from transformers import pipeline as hf_pipeline
        logger.info("Loading FinBERT model (ProsusAI/finbert) — first run downloads ~440MB...")
        _finbert_pipeline = hf_pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            device=-1,           # CPU — works everywhere
            truncation=True,
            max_length=512,
            top_k=None,          # Return all 3 class scores
        )
        logger.info("FinBERT loaded successfully.")
    except Exception as e:
        logger.warning(f"FinBERT failed to load, will use keyword scoring: {e}")
        _finbert_pipeline = None
    return _finbert_pipeline


def finbert_score_texts(texts: list) -> float | None:
    """Score a list of texts using FinBERT. Returns -100 to +100."""
    pipe = _get_finbert()
    if pipe is None or not texts:
        return None

    scores = []
    for text in texts[:25]:
        text = text.strip()
        if not text:
            continue
        try:
            result = pipe(text[:512])  # Returns list of [{label, score}] for all classes
            # result is list of dicts for each class
            label_scores = {r["label"]: r["score"] for r in result[0]}
            pos = label_scores.get("positive", 0)
            neg = label_scores.get("negative", 0)
            # Net score: positive - negative, scaled to -100/+100
            scores.append((pos - neg) * 100)
        except Exception as e:
            logger.debug(f"FinBERT inference error: {e}")
            continue

    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


def _recency_weight(published_at: str) -> float:
    try:
        if published_at.endswith("Z"):
            published_at = published_at[:-1] + "+00:00"
        pub_time = datetime.fromisoformat(published_at)
        now = datetime.now(timezone.utc)
        hours_ago = (now - pub_time).total_seconds() / 3600
        if hours_ago <= 24:
            return 1.0
        elif hours_ago <= 48:
            return 0.7
        else:
            return 0.4
    except Exception:
        return 0.7


def _keyword_score(text: str) -> float:
    words = text.lower().split()
    bull = sum(1 for w in words if any(bw in w for bw in BULLISH_WORDS))
    bear = sum(1 for w in words if any(bw in w for bw in BEARISH_WORDS))
    total = bull + bear
    if total == 0:
        return 0.0
    return ((bull - bear) / total) * 100


def pre_score_headlines(news_articles: list, reddit_posts: list) -> float:
    total_weight = 0.0
    weighted_score = 0.0

    for article in news_articles:
        text = f"{article.get('title', '')} {article.get('description', '')}"
        score = _keyword_score(text)
        weight = _recency_weight(article.get("publishedAt", ""))
        weighted_score += score * weight
        total_weight += weight

    for post in reddit_posts:
        text = post.get("title", "")
        score = _keyword_score(text)
        upvote_weight = min(1.0 + post.get("score", 0) / 1000, 3.0)
        weight = 0.7 * upvote_weight
        weighted_score += score * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0
    return weighted_score / total_weight


def _claude_analyze(ticker: str, news_articles: list, reddit_posts: list) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    headlines = []
    for a in news_articles[:15]:
        headlines.append(f"[NEWS] {a.get('title', '')} - {a.get('source', '')}")
    for p in reddit_posts[:10]:
        headlines.append(f"[REDDIT r/{p.get('subreddit', 'investing')}] {p.get('title', '')} (score: {p.get('score', 0)})")

    if not headlines:
        raise ValueError("No content to analyze")

    content_str = "\n".join(headlines)
    system_prompt = (
        f"You are a quantitative financial analyst. Analyze the following recent news headlines "
        f"and social media posts about {ticker}. Return ONLY a valid JSON object with these exact fields:\n"
        '{\n'
        '  "sentiment": "bullish" | "neutral" | "bearish",\n'
        '  "confidence": "high" | "medium" | "low",\n'
        '  "score": <integer -100 to 100>,\n'
        '  "key_themes": [<up to 4 short theme strings>],\n'
        '  "rationale": "<2-3 sentence plain English summary>",\n'
        '  "risk_flags": [<up to 3 downside risks>]\n'
        '}\n'
        "Base your analysis on evidence in the provided content only."
    )

    last_error = None
    delays = [2, 4, 8]
    for attempt, delay in enumerate(delays):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                messages=[{"role": "user", "content": f"Content to analyze:\n{content_str}"}],
                system=system_prompt,
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            last_error = e
            err_str = str(e)
            logger.warning(f"Claude sentiment attempt {attempt + 1} failed for {ticker}: {type(e).__name__}")
            if "credit balance" in err_str or "401" in err_str or "permission" in err_str.lower():
                break
            if attempt < len(delays) - 1:
                time.sleep(delay)

    raise RuntimeError(f"All Claude retries failed: {last_error}")


def analyze_sentiment(
    ticker: str,
    news_articles: list,
    reddit_posts: list,
    google_trends: dict = None,
    stocktwits: dict = None,
    av_news: dict = None,
) -> dict:
    """
    Multi-source sentiment blend:
      1. Keyword scoring   (always available)
      2. FinBERT           (local model, always attempted)
      3. StockTwits        (free crowd sentiment — self-tagged bullish/bearish)
      4. AV News Sentiment (Alpha Vantage pre-scored articles, US tickers only)
      5. Google Trends     (search interest direction adjustment)

    Sources are combined using a dynamic weighted average that rewards
    having more signals available.
    """
    sources_used = []

    # ── Step 1: Keyword pre-score ─────────────────────────────────────────────
    raw_score = pre_score_headlines(news_articles, reddit_posts)
    sources_used.append("keyword")

    # ── Step 2: FinBERT on all available text ─────────────────────────────────
    all_texts = [
        (a.get("title") or "") + " " + (a.get("description") or "")
        for a in news_articles if a.get("title")
    ]
    all_texts += [p.get("title", "") for p in reddit_posts if p.get("title")]
    finbert_raw = finbert_score_texts(all_texts)
    if finbert_raw is not None:
        sources_used.append("finbert")

    # ── Step 3: StockTwits crowd sentiment ────────────────────────────────────
    # bull_ratio: 0.0 = fully bearish (-100), 0.5 = neutral (0), 1.0 = fully bullish (+100)
    stocktwits_score = None
    if stocktwits and stocktwits.get("available") and stocktwits.get("total", 0) >= 3:
        stocktwits_score = (stocktwits["bull_ratio"] - 0.5) * 200
        sources_used.append("stocktwits")

    # ── Step 4: Alpha Vantage pre-scored news ─────────────────────────────────
    av_score = None
    if av_news and av_news.get("available"):
        av_score = float(av_news.get("score", 0))
        sources_used.append("av_news")

    # ── Step 5: Dynamic weighted blend ───────────────────────────────────────
    # Weights sum to 1.0; FinBERT and AV News anchor the blend when available.
    #
    # Priority hierarchy (highest → lowest reliability):
    #   AV News > FinBERT > StockTwits > Keyword
    #
    # Baseline (keyword only): keyword 1.0
    # +FinBERT:                finbert 0.70, keyword 0.30
    # +StockTwits:             finbert 0.55, stocktwits 0.25, keyword 0.20
    # +AV News:                av_news 0.35, finbert 0.40, stocktwits 0.10, keyword 0.15
    # AV News only (no FinBERT): av_news 0.55, stocktwits 0.20, keyword 0.25

    if finbert_raw is not None and av_score is not None and stocktwits_score is not None:
        final_score = (av_score * 0.35 + finbert_raw * 0.40
                       + stocktwits_score * 0.10 + raw_score * 0.15)
        confidence = "high"
    elif finbert_raw is not None and av_score is not None:
        final_score = av_score * 0.40 + finbert_raw * 0.45 + raw_score * 0.15
        confidence = "high"
    elif finbert_raw is not None and stocktwits_score is not None:
        final_score = finbert_raw * 0.55 + stocktwits_score * 0.25 + raw_score * 0.20
        confidence = "medium"
    elif av_score is not None and stocktwits_score is not None:
        final_score = av_score * 0.55 + stocktwits_score * 0.20 + raw_score * 0.25
        confidence = "medium"
    elif finbert_raw is not None:
        final_score = finbert_raw * 0.70 + raw_score * 0.30
        confidence = "medium"
    elif av_score is not None:
        final_score = av_score * 0.65 + raw_score * 0.35
        confidence = "medium"
    elif stocktwits_score is not None:
        final_score = stocktwits_score * 0.60 + raw_score * 0.40
        confidence = "low"
    else:
        final_score = raw_score
        confidence = "low"

    # ── Step 6: Google Trends direction adjustment (±8 pts) ───────────────────
    trends_adjustment = 0.0
    if google_trends and google_trends.get("available"):
        direction = google_trends.get("trend_direction", 0)
        trends_adjustment = direction * 8.0
        final_score += trends_adjustment

    # ── Step 7: Derive labels from blended score ──────────────────────────────
    sentiment = "bullish" if final_score > 15 else ("bearish" if final_score < -15 else "neutral")

    # Build rationale from sources actually used
    source_str = " + ".join(sources_used)
    article_count = len(all_texts)
    rationale_parts = [f"Blended sentiment from {source_str} ({article_count} texts)."]
    if stocktwits and stocktwits.get("available"):
        st_bull = stocktwits.get("bullish", 0)
        st_bear = stocktwits.get("bearish", 0)
        rationale_parts.append(f"StockTwits: {st_bull} bullish / {st_bear} bearish tagged messages.")
    if av_news and av_news.get("available"):
        rationale_parts.append(
            f"AV News: {av_news.get('article_count', 0)} relevant articles, "
            f"label: {av_news.get('label', 'N/A')}."
        )

    # ── Normalize to 0-100 ────────────────────────────────────────────────────
    normalized = float((final_score + 100) / 2)
    normalized = max(0.0, min(100.0, normalized))

    return {
        "sentiment": sentiment,
        "confidence": confidence,
        "score": round(final_score, 2),
        "key_themes": [],
        "rationale": " ".join(rationale_parts),
        "risk_flags": [],
        "raw_keyword_score": round(raw_score, 2),
        "finbert_score": round(finbert_raw, 2) if finbert_raw is not None else None,
        "stocktwits_score": round(stocktwits_score, 2) if stocktwits_score is not None else None,
        "av_news_score": round(av_score, 2) if av_score is not None else None,
        "trends_adjustment": round(trends_adjustment, 2),
        "final_sentiment_score": round(normalized, 2),
        "data_source": "+".join(sources_used),
    }
