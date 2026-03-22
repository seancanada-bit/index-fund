"""
Self-improvement engine.
Every 24 hours:
 1. Fetch current prices for predictions that are >=7 days old and unscored
 2. Compute actual 7-day returns and store as outcomes
 3. Run Pearson correlation between each sub-score and actual return
 4. Nudge the 7-day scoring weights toward better-correlated components
 5. Persist updated weights to Postgres (via prediction_store) + weights.json
"""
import os
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import prediction_store as store

logger = logging.getLogger(__name__)

_WEIGHTS_PATH = Path(__file__).parent / "weights.json"

DEFAULTS = {"technical": 0.55, "macro": 0.15, "sentiment": 0.30}
_LEARNING_RATE = 0.20   # How aggressively to shift weights each cycle (0=never, 1=full replacement)
_MIN_SAMPLES = 10        # Need at least this many evaluated pairs before adjusting


# ── Weights I/O ──────────────────────────────────────────────────────────────

def load_weights() -> dict:
    """
    Load current adaptive weights.
    Priority: Postgres weight_history → weights.json → hardcoded defaults.
    """
    # 1. Try Postgres
    try:
        history = store.get_weight_history(limit=1)
        if history:
            row = history[0]
            w = {
                "technical":  row.get("technical_weight",  DEFAULTS["technical"]),
                "macro":      row.get("macro_weight",      DEFAULTS["macro"]),
                "sentiment":  row.get("sentiment_weight",  DEFAULTS["sentiment"]),
                "updated_at": row.get("recorded_at"),
                "sample_count": row.get("sample_count", 0),
            }
            logger.debug(f"Weights loaded from Postgres: {w}")
            return w
    except Exception as e:
        logger.debug(f"load_weights Postgres fallback: {e}")

    # 2. Try local file
    try:
        if _WEIGHTS_PATH.exists():
            with open(_WEIGHTS_PATH) as f:
                w = json.load(f)
            logger.debug(f"Weights loaded from file: {w}")
            return w
    except Exception as e:
        logger.debug(f"load_weights file fallback: {e}")

    # 3. Hardcoded defaults
    return {**DEFAULTS, "updated_at": None, "sample_count": 0}


def save_weights(weights: dict, correlations: dict, sample_count: int, notes: str = ""):
    """Persist updated weights to both weights.json and Postgres."""
    payload = {
        "technical":  round(weights["technical"],  4),
        "macro":      round(weights["macro"],       4),
        "sentiment":  round(weights["sentiment"],   4),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": sample_count,
    }
    # File
    try:
        with open(_WEIGHTS_PATH, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logger.warning(f"save_weights file error: {e}")
    # Postgres
    try:
        store.log_weight_update(weights, correlations, sample_count, notes)
    except Exception as e:
        logger.warning(f"save_weights DB error: {e}")


# ── Math helpers ─────────────────────────────────────────────────────────────

def _pearson(xs: list, ys: list) -> float:
    """Pearson correlation without numpy/scipy."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx  = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy  = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def _softmax(d: dict) -> dict:
    """Normalise positive values in dict so they sum to 1."""
    floored = {k: max(v, 0.01) for k, v in d.items()}
    total = sum(floored.values())
    return {k: v / total for k, v in floored.items()}


# ── Outcome evaluation ────────────────────────────────────────────────────────

def evaluate_outcomes() -> int:
    """
    For every prediction older than 7 days without an outcome, fetch the
    current price from yfinance and record the actual 7-day return.
    Returns the number of newly evaluated predictions.
    """
    pending = store.get_unevaluated_predictions(min_age_days=7)
    if not pending:
        logger.info("No pending predictions to evaluate.")
        return 0

    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not available — cannot evaluate outcomes.")
        return 0

    # Group by ticker to minimise API calls
    by_ticker: dict[str, list] = {}
    for p in pending:
        by_ticker.setdefault(p["ticker"], []).append(p)

    evaluated = 0
    for ticker, preds in by_ticker.items():
        try:
            info = yf.Ticker(ticker).fast_info
            current_price = getattr(info, "last_price", None) or getattr(info, "regular_market_price", None)
            if current_price is None:
                logger.warning(f"Could not get current price for {ticker}")
                continue
            current_price = float(current_price)
        except Exception as e:
            logger.warning(f"yfinance error for {ticker}: {e}")
            continue

        for pred in preds:
            past_price = pred.get("price_at_prediction")
            if not past_price or past_price <= 0:
                continue
            actual_return = round(((current_price - past_price) / past_price) * 100, 4)
            try:
                store.log_outcome(
                    prediction_id=pred["id"],
                    price_at_eval=current_price,
                    actual_return=actual_return,
                    horizon_days=7,
                )
                evaluated += 1
            except Exception as e:
                logger.error(f"log_outcome failed for pred {pred['id']}: {e}")

    logger.info(f"Evaluated {evaluated} predictions.")
    return evaluated


# ── Weight adjustment ─────────────────────────────────────────────────────────

def adjust_weights() -> dict | None:
    """
    Analyse the prediction–outcome history.
    Compute Pearson correlation between each sub-score and the actual 7-day
    return.  Blend new weights toward higher-correlated components.
    Returns new weights dict (or None if insufficient data).
    """
    pairs = store.get_evaluated_pairs(limit=500)
    seven_day = [p for p in pairs if p.get("horizon_days") == 7]

    if len(seven_day) < _MIN_SAMPLES:
        logger.info(f"Insufficient data for weight adjustment ({len(seven_day)} < {_MIN_SAMPLES}).")
        return None

    returns = [p["actual_return"] for p in seven_day]
    tech_scores = [p["technical_score"] for p in seven_day]
    macro_scores = [p["macro_score"]    for p in seven_day]
    sent_scores  = [p["sentiment_score"] for p in seven_day]

    correlations = {
        "technical":  _pearson(tech_scores, returns),
        "macro":      _pearson(macro_scores, returns),
        "sentiment":  _pearson(sent_scores,  returns),
    }
    logger.info(f"Sub-score correlations with 7d return: {correlations}")

    # Use absolute correlations as signal strength (even negative correlation is informative
    # — a strongly negative-correlated score should still get some weight, just less)
    # Map to [0, 1] range where 1.0 = perfect correlation
    abs_corr = {k: abs(v) for k, v in correlations.items()}

    # Edge case: all near-zero correlations → keep current weights
    if max(abs_corr.values()) < 0.05:
        logger.info("All correlations near zero — weights unchanged.")
        return None

    # Target weights based on correlation magnitude
    target = _softmax(abs_corr)

    # Load current weights and blend
    current = load_weights()
    new_weights = {
        "technical": current.get("technical", DEFAULTS["technical"]) * (1 - _LEARNING_RATE) + target["technical"] * _LEARNING_RATE,
        "macro":     current.get("macro",     DEFAULTS["macro"])     * (1 - _LEARNING_RATE) + target["macro"]     * _LEARNING_RATE,
        "sentiment": current.get("sentiment", DEFAULTS["sentiment"]) * (1 - _LEARNING_RATE) + target["sentiment"] * _LEARNING_RATE,
    }

    # Re-normalise to ensure they sum to exactly 1.0
    new_weights = _softmax(new_weights)

    notes = (
        f"Adjusted from {len(seven_day)} samples. "
        f"Correlations — tech:{correlations['technical']:.3f} "
        f"macro:{correlations['macro']:.3f} "
        f"sent:{correlations['sentiment']:.3f}"
    )
    save_weights(new_weights, correlations, len(seven_day), notes)
    logger.info(f"Weights updated: {new_weights}")
    return new_weights


# ── Main cycle ────────────────────────────────────────────────────────────────

def run_self_improvement():
    """Full improvement cycle: evaluate outcomes → adjust weights."""
    logger.info("Self-improvement cycle starting...")
    try:
        n_evaluated = evaluate_outcomes()
        new_weights = adjust_weights()
        if new_weights:
            logger.info(f"Cycle complete. Evaluated {n_evaluated} predictions. New weights: {new_weights}")
        else:
            logger.info(f"Cycle complete. Evaluated {n_evaluated} predictions. Weights unchanged.")
    except Exception as e:
        logger.error(f"Self-improvement cycle error: {e}", exc_info=True)
