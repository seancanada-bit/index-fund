"""
Triple Lock alert system.
Fires an email when a fund simultaneously meets all 5 breakout conditions.
Config via env vars:
    ALERT_EMAIL_FROM      — Gmail address to send from
    ALERT_EMAIL_PASSWORD  — Gmail app password (16 chars)
    ALERT_EMAIL_TO        — Recipient address (can be same as FROM)
"""
import os
import smtplib
import statistics
import logging
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
COMPOSITE_THRESHOLD = 78    # top ~5% of historical scores
SUB_SCORE_THRESHOLD = 65    # each of technical / macro / sentiment must clear this
RANK_JUMP_MIN       = 3     # positions gained vs previous cycle
STDDEV_MIN          = 1.5   # standard deviations above cohort mean
COOLDOWN_HOURS      = 48    # same ticker cannot re-alert within this window

# In-memory cooldown fallback (used when DB is unavailable)
_alert_cooldowns: dict = {}


# ── Cooldown helpers ──────────────────────────────────────────────────────────
def _get_cooldown(ticker: str):
    """Return datetime of last alert for ticker, or None."""
    try:
        from prediction_store import get_alert_cooldown
        return get_alert_cooldown(ticker)
    except Exception:
        return _alert_cooldowns.get(ticker)


def _set_cooldown(ticker: str):
    now = datetime.now(timezone.utc)
    _alert_cooldowns[ticker] = now
    try:
        from prediction_store import set_alert_cooldown
        set_alert_cooldown(ticker, now)
    except Exception:
        pass


def _is_on_cooldown(ticker: str) -> bool:
    last = _get_cooldown(ticker)
    if last is None:
        return False
    return datetime.now(timezone.utc) - last < timedelta(hours=COOLDOWN_HOURS)


# ── Email sender ──────────────────────────────────────────────────────────────
def send_alert_email(subject: str, body: str):
    email_from = os.getenv("ALERT_EMAIL_FROM")
    email_to   = os.getenv("ALERT_EMAIL_TO")
    password   = os.getenv("ALERT_EMAIL_PASSWORD")

    if not all([email_from, email_to, password]):
        logger.warning("Alert email env vars not configured — skipping send.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = email_from
    msg["To"]      = email_to
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(email_from, password)
            smtp.send_message(msg)
        logger.info(f"Alert email sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")


# ── Triple Lock evaluator ─────────────────────────────────────────────────────
def _evaluate_triple_lock(
    fund: dict,
    all_funds: list,
    prev_ranks: dict,
) -> tuple:
    """
    Returns (triggered: bool, signals: list[str]).
    All 6 conditions must pass for triggered=True.
    """
    ticker          = fund.get("ticker", "")
    composite       = fund.get("composite_score", 0)
    technical_score = fund.get("technical", {}).get("technical_score", 0)
    macro_score     = fund.get("macro", {}).get("macro_score", 0)
    sentiment_score = fund.get("sentiment", {}).get("final_sentiment_score", 0)
    score_7d        = fund.get("score_7d") or composite
    score_30d       = fund.get("score_30d") or 0
    confidence      = fund.get("confidence_level", "low")
    current_rank    = fund.get("rank", 99)
    prev_rank       = prev_ranks.get(ticker, current_rank)

    failures = []
    passed   = []

    # 1. Composite score
    if composite >= COMPOSITE_THRESHOLD:
        passed.append(f"Composite score {composite:.1f} >= {COMPOSITE_THRESHOLD}")
    else:
        failures.append(f"Composite {composite:.1f} below threshold {COMPOSITE_THRESHOLD}")

    # 2. Triple sub-score confirmation
    if all(s >= SUB_SCORE_THRESHOLD for s in [technical_score, macro_score, sentiment_score]):
        passed.append(
            f"Triple confirmation — Technical:{technical_score:.0f}  "
            f"Macro:{macro_score:.0f}  Sentiment:{sentiment_score:.0f}"
        )
    else:
        failures.append(
            f"Sub-scores not all >= {SUB_SCORE_THRESHOLD} "
            f"(T:{technical_score:.0f} M:{macro_score:.0f} S:{sentiment_score:.0f})"
        )

    # 3. Upward momentum (7d > 30d > 0)
    if score_7d > score_30d > 0:
        passed.append(f"Upward momentum — 7d:{score_7d:.1f} > 30d:{score_30d:.1f}")
    else:
        failures.append(f"Momentum check failed (7d:{score_7d:.1f}, 30d:{score_30d:.1f})")

    # 4. Rank acceleration
    rank_jump = prev_rank - current_rank   # positive = improved
    if rank_jump >= RANK_JUMP_MIN:
        passed.append(f"Rank jumped {rank_jump} positions (#{prev_rank} -> #{current_rank})")
    else:
        failures.append(f"Rank jump {rank_jump} < {RANK_JUMP_MIN} required")

    # 5. Model confidence
    if confidence == "high":
        passed.append("Model confidence: HIGH")
    else:
        failures.append(f"Confidence '{confidence}' not 'high'")

    # 6. Cohort outlier (>= 1.5 standard deviations above mean)
    all_scores = [f.get("composite_score", 0) for f in all_funds]
    if len(all_scores) >= 5:
        try:
            mean  = statistics.mean(all_scores)
            stdev = statistics.stdev(all_scores)
            z     = (composite - mean) / stdev if stdev > 0 else 0
            if z >= STDDEV_MIN:
                passed.append(f"Cohort outlier: {z:.2f} std devs above mean")
            else:
                failures.append(f"Only {z:.2f} std devs above cohort mean (need {STDDEV_MIN})")
        except Exception:
            pass  # skip cohort check if stats fail

    triggered = len(failures) == 0
    return triggered, passed if triggered else failures


# ── Public entry point ────────────────────────────────────────────────────────
def check_and_alert(ranked_funds: list, prev_ranks: dict) -> list:
    """
    Evaluate every fund against the Triple Lock formula.
    Sends an email for each fund that passes and is not on cooldown.
    Returns list of tickers that triggered.

    Args:
        ranked_funds: output of rank_funds() — list of fund dicts
        prev_ranks:   {ticker: rank_int} from the previous forecast cycle
    """
    triggered = []

    for fund in ranked_funds:
        ticker = fund.get("ticker", "")

        if _is_on_cooldown(ticker):
            continue

        fired, signals = _evaluate_triple_lock(fund, ranked_funds, prev_ranks)

        if not fired:
            continue

        _set_cooldown(ticker)
        triggered.append(ticker)

        fund_name  = fund.get("fund_name", ticker)
        composite  = fund.get("composite_score", 0)
        rank       = fund.get("rank", "?")
        prev_r     = prev_ranks.get(ticker, rank)
        price      = fund.get("current_price")
        currency   = fund.get("currency", "USD")
        price_str  = f"{currency} ${price:.2f}" if price else "N/A"

        subject = f"IFF Breakout Alert: {ticker} — Triple Lock Signal"
        body = f"""Index Fund Forecaster — Breakout Alert
{'=' * 52}

Fund:            {fund_name} ({ticker})
Current Rank:    #{rank}  (was #{prev_r} last cycle)
Composite Score: {composite:.1f} / 100
Current Price:   {price_str}

All conditions confirmed:
{chr(10).join(f'  + {s}' for s in signals)}

This alert is generated by your self-improving forecasting model.
Not financial advice. Past signals do not guarantee future returns.

Full forecast: https://pacificlogo.ca/sandbox/index-fund-forecaster/
"""
        send_alert_email(subject, body)
        logger.info(f"Triple Lock alert fired for {ticker} (score {composite:.1f}, rank #{rank})")

    return triggered
