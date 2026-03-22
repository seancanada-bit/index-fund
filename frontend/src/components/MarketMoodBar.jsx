import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { motion } from 'framer-motion';

const SOURCE_LABELS = {
  yfinance: 'YF',
  alpha_vantage: 'AV',
  fred: 'FRED',
  news_api: 'News',
  reddit: 'Reddit',
  claude_api: 'Claude',
  finbert: 'FinBERT',
  fear_greed: 'F&G',
  google_trends: 'Trends',
};

function LiveClock() {
  const [time, setTime] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const hh = String(time.getUTCHours()).padStart(2, '0');
  const mm = String(time.getUTCMinutes()).padStart(2, '0');
  const ss = String(time.getUTCSeconds()).padStart(2, '0');
  return (
    <div className="flex items-center gap-1.5">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />
      <span className="font-mono-data text-xs text-gray-400">{hh}:{mm}:{ss} UTC</span>
    </div>
  );
}

function FearGreedBadge({ fearGreed }) {
  if (!fearGreed?.available) return null;
  const score = fearGreed.score;
  const rating = fearGreed.rating?.replace(/_/g, ' ') ?? 'neutral';
  const color =
    score <= 25 ? '#ef4444' :
    score <= 45 ? '#f87171' :
    score <= 55 ? '#f59e0b' :
    score <= 75 ? '#6ee7b7' :
    '#10b981';

  return (
    <div className="flex items-center gap-2 px-3 py-1 rounded-md border"
      style={{ borderColor: color + '40', backgroundColor: color + '0d' }}>
      <span className="font-sans text-xs text-gray-500 hidden sm:block">F&amp;G</span>
      <span className="font-mono-data text-sm font-semibold" style={{ color }}>
        {score.toFixed(0)}
      </span>
      <span className="font-sans text-xs capitalize hidden md:block" style={{ color: color + 'cc' }}>
        {rating}
      </span>
      <div className="w-16 h-1 bg-gray-800 rounded-full overflow-hidden hidden sm:block">
        <motion.div
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
          initial={{ width: 0 }}
          animate={{ width: `${score}%` }}
          transition={{ duration: 1.2, ease: 'easeOut', delay: 0.5 }}
        />
      </div>
    </div>
  );
}
FearGreedBadge.propTypes = { fearGreed: PropTypes.object };

function SourceDots({ status }) {
  const entries = Object.entries(status || {});
  if (entries.length === 0) return null;
  return (
    <div className="hidden lg:flex items-center gap-1.5">
      {entries.map(([key, val]) => {
        const color = val === 'ok' ? '#10b981' : val === 'degraded' ? '#f59e0b' : '#ef4444';
        return (
          <div key={key} className="flex items-center gap-1" title={`${key}: ${val}`}>
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
            <span className="font-mono-data text-gray-600" style={{ fontSize: 9 }}>
              {SOURCE_LABELS[key] ?? key}
            </span>
          </div>
        );
      })}
    </div>
  );
}
SourceDots.propTypes = { status: PropTypes.object };

function formatUpdated(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZoneName: 'short' });
  } catch { return null; }
}

export default function MarketMoodBar({ status, lastUpdated, fearGreed, onRefresh, refreshing }) {
  const updated = formatUpdated(lastUpdated);

  return (
    <div className="border-b border-gray-800/80 sticky top-0 z-50 backdrop-blur-sm"
      style={{ backgroundColor: 'rgba(10,14,26,0.92)' }}>
      <div className="mx-auto max-w-7xl px-4 py-2 flex items-center gap-3 min-h-[40px]">
        {/* Left: brand */}
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-mono-data text-xs font-semibold text-gray-400 tracking-widest uppercase">
            IFF
          </span>
          <span className="text-gray-700 hidden sm:block">|</span>
          <span className="font-mono-data text-xs text-gray-600 hidden sm:block">v2.0</span>
        </div>

        <div className="w-px h-4 bg-gray-800 hidden sm:block" />

        {/* Clock */}
        <LiveClock />

        {/* Fear & Greed */}
        {fearGreed?.available && (
          <>
            <div className="w-px h-4 bg-gray-800" />
            <FearGreedBadge fearGreed={fearGreed} />
          </>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Source dots */}
        <SourceDots status={status} />

        {updated && (
          <div className="hidden md:flex items-center gap-1.5">
            <div className="w-px h-4 bg-gray-800" />
            <span className="font-mono-data text-xs text-gray-600">
              {updated}
            </span>
          </div>
        )}

        {/* Refresh */}
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded border text-xs font-sans transition-all
            ${refreshing
              ? 'border-gray-800 text-gray-600 cursor-not-allowed'
              : 'border-gray-700 text-gray-400 hover:border-emerald-700 hover:text-emerald-400 cursor-pointer'
            }`}
        >
          <motion.span
            animate={refreshing ? { rotate: 360 } : { rotate: 0 }}
            transition={refreshing ? { duration: 1, repeat: Infinity, ease: 'linear' } : {}}
            style={{ display: 'inline-block' }}
          >
            ↻
          </motion.span>
          <span className="hidden sm:block">{refreshing ? 'Updating' : 'Refresh'}</span>
        </button>
      </div>
    </div>
  );
}

MarketMoodBar.propTypes = {
  status: PropTypes.object,
  lastUpdated: PropTypes.string,
  fearGreed: PropTypes.object,
  onRefresh: PropTypes.func.isRequired,
  refreshing: PropTypes.bool,
};
