import React from 'react';
import PropTypes from 'prop-types';
import { motion } from 'framer-motion';

export const HORIZONS = [
  {
    key: '7d',
    label: '7-Day',
    short: '7D',
    description: 'Near-term momentum, RSI & sentiment',
    scoreKey: 'score_7d',
    rankKey: 'rank_7d',
    color: '#10b981',
  },
  {
    key: '30d',
    label: '30-Day',
    short: '30D',
    description: 'Macro environment & trend strength',
    scoreKey: 'score_30d',
    rankKey: 'rank_30d',
    color: '#6ee7b7',
  },
  {
    key: '1y',
    label: '1-Year',
    short: '1Y',
    description: 'Historical returns, Sharpe & drawdown',
    scoreKey: 'score_1y',
    rankKey: 'rank_1y',
    color: '#f59e0b',
  },
  {
    key: '5y',
    label: '5-Year',
    short: '5Y',
    description: 'Core holding quality, fees & total return',
    scoreKey: 'score_5y',
    rankKey: 'rank_5y',
    color: '#a78bfa',
  },
];

export function getHorizon(key) {
  return HORIZONS.find(h => h.key === key) || HORIZONS[0];
}

export default function HorizonSelector({ active, onChange }) {
  const activeHorizon = getHorizon(active);

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-3">
      {/* Tab pills */}
      <div
        className="flex items-center gap-1 p-1 rounded-xl border border-gray-800"
        style={{ backgroundColor: '#0d1120' }}
      >
        {HORIZONS.map((h) => {
          const isActive = active === h.key;
          return (
            <button
              key={h.key}
              onClick={() => onChange(h.key)}
              className="relative px-3 py-1.5 rounded-lg font-mono-data text-xs font-semibold transition-colors duration-150 focus:outline-none"
              style={{ color: isActive ? h.color : '#6b7280' }}
            >
              {isActive && (
                <motion.div
                  layoutId="horizon-pill"
                  className="absolute inset-0 rounded-lg"
                  style={{ backgroundColor: h.color + '18', border: `1px solid ${h.color}40` }}
                  transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                />
              )}
              <span className="relative z-10">{h.label}</span>
            </button>
          );
        })}
      </div>

      {/* Description */}
      <motion.p
        key={active}
        initial={{ opacity: 0, x: 6 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.2 }}
        className="font-sans text-xs"
        style={{ color: activeHorizon.color + 'cc' }}
      >
        {activeHorizon.description}
      </motion.p>
    </div>
  );
}

HorizonSelector.propTypes = {
  active: PropTypes.string.isRequired,
  onChange: PropTypes.func.isRequired,
};
