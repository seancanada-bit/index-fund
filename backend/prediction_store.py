"""
Prediction storage layer.
Primary: PostgreSQL via DATABASE_URL (Supabase, Render Postgres, etc.)
Fallback: In-memory store (persists within session, resets on restart)
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

# ── In-memory fallback ────────────────────────────────────────────────────────
_predictions: list[dict] = []
_outcomes: list[dict] = []
_weight_history: list[dict] = []
_next_id = 0

# ── DB circuit-breaker ────────────────────────────────────────────────────────
# After the first connection failure, skip all subsequent attempts for 5 minutes
# to avoid spamming logs and blocking the forecast build with 39 parallel timeouts.
_db_failed_at: Optional[datetime] = None
_DB_RETRY_INTERVAL = timedelta(minutes=5)


# ── DB helpers ────────────────────────────────────────────────────────────────
def _conn():
    global _db_failed_at
    if not DATABASE_URL:
        return None
    # Circuit-breaker: if we recently failed, skip immediately
    if _db_failed_at is not None:
        if datetime.now(timezone.utc) - _db_failed_at < _DB_RETRY_INTERVAL:
            return None
        # Retry window elapsed — try again
        _db_failed_at = None
    try:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
        _db_failed_at = None  # success — reset breaker
        return conn
    except Exception as e:
        if _db_failed_at is None:
            # Log only on the first failure; subsequent failures are silent
            logger.warning(f"DB connect failed: {e} — falling back to in-memory store (will retry in 5 min)")
        _db_failed_at = datetime.now(timezone.utc)
        return None


def _ensure_tables(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id          SERIAL PRIMARY KEY,
                logged_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ticker      VARCHAR(10) NOT NULL,
                rank        INTEGER NOT NULL,
                composite_score   FLOAT NOT NULL,
                technical_score   FLOAT NOT NULL,
                macro_score       FLOAT NOT NULL,
                sentiment_score   FLOAT NOT NULL,
                price_at_prediction FLOAT
            );
            CREATE TABLE IF NOT EXISTS outcomes (
                id              SERIAL PRIMARY KEY,
                prediction_id   INTEGER REFERENCES predictions(id),
                evaluated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                price_at_eval   FLOAT,
                actual_return   FLOAT,
                horizon_days    INTEGER DEFAULT 7
            );
            CREATE TABLE IF NOT EXISTS weight_history (
                id                   SERIAL PRIMARY KEY,
                recorded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                technical_weight     FLOAT NOT NULL,
                macro_weight         FLOAT NOT NULL,
                sentiment_weight     FLOAT NOT NULL,
                sample_count         INTEGER,
                technical_corr       FLOAT,
                macro_corr           FLOAT,
                sentiment_corr       FLOAT,
                notes                TEXT
            );
            CREATE TABLE IF NOT EXISTS alert_log (
                id          SERIAL PRIMARY KEY,
                ticker      VARCHAR(10) NOT NULL UNIQUE,
                alerted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        conn.commit()


# ── Public API ─────────────────────────────────────────────────────────────────
def log_predictions(fund_list: list[dict]):
    """Snapshot the current forecast rankings to storage."""
    global _next_id
    now = datetime.now(timezone.utc)

    db = _conn()
    if db:
        _ensure_tables(db)
        try:
            with db.cursor() as cur:
                for f in fund_list:
                    cur.execute("""
                        INSERT INTO predictions
                            (logged_at, ticker, rank, composite_score,
                             technical_score, macro_score, sentiment_score, price_at_prediction)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        now,
                        f.get("ticker"),
                        f.get("rank", 0),
                        f.get("composite_score", 50),
                        f.get("technical", {}).get("technical_score", 50),
                        f.get("macro", {}).get("macro_score", 50),
                        f.get("sentiment", {}).get("final_sentiment_score", 50),
                        f.get("current_price"),
                    ))
            db.commit()
            logger.info(f"Logged {len(fund_list)} predictions to Postgres.")
        except Exception as e:
            logger.error(f"log_predictions DB error: {e}")
            db.rollback()
        finally:
            db.close()
    else:
        for f in fund_list:
            _next_id += 1
            _predictions.append({
                "id": _next_id,
                "logged_at": now,
                "ticker": f.get("ticker"),
                "rank": f.get("rank", 0),
                "composite_score": f.get("composite_score", 50),
                "technical_score": f.get("technical", {}).get("technical_score", 50),
                "macro_score": f.get("macro", {}).get("macro_score", 50),
                "sentiment_score": f.get("sentiment", {}).get("final_sentiment_score", 50),
                "price_at_prediction": f.get("current_price"),
            })


def get_unevaluated_predictions(min_age_days: int = 7) -> list[dict]:
    """Return predictions old enough to evaluate that have no outcome yet."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)

    db = _conn()
    if db:
        _ensure_tables(db)
        try:
            with db.cursor() as cur:
                cur.execute("""
                    SELECT p.id, p.logged_at, p.ticker, p.rank,
                           p.technical_score, p.macro_score, p.sentiment_score,
                           p.price_at_prediction
                    FROM predictions p
                    LEFT JOIN outcomes o
                           ON o.prediction_id = p.id AND o.horizon_days = 7
                    WHERE p.logged_at < %s AND o.id IS NULL
                """, (cutoff,))
                cols = ["id","logged_at","ticker","rank",
                        "technical_score","macro_score","sentiment_score","price_at_prediction"]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"get_unevaluated DB error: {e}")
            return []
        finally:
            db.close()
    else:
        evaluated_ids = {o["prediction_id"] for o in _outcomes if o.get("horizon_days") == 7}
        return [p for p in _predictions
                if p["logged_at"] < cutoff and p["id"] not in evaluated_ids]


def log_outcome(prediction_id: int, price_at_eval: float, actual_return: float, horizon_days: int = 7):
    now = datetime.now(timezone.utc)
    db = _conn()
    if db:
        try:
            with db.cursor() as cur:
                cur.execute("""
                    INSERT INTO outcomes (prediction_id, evaluated_at, price_at_eval,
                                         actual_return, horizon_days)
                    VALUES (%s,%s,%s,%s,%s)
                """, (prediction_id, now, price_at_eval, actual_return, horizon_days))
            db.commit()
        except Exception as e:
            logger.error(f"log_outcome DB error: {e}")
            db.rollback()
        finally:
            db.close()
    else:
        _outcomes.append({
            "prediction_id": prediction_id,
            "evaluated_at": now,
            "price_at_eval": price_at_eval,
            "actual_return": actual_return,
            "horizon_days": horizon_days,
        })


def get_evaluated_pairs(limit: int = 500) -> list[dict]:
    """Return joined prediction + outcome rows for analysis."""
    db = _conn()
    if db:
        try:
            with db.cursor() as cur:
                cur.execute("""
                    SELECT p.ticker, p.rank, p.technical_score, p.macro_score,
                           p.sentiment_score, p.composite_score,
                           o.actual_return, o.horizon_days, p.logged_at
                    FROM predictions p
                    JOIN outcomes o ON o.prediction_id = p.id
                    WHERE o.actual_return IS NOT NULL
                    ORDER BY p.logged_at DESC
                    LIMIT %s
                """, (limit,))
                cols = ["ticker","rank","technical_score","macro_score","sentiment_score",
                        "composite_score","actual_return","horizon_days","logged_at"]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"get_evaluated_pairs DB error: {e}")
            return []
        finally:
            db.close()
    else:
        out_map = {o["prediction_id"]: o for o in _outcomes}
        result = []
        for p in _predictions:
            if p["id"] in out_map:
                o = out_map[p["id"]]
                result.append({**p, "actual_return": o["actual_return"], "horizon_days": o["horizon_days"]})
        return result[-limit:]


def log_weight_update(weights: dict, correlations: dict, sample_count: int, notes: str = ""):
    now = datetime.now(timezone.utc)
    db = _conn()
    if db:
        try:
            with db.cursor() as cur:
                cur.execute("""
                    INSERT INTO weight_history
                        (recorded_at, technical_weight, macro_weight, sentiment_weight,
                         sample_count, technical_corr, macro_corr, sentiment_corr, notes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    now,
                    weights.get("technical", 0.40),
                    weights.get("macro", 0.30),
                    weights.get("sentiment", 0.30),
                    sample_count,
                    correlations.get("technical"),
                    correlations.get("macro"),
                    correlations.get("sentiment"),
                    notes,
                ))
            db.commit()
        except Exception as e:
            logger.error(f"log_weight_update DB error: {e}")
            db.rollback()
        finally:
            db.close()
    else:
        _weight_history.append({
            "recorded_at": now,
            **weights,
            "sample_count": sample_count,
            **{f"{k}_corr": v for k, v in correlations.items()},
            "notes": notes,
        })


def get_weight_history(limit: int = 50) -> list[dict]:
    db = _conn()
    if db:
        try:
            with db.cursor() as cur:
                cur.execute("""
                    SELECT recorded_at, technical_weight, macro_weight, sentiment_weight,
                           sample_count, technical_corr, macro_corr, sentiment_corr, notes
                    FROM weight_history ORDER BY recorded_at DESC LIMIT %s
                """, (limit,))
                cols = ["recorded_at","technical_weight","macro_weight","sentiment_weight",
                        "sample_count","technical_corr","macro_corr","sentiment_corr","notes"]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                # Serialize datetime for JSON
                for row in rows:
                    if hasattr(row.get("recorded_at"), "isoformat"):
                        row["recorded_at"] = row["recorded_at"].isoformat()
                return rows
        except Exception as e:
            logger.error(f"get_weight_history DB error: {e}")
            return []
        finally:
            db.close()
    else:
        result = sorted(_weight_history, key=lambda x: x["recorded_at"], reverse=True)[:limit]
        out = []
        for r in result:
            row = {**r}
            if hasattr(row.get("recorded_at"), "isoformat"):
                row["recorded_at"] = row["recorded_at"].isoformat()
            out.append(row)
        return out


def get_track_record_stats() -> dict:
    """Aggregate accuracy metrics for the API and UI."""
    pairs = get_evaluated_pairs()
    seven_day = [p for p in pairs if p.get("horizon_days") == 7]

    base = {"available": False, "sample_count": len(seven_day)}
    if len(seven_day) < 5:
        return base

    top = [p for p in seven_day if p["rank"] <= 3]
    all_returns = [p["actual_return"] for p in seven_day]
    top_returns = [p["actual_return"] for p in top]

    avg_all = sum(all_returns) / len(all_returns)
    avg_top = sum(top_returns) / len(top_returns) if top_returns else 0
    top_positive_rate = sum(1 for r in top_returns if r > 0) / len(top_returns) * 100 if top_returns else 0

    best = max(seven_day, key=lambda p: p["actual_return"])
    worst = min(seven_day, key=lambda p: p["actual_return"])

    # Weekly buckets — group by week, check if top-3 outperformed average that week
    from collections import defaultdict
    weeks = defaultdict(list)
    for p in seven_day:
        la = p["logged_at"]
        week_key = la.strftime("%Y-W%U") if hasattr(la, "strftime") else str(la)[:8]
        weeks[week_key].append(p)

    weeks_top_beat = 0
    for week_preds in weeks.values():
        week_top = [p["actual_return"] for p in week_preds if p["rank"] <= 3]
        week_avg = sum(p["actual_return"] for p in week_preds) / len(week_preds)
        if week_top and sum(week_top) / len(week_top) > week_avg:
            weeks_top_beat += 1
    beat_rate = weeks_top_beat / len(weeks) * 100 if weeks else 0

    return {
        "available": True,
        "sample_count": len(seven_day),
        "weeks_tracked": len(weeks),
        "avg_return_top3": round(avg_top, 2),
        "avg_return_all": round(avg_all, 2),
        "top3_positive_rate": round(top_positive_rate, 1),
        "top3_beat_market_rate": round(beat_rate, 1),
        "best_call": {"ticker": best["ticker"], "return": round(best["actual_return"], 2),
                      "rank_at_time": best["rank"]},
        "worst_call": {"ticker": worst["ticker"], "return": round(worst["actual_return"], 2),
                       "rank_at_time": worst["rank"]},
    }


# ── Alert cooldown helpers ────────────────────────────────────────────────────
def get_alert_cooldown(ticker: str):
    """Return the datetime of the last alert for ticker, or None."""
    db = _conn()
    if db:
        _ensure_tables(db)
        try:
            with db.cursor() as cur:
                cur.execute(
                    "SELECT alerted_at FROM alert_log WHERE ticker = %s", (ticker,)
                )
                row = cur.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"get_alert_cooldown DB error: {e}")
            return None
        finally:
            db.close()
    return None


def set_alert_cooldown(ticker: str, alerted_at: datetime):
    """Upsert the alert timestamp for ticker."""
    db = _conn()
    if db:
        _ensure_tables(db)
        try:
            with db.cursor() as cur:
                cur.execute("""
                    INSERT INTO alert_log (ticker, alerted_at)
                    VALUES (%s, %s)
                    ON CONFLICT (ticker) DO UPDATE SET alerted_at = EXCLUDED.alerted_at
                """, (ticker, alerted_at))
            db.commit()
        except Exception as e:
            logger.error(f"set_alert_cooldown DB error: {e}")
            db.rollback()
        finally:
            db.close()


# ── In-flight predictions status ──────────────────────────────────────────────
def get_predictions_status() -> dict:
    """Return in-flight prediction stats for the UI progress panel."""
    now = datetime.now(timezone.utc)
    EVAL_HORIZON = 7  # days

    db = _conn()
    if db:
        _ensure_tables(db)
        try:
            with db.cursor() as cur:
                # Total predictions ever logged
                cur.execute("SELECT COUNT(*) FROM predictions")
                total = cur.fetchone()[0]

                # Oldest unevaluated prediction (determines days-to-first-result)
                cur.execute("""
                    SELECT MIN(p.logged_at) FROM predictions p
                    LEFT JOIN outcomes o ON o.prediction_id = p.id AND o.horizon_days = 7
                    WHERE o.id IS NULL
                """)
                oldest_row = cur.fetchone()
                oldest = oldest_row[0] if oldest_row else None

                # Most recent top-3 picks (one row per ticker, latest logged_at)
                cur.execute("""
                    SELECT DISTINCT ON (ticker)
                        ticker, rank, composite_score, price_at_prediction, logged_at
                    FROM predictions
                    WHERE rank <= 3
                    ORDER BY ticker, logged_at DESC
                """)
                cols = ["ticker", "rank", "composite_score", "price_at_prediction", "logged_at"]
                top_picks = []
                for row in cur.fetchall():
                    pick = dict(zip(cols, row))
                    if hasattr(pick.get("logged_at"), "isoformat"):
                        pick["logged_at"] = pick["logged_at"].isoformat()
                    top_picks.append(pick)

                # Days until first evaluation
                days_until = None
                if oldest:
                    if oldest.tzinfo is None:
                        oldest = oldest.replace(tzinfo=timezone.utc)
                    age_days = (now - oldest).days
                    days_until = max(0, EVAL_HORIZON - age_days)

                return {
                    "total_logged": total,
                    "oldest_prediction": oldest.isoformat() if oldest else None,
                    "days_until_first_eval": days_until,
                    "eval_horizon_days": EVAL_HORIZON,
                    "top_picks_in_flight": sorted(top_picks, key=lambda x: x["rank"]),
                }
        except Exception as e:
            logger.error(f"get_predictions_status DB error: {e}")
            return {"total_logged": 0, "days_until_first_eval": None, "top_picks_in_flight": []}
        finally:
            db.close()
    else:
        # In-memory fallback
        total = len(_predictions)
        oldest = min((p["logged_at"] for p in _predictions), default=None)
        days_until = None
        if oldest:
            age_days = (now - oldest).days if hasattr(oldest, "days") else 0
            days_until = max(0, EVAL_HORIZON - age_days)
        top_recent = sorted(
            [p for p in _predictions if p.get("rank", 99) <= 3],
            key=lambda x: x.get("logged_at", now), reverse=True
        )[:3]
        picks = []
        for p in top_recent:
            pick = {k: v for k, v in p.items()}
            if hasattr(pick.get("logged_at"), "isoformat"):
                pick["logged_at"] = pick["logged_at"].isoformat()
            picks.append(pick)
        return {
            "total_logged": total,
            "oldest_prediction": oldest.isoformat() if oldest and hasattr(oldest, "isoformat") else None,
            "days_until_first_eval": days_until,
            "eval_horizon_days": EVAL_HORIZON,
            "top_picks_in_flight": sorted(picks, key=lambda x: x.get("rank", 99)),
        }
