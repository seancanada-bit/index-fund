"""
Self-improvement engine — runs every 24 hours.

Cycle:
 1. Evaluate 7d outcomes for predictions ≥7 days old
 2. Evaluate 30d outcomes for predictions ≥30 days old
 3. Compute recency-weighted Pearson correlation for each sub-score vs actual return
    (recent data weighted exponentially higher; half-life = 30 days)
 4. Nudge weights toward better-correlated components at a conservative learning rate
 5. Persist 7d and 30d weights separately to Postgres + JSON fallback files
"""
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import prediction_store as store

logger = logging.getLogger(__name__)

_WEIGHTS_7D_PATH  = Path(__file__).parent / "weights.json"
_WEIGHTS_30D_PATH = Path(__file__).parent / "weights_30d.json"

DEFAULTS_7D  = {"technical": 0.55, "macro": 0.15, "sentiment": 0.30}
DEFAULTS_30D = {"technical": 0.30, "macro": 0.45, "sentiment": 0.25}

_LEARNING_RATE   = 0.20   # Max shift per cycle (0 = frozen, 1 = full replacement)
_MIN_SAMPLES     = 10     # Minimum evaluated pairs before adjusting weights
_RECENCY_HALFLIFE = 30    # Days at which a sample's weight is halved


# ── Weights I/O ───────────────────────────────────────────────────────────────

def load_weights(horizon: str = "7d") -> dict:
    """
    Load current adaptive weights for a given horizon.
    Priority: Postgres weight_history → JSON file → hardcoded defaults.
    """
    defaults = DEFAULTS_7D if horizon == "7d" else DEFAULTS_30D
    prefix   = f"{horizon}:"

    # 1. Postgres
    try:
        history = store.get_weight_history(limit=50)
        # Filter rows tagged for this horizon
        tagged = [r for r in history if str(r.get("notes", "")).startswith(prefix)]
        if tagged:
            row = tagged[0]
            return {
                "technical":    row.get("technical_weight",  defaults["technical"]),
                "macro":        row.get("macro_weight",      defaults["macro"]),
                "sentiment":    row.get("sentiment_weight",  defaults["sentiment"]),
                "updated_at":   row.get("recorded_at"),
                "sample_count": row.get("sample_count", 0),
            }
    except Exception as e:
        logger.debug(f"load_weights ({horizon}) Postgres fallback: {e}")

    # 2. JSON file
    path = _WEIGHTS_7D_PATH if horizon == "7d" else _WEIGHTS_30D_PATH
    try:
        if path.exists():
            with open(path) as f:
                w = json.load(f)
            logger.debug(f"Weights ({horizon}) loaded from file: {w}")
            return w
    except Exception as e:
        logger.debug(f"load_weights ({horizon}) file fallback: {e}")

    # 3. Defaults
    return {**defaults, "updated_at": None, "sample_count": 0}


def save_weights(weights: dict, correlations: dict, sample_count: int,
                 horizon: str = "7d", notes: str = ""):
    """Persist updated weights to JSON and Postgres, tagged by horizon."""
    payload = {
        "technical":    round(weights["technical"],  4),
        "macro":        round(weights["macro"],       4),
        "sentiment":    round(weights["sentiment"],   4),
        "updated_at":   datetime.now(timezone.utc).isoformat(),
        "sample_count": sample_count,
    }
    path = _WEIGHTS_7D_PATH if horizon == "7d" else _WEIGHTS_30D_PATH
    try:
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logger.warning(f"save_weights ({horizon}) file error: {e}")

    full_notes = f"{horizon}: {notes}" if notes else f"{horizon}:"
    try:
        store.log_weight_update(weights, correlations, sample_count, full_notes)
    except Exception as e:
        logger.warning(f"save_weights ({horizon}) DB error: {e}")


# ── Math helpers ──────────────────────────────────────────────────────────────

def _weighted_pearson(xs: list, ys: list, ws: list) -> float:
    """
    Recency-weighted Pearson correlation.
    ws: per-sample weights (higher = more influence).
    """
    n = len(xs)
    if n < 3:
        return 0.0
    sw = sum(ws)
    if sw == 0:
        return 0.0
    mx = sum(w * x for w, x in zip(ws, xs)) / sw
    my = sum(w * y for w, y in zip(ws, ys)) / sw
    num  = sum(ws[i] * (xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx   = math.sqrt(sum(ws[i] * (xs[i] - mx) ** 2 for i in range(n)) / sw)
    dy   = math.sqrt(sum(ws[i] * (ys[i] - my) ** 2 for i in range(n)) / sw)
    if dx == 0 or dy == 0:
        return 0.0
    return (num / sw) / (dx * dy)


def _recency_weights(pairs: list, half_life_days: int = _RECENCY_HALFLIFE) -> list:
    """
    Exponential decay weights based on prediction age.
    A sample logged `half_life_days` ago gets weight 0.5; today gets weight 1.0.
    """
    now   = datetime.now(timezone.utc)
    decay = math.log(2) / half_life_days
    result = []
    for p in pairs:
        logged = p.get("logged_at")
        if logged is None:
            result.append(1.0)
            continue
        if isinstance(logged, str):
            try:
                logged = datetime.fromisoformat(logged.replace("Z", "+00:00"))
            except Exception:
                result.append(1.0)
                continue
        if logged.tzinfo is None:
            logged = logged.replace(tzinfo=timezone.utc)
        age_days = max((now - logged).total_seconds() / 86400, 0)
        result.append(math.exp(-decay * age_days))
    return result


def _softmax(d: dict) -> dict:
    """Normalise positive values in dict to sum to 1."""
    floored = {k: max(v, 0.01) for k, v in d.items()}
    total   = sum(floored.values())
    return {k: v / total for k, v in floored.items()}


# ── Outcome evaluation ────────────────────────────────────────────────────────

def evaluate_outcomes() -> int:
    """
    Fetch current prices and log outcomes for:
    - 7d horizon: predictions ≥7 days old with no 7d outcome yet
    - 30d horizon: predictions ≥30 days old with no 30d outcome yet
    One yfinance price fetch per unique ticker across both horizons.
    Returns total number of newly evaluated predictions.
    """
    pending_7d  = store.get_unevaluated_predictions(min_age_days=7,  horizon_days=7)
    pending_30d = store.get_unevaluated_predictions(min_age_days=30, horizon_days=30)

    # Group by ticker: {ticker: {7: [...], 30: [...]}}
    by_ticker: dict = {}
    for p in pending_7d:
        by_ticker.setdefault(p["ticker"], {7: [], 30: []})[7].append(p)
    for p in pending_30d:
        by_ticker.setdefault(p["ticker"], {7: [], 30: []})[30].append(p)

    if not by_ticker:
        logger.info("No pending predictions to evaluate.")
        return 0

    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not available — cannot evaluate outcomes.")
        return 0

    evaluated = 0
    for ticker, horizons in by_ticker.items():
        try:
            info = yf.Ticker(ticker).fast_info
            current_price = (
                getattr(info, "last_price", None)
                or getattr(info, "regular_market_price", None)
            )
            if current_price is None:
                continue
            current_price = float(current_price)
        except Exception as e:
            logger.warning(f"yfinance error for {ticker}: {e}")
            continue

        for horizon_days, preds in horizons.items():
            for pred in preds:
                past_price = pred.get("price_at_prediction")
                if not past_price or past_price <= 0:
                    continue
                actual_return = round(
                    ((current_price - past_price) / past_price) * 100, 4
                )
                try:
                    store.log_outcome(pred["id"], current_price, actual_return, horizon_days)
                    evaluated += 1
                except Exception as e:
                    logger.error(f"log_outcome failed (pred {pred['id']}, {horizon_days}d): {e}")

    logger.info(f"Evaluated {evaluated} predictions ({len(pending_7d)} pending 7d, {len(pending_30d)} pending 30d).")
    return evaluated


# ── Weight adjustment ─────────────────────────────────────────────────────────

def _adjust(horizon: str, horizon_days: int, defaults: dict) -> dict | None:
    """
    Core weight adjustment logic for a given horizon.
    Uses recency-weighted Pearson correlation between sub-scores and actual returns.
    """
    pairs = store.get_evaluated_pairs(limit=500)
    filtered = [p for p in pairs if p.get("horizon_days") == horizon_days]

    if len(filtered) < _MIN_SAMPLES:
        logger.info(f"[{horizon}] Insufficient data ({len(filtered)} < {_MIN_SAMPLES}) — weights unchanged.")
        return None

    weights   = _recency_weights(filtered)
    returns   = [p["actual_return"]    for p in filtered]
    tech_s    = [p["technical_score"]  for p in filtered]
    macro_s   = [p["macro_score"]      for p in filtered]
    sent_s    = [p["sentiment_score"]  for p in filtered]

    correlations = {
        "technical": _weighted_pearson(tech_s,  returns, weights),
        "macro":     _weighted_pearson(macro_s, returns, weights),
        "sentiment": _weighted_pearson(sent_s,  returns, weights),
    }
    logger.info(f"[{horizon}] Recency-weighted correlations with {horizon_days}d return: {correlations}")

    abs_corr = {k: abs(v) for k, v in correlations.items()}
    if max(abs_corr.values()) < 0.05:
        logger.info(f"[{horizon}] All correlations near zero — weights unchanged.")
        return None

    target  = _softmax(abs_corr)
    current = load_weights(horizon)
    new_weights = {
        k: current.get(k, defaults[k]) * (1 - _LEARNING_RATE) + target[k] * _LEARNING_RATE
        for k in defaults
    }
    new_weights = _softmax(new_weights)

    # Effective sample size (sum of recency weights, relative to flat weighting)
    effective_n = round(sum(weights) ** 2 / sum(w ** 2 for w in weights)) if weights else len(filtered)

    notes = (
        f"n={len(filtered)} (eff={effective_n}). "
        f"corr tech:{correlations['technical']:.3f} "
        f"macro:{correlations['macro']:.3f} "
        f"sent:{correlations['sentiment']:.3f}"
    )
    save_weights(new_weights, correlations, len(filtered), horizon=horizon, notes=notes)
    logger.info(f"[{horizon}] Weights updated: {new_weights}")
    return new_weights


def adjust_weights()    -> dict | None: return _adjust("7d",  7,  DEFAULTS_7D)
def adjust_weights_30d() -> dict | None: return _adjust("30d", 30, DEFAULTS_30D)


# ── Main cycle ────────────────────────────────────────────────────────────────

def run_self_improvement():
    """Full improvement cycle: evaluate outcomes → adjust 7d and 30d weights."""
    logger.info("Self-improvement cycle starting...")
    try:
        n_evaluated = evaluate_outcomes()
        w7d  = adjust_weights()
        w30d = adjust_weights_30d()
        logger.info(
            f"Cycle complete. Evaluated {n_evaluated} predictions. "
            f"7d weights: {w7d or 'unchanged'}. "
            f"30d weights: {w30d or 'unchanged'}."
        )
    except Exception as e:
        logger.error(f"Self-improvement cycle error: {e}", exc_info=True)
