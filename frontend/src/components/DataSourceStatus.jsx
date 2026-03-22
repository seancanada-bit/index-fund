import React from 'react';
import PropTypes from 'prop-types';

const SOURCE_LABELS = {
  yfinance: 'yfinance',
  alpha_vantage: 'AlphaVantage',
  fred: 'FRED',
  news_api: 'NewsAPI',
  reddit: 'Reddit',
  claude_api: 'Claude',
};

const DOT_COLORS = {
  ok: 'bg-emerald-400',
  degraded: 'bg-amber-400',
  error: 'bg-red-400',
};

export default function DataSourceStatus({ status, lastUpdated }) {
  const sources = Object.entries(SOURCE_LABELS);
  const hasStatus = Object.keys(status || {}).length > 0;

  return (
    <div className="flex items-center gap-3 flex-wrap">
      {hasStatus && sources.map(([key, label]) => {
        const state = status[key] || 'ok';
        return (
          <div key={key} className="flex items-center gap-1" title={`${label}: ${state}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${DOT_COLORS[state] || 'bg-gray-500'}`} />
            <span className="font-mono-data text-xs text-gray-600 hidden sm:inline">{label}</span>
          </div>
        );
      })}
    </div>
  );
}

DataSourceStatus.propTypes = {
  status: PropTypes.object,
  lastUpdated: PropTypes.string,
};
