import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import PropTypes from 'prop-types';

const DATA_BASE = process.env.PUBLIC_URL || '';

const COMPONENT_COLOR = {
  technical: '#10b981',
  macro:     '#3b82f6',
  sentiment: '#f59e0b',
};

function WeightBar({ label, value, color }) {
  const pct = Math.round(value * 100);
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="font-sans text-xs text-gray-400 capitalize">{label}</span>
        <span className="font-mono-data text-sm font-semibold tabular-nums" style={{ color }}>
          {pct}%
        </span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
        />
      </div>
    </div>
  );
}
WeightBar.propTypes = { label: PropTypes.string, value: PropTypes.number, color: PropTypes.string };

function HistoryRow({ row, index }) {
  const date = row.recorded_at
    ? new Date(row.recorded_at).toLocaleDateString('en', { month: 'short', day: 'numeric', year: '2-digit' })
    : '—';
  return (
    <motion.tr
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.04 }}
      className="border-b border-gray-800/50"
    >
      <td className="py-2 px-3 font-sans text-xs text-gray-500">{date}</td>
      <td className="py-2 px-3 font-mono-data text-xs text-emerald-400">{Math.round((row.technical_weight ?? 0) * 100)}%</td>
      <td className="py-2 px-3 font-mono-data text-xs text-blue-400">{Math.round((row.macro_weight ?? 0) * 100)}%</td>
      <td className="py-2 px-3 font-mono-data text-xs text-amber-400">{Math.round((row.sentiment_weight ?? 0) * 100)}%</td>
      <td className="py-2 px-3 font-sans text-xs text-gray-600 tabular-nums">{row.sample_count ?? '—'}</td>
    </motion.tr>
  );
}
HistoryRow.propTypes = { row: PropTypes.object, index: PropTypes.number };

export default function ModelInsights() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${DATA_BASE}/model-insights.json`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="bg-card rounded-xl p-6 animate-pulse space-y-3">
        <div className="h-4 bg-gray-700/60 rounded w-1/3" />
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => <div key={i} className="h-6 bg-gray-700/40 rounded" />)}
        </div>
      </div>
    );
  }

  const weights = data?.current_weights;
  const history = data?.weight_history ?? [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="bg-card rounded-xl p-6"
    >
      <p className="font-sans text-xs text-gray-500 uppercase tracking-widest mb-4 flex items-center gap-2">
        <span>🧠</span> Model Insights
        <span className="font-sans normal-case tracking-normal text-gray-700">
          · self-adjusting 7-day weights
        </span>
      </p>

      {/* Current weights */}
      <div className="mb-6">
        <p className="font-sans text-xs text-gray-600 mb-3">Current scoring weights (7-day horizon)</p>
        {weights ? (
          <div className="space-y-3">
            {['technical', 'macro', 'sentiment'].map(key => (
              <WeightBar
                key={key}
                label={key}
                value={weights[key] ?? 0}
                color={COMPONENT_COLOR[key]}
              />
            ))}
            {weights.sample_count > 0 && (
              <p className="font-sans text-xs text-gray-700 mt-2">
                Calibrated on {weights.sample_count} evaluated predictions.
                {weights.updated_at && ` Last adjusted ${new Date(weights.updated_at).toLocaleDateString()}.`}
              </p>
            )}
            {(!weights.sample_count || weights.sample_count === 0) && (
              <p className="font-sans text-xs text-gray-700 mt-2">
                Using default weights — will self-adjust once 10+ outcomes are evaluated.
              </p>
            )}
          </div>
        ) : (
          <p className="font-sans text-xs text-gray-600">Weights not yet available.</p>
        )}
      </div>

      {/* Weight history table */}
      {history.length > 0 && (
        <div>
          <p className="font-sans text-xs text-gray-600 mb-2">Weight adjustment history</p>
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="py-2 px-3 text-left font-sans text-xs text-gray-600">Date</th>
                  <th className="py-2 px-3 text-left font-sans text-xs text-emerald-700">Technical</th>
                  <th className="py-2 px-3 text-left font-sans text-xs text-blue-700">Macro</th>
                  <th className="py-2 px-3 text-left font-sans text-xs text-amber-700">Sentiment</th>
                  <th className="py-2 px-3 text-left font-sans text-xs text-gray-600">Samples</th>
                </tr>
              </thead>
              <tbody>
                {history.map((row, i) => (
                  <HistoryRow key={i} row={row} index={i} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {history.length === 0 && (
        <p className="font-sans text-xs text-gray-700">
          Weight history will appear here after the first self-adjustment cycle (runs daily once 10+ predictions are evaluated).
        </p>
      )}
    </motion.div>
  );
}
