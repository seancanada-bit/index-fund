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


def analyze_sentiment(ticker: str, news_articles: list, reddit_posts: list,
                      google_trends: dict = None) -> dict:
    # Step 1: keyword pre-score
    raw_score = pre_score_headlines(news_articles, reddit_posts)

    # Step 2: FinBERT on all headlines (runs locally, always attempted)
    all_texts = [(a.get("title") or "") + " " + (a.get("description") or "")
                 for a in news_articles if a.get("title")]
    all_texts += [p.get("title", "") for p in reddit_posts if p.get("title")]
    finbert_raw = finbert_score_texts(all_texts)
    data_source = "finbert+keyword" if finbert_raw is not None else "keyword_fallback"

    # Step 3: Claude (disabled)
    claude_result = None

    # Step 4: Blend scores
    if claude_result and finbert_raw is not None:
        # All three available
        claude_score = float(claude_result.get("score", 0))
        final_score = claude_score * 0.50 + finbert_raw * 0.30 + raw_score * 0.20
        sentiment = claude_result.get("sentiment", "neutral")
        confidence = claude_result.get("confidence", "medium")
        key_themes = claude_result.get("key_themes", [])
        rationale = claude_result.get("rationale", "")
        risk_flags = claude_result.get("risk_flags", [])
    elif claude_result:
        claude_score = float(claude_result.get("score", 0))
        final_score = claude_score * 0.70 + raw_score * 0.30
        sentiment = claude_result.get("sentiment", "neutral")
        confidence = claude_result.get("confidence", "medium")
        key_themes = claude_result.get("key_themes", [])
        rationale = claude_result.get("rationale", "")
        risk_flags = claude_result.get("risk_flags", [])
    elif finbert_raw is not None:
        final_score = finbert_raw * 0.70 + raw_score * 0.30
        sentiment = "bullish" if final_score > 15 else ("bearish" if final_score < -15 else "neutral")
        confidence = "medium"
        key_themes = []
        rationale = f"FinBERT financial sentiment analysis of {len(all_texts)} recent headlines."
        risk_flags = []
    else:
        final_score = raw_score
        sentiment = "bullish" if raw_score > 20 else ("bearish" if raw_score < -20 else "neutral")
        confidence = "low"
        key_themes = []
        rationale = "Keyword-based sentiment scoring only."
        risk_flags = []

    # Step 5: Adjust for Google Trends (if rising interest, small boost)
    trends_adjustment = 0.0
    if google_trends and google_trends.get("available"):
        direction = google_trends.get("trend_direction", 0)
        trends_adjustment = direction * 8.0  # ±8 points for trending up/down
        final_score += trends_adjustment

    # Normalize to 0-100
    normalized = float((final_score + 100) / 2)
    normalized = max(0.0, min(100.0, normalized))

    return {
        "sentiment": sentiment,
        "confidence": confidence,
        "score": round(float(claude_result["score"]) if claude_result else (finbert_raw or raw_score), 2),
        "key_themes": key_themes,
        "rationale": rationale,
        "risk_flags": risk_flags,
        "raw_keyword_score": round(raw_score, 2),
        "finbert_score": round(finbert_raw, 2) if finbert_raw is not None else None,
        "trends_adjustment": round(trends_adjustment, 2),
        "final_sentiment_score": round(normalized, 2),
        "data_source": data_source,
    }
