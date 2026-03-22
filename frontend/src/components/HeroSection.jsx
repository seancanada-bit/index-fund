import React from 'react';
import PropTypes from 'prop-types';
import { motion } from 'framer-motion';

function RefreshIcon({ spinning }) {
  return (
    <motion.svg
      animate={spinning ? { rotate: 360 } : { rotate: 0 }}
      transition={spinning ? { duration: 1, repeat: Infinity, ease: 'linear' } : {}}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
    </motion.svg>
  );
}
RefreshIcon.propTypes = { spinning: PropTypes.bool };

function formatDate(isoString) {
  if (!isoString) return null;
  try {
    const d = new Date(isoString);
    return d.toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
    });
  } catch {
    return null;
  }
}

export default function HeroSection({ onRefresh, refreshing, lastUpdated }) {
  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  });

  return (
    <section className="mx-auto max-w-7xl px-4 pt-12 pb-8">
      <motion.div
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="font-mono-data text-xs text-emerald-400 tracking-widest uppercase">
                AI-Powered Analysis
              </span>
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            </div>
            <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight tracking-tight">
              7-Day Index Fund
              <br />
              <span className="text-emerald-400">Outlook</span>
            </h1>
            <p className="mt-3 text-gray-400 font-sans text-sm max-w-xl">
              {today} &mdash; Rankings derived from technical indicators, macroeconomic signals, and AI sentiment analysis across news and social media.
            </p>
            <p className="mt-1 text-xs text-gray-600 font-sans">
              For informational purposes only. Not financial advice. Past performance does not guarantee future results.
            </p>
          </div>

          <div className="flex flex-col items-start sm:items-end gap-2 shrink-0">
            <button
              onClick={onRefresh}
              disabled={refreshing}
              className={`
                flex items-center gap-2 px-4 py-2 rounded-lg border font-sans text-sm font-medium
                transition-all duration-200
                ${refreshing
                  ? 'border-gray-700 text-gray-500 cursor-not-allowed'
                  : 'border-emerald-700 text-emerald-400 hover:bg-emerald-400/10 hover:border-emerald-500 cursor-pointer'
                }
              `}
            >
              <RefreshIcon spinning={refreshing} />
              {refreshing ? 'Refreshing…' : 'Refresh Data'}
            </button>

            {lastUpdated && (
              <p className="font-mono-data text-xs text-gray-600">
                Updated: {formatDate(lastUpdated)}
              </p>
            )}
          </div>
        </div>

        {/* Divider */}
        <div className="mt-8 flex items-center gap-3">
          <div className="flex-1 h-px bg-gradient-to-r from-emerald-800/50 via-gray-700 to-transparent" />
          <span className="font-mono-data text-xs text-gray-600">20 FUNDS TRACKED</span>
          <div className="flex-1 h-px bg-gradient-to-l from-emerald-800/50 via-gray-700 to-transparent" />
        </div>
      </motion.div>
    </section>
  );
}

HeroSection.propTypes = {
  onRefresh: PropTypes.func.isRequired,
  refreshing: PropTypes.bool,
  lastUpdated: PropTypes.string,
};
