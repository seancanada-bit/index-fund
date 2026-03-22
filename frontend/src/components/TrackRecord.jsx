import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { motion } from 'framer-motion';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function StatBox({ label, value, sub, color = 'text-gray-200' }) {
  return (
    <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-4 flex flex-col gap-1">
      <span className="font-sans text-xs text-gray-500 uppercase tracking-wider">{label}</span>
      <span className={`font-mono-data text-2xl font-semibold tabular-nums ${color}`}>{value}</span>
      {sub && <span className="font-sans text-xs text-gray-600">{sub}</span>}
    </div>
  );
}
StatBox.propTypes = { label: PropTypes.string, value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]), sub: PropTypes.string, color: PropTypes.string };

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
CallCard.propTypes = { label: PropTypes.string, ticker: PropTypes.string, returnVal: PropTypes.number, rank: PropTypes.number };

export default function TrackRecord() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/track-record`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="bg-card rounded-xl p-6 animate-pulse space-y-3">
        <div className="h-4 bg-gray-700/60 rounded w-1/4" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => <div key={i} className="h-20 bg-gray-700/40 rounded-lg" />)}
        </div>
      </div>
    );
  }

  if (!data || !data.available) {
    return (
      <div className="bg-card rounded-xl p-6">
        <p className="font-sans text-xs text-gray-500 uppercase tracking-widest mb-3 flex items-center gap-2">
          <span>📊</span> Prediction Track Record
        </p>
        <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-6 text-center">
          <p className="font-sans text-sm text-gray-500">
            Track record builds automatically over time.
          </p>
          <p className="font-sans text-xs text-gray-600 mt-1">
            {data?.sample_count ?? 0} predictions logged — need 5 evaluated outcomes to display stats.
          </p>
        </div>
      </div>
    );
  }

  const topColor = data.avg_return_top3 >= 0 ? 'text-emerald-400' : 'text-red-400';
  const allColor = data.avg_return_all >= 0 ? 'text-emerald-400' : 'text-red-400';

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
          · {data.sample_count} evaluated predictions · {data.weeks_tracked} weeks
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
