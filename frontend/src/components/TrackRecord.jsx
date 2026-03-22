import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { motion } from 'framer-motion';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// ── Sub-components ────────────────────────────────────────────────────────────

function StatBox({ label, value, sub, color = 'text-gray-200' }) {
  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-4 flex flex-col gap-1">
      <span className="font-sans text-xs text-gray-500 uppercase tracking-wider">{label}</span>
      <span className={`font-mono-data text-2xl font-semibold tabular-nums ${color}`}>{value}</span>
      {sub && <span className="font-sans text-xs text-gray-600">{sub}</span>}
    </div>
  );
}
StatBox.propTypes = {
  label: PropTypes.string, value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  sub: PropTypes.string, color: PropTypes.string,
};

function CallCard({ label, ticker, returnVal, rank }) {
  const isPos = returnVal >= 0;
  return (
    <div className="flex items-center justify-between py-2 px-3 bg-gray-900/40 border border-gray-800 rounded-lg">
      <div>
        <span className="font-sans text-xs text-gray-500 uppercase tracking-wider mr-2">{label}</span>
        <span className="font-mono-data text-sm text-white">{ticker}</span>
        <span className="font-sans text-xs text-gray-600 ml-2">rank #{rank}</span>
      </div>
      <span className={`font-mono-data text-sm font-semibold ${isPos ? 'text-emerald-400' : 'text-red-400'}`}>
        {isPos ? '+' : ''}{returnVal.toFixed(2)}%
      </span>
    </div>
  );
}
CallCard.propTypes = {
  label: PropTypes.string, ticker: PropTypes.string,
  returnVal: PropTypes.number, rank: PropTypes.number,
};

function InFlightPick({ pick, index }) {
  const loggedDate = pick.logged_at ? new Date(pick.logged_at) : null;
  const ageHours = loggedDate ? Math.floor((Date.now() - loggedDate) / 3600000) : null;
  const ageDays  = ageHours != null ? Math.floor(ageHours / 24) : null;

  const rankColors = ['text-emerald-400', 'text-blue-400', 'text-amber-400'];
  const rankColor  = rankColors[index] || 'text-gray-400';

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.08 }}
      className="flex items-center justify-between py-2.5 px-3 bg-gray-900/40 border border-gray-800/60 rounded-lg"
    >
      <div className="flex items-center gap-3">
        <span className={`font-mono-data text-xs font-bold ${rankColor}`}>#{pick.rank}</span>
        <div>
          <span className="font-mono-data text-sm text-white">{pick.ticker}</span>
          {pick.price_at_prediction && (
            <span className="font-sans text-xs text-gray-600 ml-2">
              logged @ ${pick.price_at_prediction.toFixed(2)}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="font-mono-data text-xs text-gray-500 tabular-nums">
          {pick.composite_score != null ? `${Math.round(pick.composite_score)}/100` : '—'}
        </span>
        {ageDays != null && (
          <span className="font-sans text-xs text-gray-600">
            {ageDays === 0
              ? `${ageHours}h ago`
              : `${ageDays}d ago`}
          </span>
        )}
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
      </div>
    </motion.div>
  );
}
InFlightPick.propTypes = { pick: PropTypes.object, index: PropTypes.number };

function InFlightPanel({ status }) {
  const total       = status?.total_logged ?? 0;
  const daysLeft    = status?.days_until_first_eval;
  const horizon     = status?.eval_horizon_days ?? 7;
  const picks       = status?.top_picks_in_flight ?? [];

  // Progress toward first evaluation: 0 → horizon days
  const progressPct = daysLeft != null
    ? Math.round(((horizon - daysLeft) / horizon) * 100)
    : 0;

  const readyToEval = daysLeft === 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="bg-card rounded-xl p-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <p className="font-sans text-xs text-gray-500 uppercase tracking-widest flex items-center gap-2">
          <span>📡</span> Prediction Track Record
        </p>
        <span className="flex items-center gap-1.5 font-sans text-xs text-emerald-500">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          {total > 0 ? 'Tracking' : 'Waiting for data'}
        </span>
      </div>

      {total === 0 ? (
        /* No predictions logged yet */
        <div className="text-center py-6">
          <p className="font-sans text-sm text-gray-500">
            First forecast cycle will log predictions automatically.
          </p>
          <p className="font-sans text-xs text-gray-700 mt-1">
            Check back in a few minutes after the backend finishes its first run.
          </p>
        </div>
      ) : (
        <>
          {/* Big stat row */}
          <div className="grid grid-cols-3 gap-3 mb-5">
            <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-3 text-center">
              <p className="font-mono-data text-2xl font-bold text-white tabular-nums">{total}</p>
              <p className="font-sans text-xs text-gray-500 mt-0.5">predictions logged</p>
            </div>
            <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-3 text-center">
              <p className={`font-mono-data text-2xl font-bold tabular-nums ${readyToEval ? 'text-emerald-400' : 'text-amber-400'}`}>
                {readyToEval ? 'Ready' : `${daysLeft ?? '?'}d`}
              </p>
              <p className="font-sans text-xs text-gray-500 mt-0.5">
                {readyToEval ? 'to evaluate' : 'until first results'}
              </p>
            </div>
            <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-3 text-center">
              <p className="font-mono-data text-2xl font-bold text-blue-400 tabular-nums">7d</p>
              <p className="font-sans text-xs text-gray-500 mt-0.5">eval horizon</p>
            </div>
          </div>

          {/* Progress bar */}
          <div className="mb-5">
            <div className="flex justify-between items-center mb-1.5">
              <span className="font-sans text-xs text-gray-600">Progress to first evaluation</span>
              <span className="font-mono-data text-xs text-gray-500">{progressPct}%</span>
            </div>
            <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${progressPct}%` }}
                transition={{ duration: 1, ease: 'easeOut' }}
                className={`h-full rounded-full ${readyToEval ? 'bg-emerald-500' : 'bg-amber-500'}`}
              />
            </div>
            <p className="font-sans text-xs text-gray-700 mt-1.5">
              {readyToEval
                ? 'First batch ready — self-improvement job will evaluate outcomes in the next 24h cycle.'
                : `Predictions logged daily. Results appear after ${horizon} days when actual returns can be measured.`}
            </p>
          </div>

          {/* Current top picks in flight */}
          {picks.length > 0 && (
            <div>
              <p className="font-sans text-xs text-gray-600 uppercase tracking-wider mb-2">
                Current top picks being tracked
              </p>
              <div className="space-y-1.5">
                {picks.map((pick, i) => (
                  <InFlightPick key={pick.ticker} pick={pick} index={i} />
                ))}
              </div>
              <p className="font-sans text-xs text-gray-700 mt-3">
                In {daysLeft ?? horizon} days the model will check actual prices and score itself.
                Results appear here automatically.
              </p>
            </div>
          )}
        </>
      )}
    </motion.div>
  );
}
InFlightPanel.propTypes = { status: PropTypes.object };

// ── Main component ────────────────────────────────────────────────────────────

export default function TrackRecord() {
  const [data,   setData]   = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/track-record`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/predictions-status`).then(r => r.json()).catch(() => null),
    ]).then(([trackData, statusData]) => {
      setData(trackData);
      setStatus(statusData);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="bg-card rounded-xl p-6 animate-pulse space-y-3">
        <div className="h-4 bg-gray-700/60 rounded w-1/4" />
        <div className="grid grid-cols-3 gap-3">
          {[...Array(3)].map((_, i) => <div key={i} className="h-16 bg-gray-700/40 rounded-lg" />)}
        </div>
        <div className="h-2 bg-gray-700/40 rounded" />
        <div className="space-y-1.5">
          {[...Array(3)].map((_, i) => <div key={i} className="h-10 bg-gray-700/30 rounded-lg" />)}
        </div>
      </div>
    );
  }

  // No evaluated outcomes yet — show in-flight panel
  if (!data || !data.available) {
    return <InFlightPanel status={status} />;
  }

  // Evaluated outcomes exist — show full stats
  const topColor = data.avg_return_top3 >= 0 ? 'text-emerald-400' : 'text-red-400';
  const allColor = data.avg_return_all  >= 0 ? 'text-emerald-400' : 'text-red-400';

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="bg-card rounded-xl p-6"
    >
      <p className="font-sans text-xs text-gray-500 uppercase tracking-widest mb-4 flex items-center gap-2">
        <span>📊</span> Prediction Track Record
        <span className="font-mono-data text-gray-700 normal-case tracking-normal">
          · {data.sample_count} evaluated · {data.weeks_tracked} weeks
        </span>
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
        <StatBox
          label="Top 3 Avg Return"
          value={`${data.avg_return_top3 >= 0 ? '+' : ''}${data.avg_return_top3}%`}
          sub="7-day horizon"
          color={topColor}
        />
        <StatBox
          label="All Funds Avg"
          value={`${data.avg_return_all >= 0 ? '+' : ''}${data.avg_return_all}%`}
          sub="7-day horizon"
          color={allColor}
        />
        <StatBox
          label="Top 3 Positive Rate"
          value={`${data.top3_positive_rate}%`}
          sub="of calls were gains"
          color={data.top3_positive_rate >= 50 ? 'text-emerald-400' : 'text-red-400'}
        />
        <StatBox
          label="Beat Market Rate"
          value={`${data.top3_beat_market_rate}%`}
          sub="weeks top-3 outperformed"
          color={data.top3_beat_market_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}
        />
      </div>

      <div className="space-y-2">
        {data.best_call && (
          <CallCard
            label="Best call"
            ticker={data.best_call.ticker}
            returnVal={data.best_call.return}
            rank={data.best_call.rank_at_time}
          />
        )}
        {data.worst_call && (
          <CallCard
            label="Worst call"
            ticker={data.worst_call.ticker}
            returnVal={data.worst_call.return}
            rank={data.worst_call.rank_at_time}
          />
        )}
      </div>

      <p className="font-sans text-xs text-gray-700 mt-4">
        Past performance is not indicative of future results. Not financial advice.
      </p>
    </motion.div>
  );
}
