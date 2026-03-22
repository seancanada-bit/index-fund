import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { motion } from 'framer-motion';

function AccuracyBar({ ticker, accuracy, windowsTested, rank }) {
  const color = accuracy >= 70 ? '#10b981' : accuracy >= 55 ? '#f59e0b' : '#ef4444';
  return (
    <div className="flex items-center gap-3">
      <span className="font-mono-data text-xs text-gray-500 w-4 text-right">{rank}</span>
      <span className="font-mono-data text-xs text-gray-300 w-10">{ticker}</span>
      <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
          initial={{ width: 0 }}
          animate={{ width: `${accuracy}%` }}
          transition={{ duration: 0.8, delay: rank * 0.03, ease: 'easeOut' }}
        />
      </div>
      <span className="font-mono-data text-xs w-10 text-right" style={{ color }}>
        {accuracy.toFixed(0)}%
      </span>
      <span className="font-sans text-xs text-gray-700 w-12 text-right">
        n={windowsTested}
      </span>
    </div>
  );
}
AccuracyBar.propTypes = {
  ticker: PropTypes.string,
  accuracy: PropTypes.number,
  windowsTested: PropTypes.number,
  rank: PropTypes.number,
};

export default function BacktestPanel({ funds }) {
  const [open, setOpen] = useState(false);

  const withBacktest = funds
    .filter(f => f.backtest?.accuracy != null)
    .sort((a, b) => b.backtest.accuracy - a.backtest.accuracy);

  if (withBacktest.length === 0) return null;

  const avgAccuracy = withBacktest.reduce((s, f) => s + f.backtest.accuracy, 0) / withBacktest.length;
  const best = withBacktest[0];
  const worst = withBacktest[withBacktest.length - 1];

  return (
    <div className="bg-card rounded-xl p-5">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between group"
      >
        <div className="flex items-center gap-3">
          <h2 className="font-sans text-sm font-semibold text-gray-400 uppercase tracking-widest group-hover:text-gray-300 transition-colors">
            Signal Backtest Accuracy
          </h2>
          <div className="flex items-center gap-2">
            <span className="font-mono-data text-xs px-2 py-0.5 rounded border border-amber-700/40 bg-amber-500/10 text-amber-400">
              ~{avgAccuracy.toFixed(0)}% avg
            </span>
            <span className="font-sans text-xs text-gray-600">
              Rolling 5-day momentum signal vs actual returns
            </span>
          </div>
        </div>
        <span className="text-gray-600 group-hover:text-gray-400 transition-colors">
          {open ? '▲' : '▼'}
        </span>
      </button>

      {open && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.25 }}
          className="overflow-hidden"
        >
          <div className="mt-4 space-y-4">
            {/* Summary stats */}
            <div className="grid grid-cols-3 gap-3">
              {[
                ['Avg Accuracy', `${avgAccuracy.toFixed(1)}%`, '#f59e0b'],
                [`Best: ${best.ticker}`, `${best.backtest.accuracy}%`, '#10b981'],
                [`Worst: ${worst.ticker}`, `${worst.backtest.accuracy}%`, '#ef4444'],
              ].map(([label, val, color]) => (
                <div key={label} className="bg-gray-800/40 rounded-lg p-3 text-center">
                  <p className="font-sans text-xs text-gray-500">{label}</p>
                  <p className="font-mono-data text-lg font-semibold mt-1" style={{ color }}>{val}</p>
                </div>
              ))}
            </div>

            {/* Accuracy bars */}
            <div className="space-y-2">
              {withBacktest.map((fund, i) => (
                <AccuracyBar
                  key={fund.ticker}
                  ticker={fund.ticker}
                  accuracy={fund.backtest.accuracy}
                  windowsTested={fund.backtest.windows_tested}
                  rank={i + 1}
                />
              ))}
            </div>

            <p className="font-sans text-xs text-gray-700 leading-relaxed border-t border-gray-800 pt-3">
              Backtested using rolling 5-trading-day windows over the last 60 days of price data.
              Signal: price above/below 10-day moving average at the start of each window.
              A 50% baseline is expected by chance — higher scores indicate the momentum signal
              is predictive for that fund historically. Past accuracy does not guarantee future results.
            </p>
          </div>
        </motion.div>
      )}
    </div>
  );
}

BacktestPanel.propTypes = {
  funds: PropTypes.arrayOf(PropTypes.object).isRequired,
};
