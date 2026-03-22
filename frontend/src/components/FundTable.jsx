import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { motion, AnimatePresence } from 'framer-motion';
import PriceSparkline from './PriceSparkline';
import { getHorizon } from './HorizonSelector';
import InvestmentGrowth from './InvestmentGrowth';

const SORT_KEYS = {
  rank: (hz) => (a, b) => (a[getHorizon(hz).rankKey] ?? a.rank) - (b[getHorizon(hz).rankKey] ?? b.rank),
  ticker: () => (a, b) => a.ticker.localeCompare(b.ticker),
  score: (hz) => (a, b) => (b[getHorizon(hz).scoreKey] ?? b.composite_score) - (a[getHorizon(hz).scoreKey] ?? a.composite_score),
  sentiment: () => (a, b) => (b.sentiment?.final_sentiment_score ?? 0) - (a.sentiment?.final_sentiment_score ?? 0),
  return_5d: () => (a, b) => (b.return_5d ?? 0) - (a.return_5d ?? 0),
};

const SENTIMENT_PILL = {
  bullish: 'bg-emerald-500/15 text-emerald-400 border-emerald-700/40',
  bearish: 'bg-red-500/15 text-red-400 border-red-700/40',
  neutral: 'bg-amber-500/15 text-amber-400 border-amber-700/40',
};

const CONFIDENCE_PILL = {
  high: 'text-emerald-400',
  medium: 'text-amber-400',
  low: 'text-red-400',
};

function MiniBar({ value }) {
  const color = value >= 65 ? '#10b981' : value >= 40 ? '#f59e0b' : '#ef4444';
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono-data text-xs w-6 text-right" style={{ color }}>{Math.round(value)}</span>
      <div className="w-16 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${value}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}
MiniBar.propTypes = { value: PropTypes.number };

function SortIcon({ active, asc }) {
  if (!active) return <span className="text-gray-700 ml-1">↕</span>;
  return <span className="text-emerald-400 ml-1">{asc ? '↑' : '↓'}</span>;
}
SortIcon.propTypes = { active: PropTypes.bool, asc: PropTypes.bool };

function ExpandedRow({ fund }) {
  return (
    <tr>
      <td colSpan={7} className="px-4 pb-4 pt-0">
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          className="bg-navy-900 rounded-lg p-4 border border-gray-800"
          style={{ backgroundColor: '#0d1120' }}
        >
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            {/* Score breakdown */}
            <div>
              <p className="font-sans text-xs text-gray-500 uppercase tracking-wider mb-2">Score Breakdown</p>
              <div className="space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500 font-sans">Technical (40%)</span>
                  <span className="font-mono-data text-gray-300">{fund.technical?.technical_score?.toFixed(1)}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500 font-sans">Macro (30%)</span>
                  <span className="font-mono-data text-gray-300">{fund.macro?.macro_score?.toFixed(1)}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500 font-sans">Sentiment (30%)</span>
                  <span className="font-mono-data text-gray-300">{fund.sentiment?.final_sentiment_score?.toFixed(1)}</span>
                </div>
              </div>
            </div>

            {/* Technical signals */}
            <div>
              <p className="font-sans text-xs text-gray-500 uppercase tracking-wider mb-2">Technical Signals</p>
              <div className="space-y-1 text-xs font-mono-data text-gray-400">
                <div>RSI: <span className="text-gray-300">{fund.technical?.rsi?.toFixed(1)}</span></div>
                <div>MACD: <span className={fund.technical?.macd > 0 ? 'text-emerald-400' : 'text-red-400'}>
                  {fund.technical?.macd?.toFixed(3)}
                </span></div>
                <div>Vol Ratio: <span className="text-gray-300">{fund.technical?.volume_ratio?.toFixed(2)}x</span></div>
                <div>5d Mom: <span className={fund.technical?.momentum_5d >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                  {fund.technical?.momentum_5d >= 0 ? '+' : ''}{fund.technical?.momentum_5d?.toFixed(2)}%
                </span></div>
              </div>
            </div>

            {/* Sparkline + sentiment */}
            <div>
              <p className="font-sans text-xs text-gray-500 uppercase tracking-wider mb-2">20-Day Price</p>
              <PriceSparkline priceHistory={fund.price_history} sentiment={fund.sentiment?.sentiment} />
              {fund.sentiment?.rationale && (
                <p className="mt-2 font-sans text-xs text-gray-500 italic leading-relaxed line-clamp-3">
                  {fund.sentiment.rationale}
                </p>
              )}
            </div>
          </div>

          {fund.key_signals?.length > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-800">
              <p className="font-sans text-xs text-gray-500 uppercase tracking-wider mb-2">Key Signals</p>
              <div className="flex flex-wrap gap-2">
                {fund.key_signals.map((sig, i) => (
                  <span key={i} className={`text-xs px-2 py-0.5 rounded border font-sans ${
                    sig.direction === 'bullish'
                      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-800'
                      : sig.direction === 'bearish'
                      ? 'bg-red-500/10 text-red-400 border-red-800'
                      : 'bg-amber-500/10 text-amber-400 border-amber-800'
                  }`}>
                    {sig.direction === 'bullish' ? '↑' : sig.direction === 'bearish' ? '↓' : '—'} {sig.label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {fund.investment_scenarios && (
            <div className="mt-4 pt-4 border-t border-gray-800">
              <p className="font-sans text-xs text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
                <span>💰</span> Investment Calculator
              </p>
              <InvestmentGrowth fund={fund} />
            </div>
          )}
        </motion.div>
      </td>
    </tr>
  );
}
ExpandedRow.propTypes = { fund: PropTypes.object };

export default function FundTable({ funds, horizon = '7d' }) {
  const [sortKey, setSortKey] = useState('score');
  const [sortAsc, setSortAsc] = useState(false);
  const [expanded, setExpanded] = useState(null);

  const hz = getHorizon(horizon);

  const handleSort = (key) => {
    if (sortKey === key) setSortAsc(a => !a);
    else { setSortKey(key); setSortAsc(false); }
  };

  const sorted = [...funds].sort((a, b) => {
    const fn = (SORT_KEYS[sortKey] || SORT_KEYS.score)(horizon);
    const result = fn(a, b);
    return sortAsc ? -result : result;
  });

  const headers = [
    { key: 'rank',     label: '#',         className: 'w-10 text-center' },
    { key: 'ticker',   label: 'Ticker',    className: 'w-28' },
    { key: 'score',    label: `${hz.short} Score`, className: 'w-32' },
    { key: 'sentiment',label: 'Sentiment', className: 'w-28' },
    { key: 'return_5d',label: '5d Return', className: 'w-24 text-right' },
    { key: 'confidence',label: 'Conf.',    className: 'w-24 text-center' },
    { key: 'detail',   label: '',          className: 'w-8' },
  ];

  return (
    <div className="bg-card rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800">
              {headers.map(h => (
                <th
                  key={h.key}
                  onClick={() => h.key !== 'detail' && h.key !== 'confidence' && handleSort(h.key)}
                  className={`px-4 py-3 font-sans text-xs text-gray-500 uppercase tracking-wider text-left
                    ${h.className} ${h.key !== 'detail' && h.key !== 'confidence' ? 'cursor-pointer hover:text-gray-300 select-none' : ''}`}
                >
                  {h.label}
                  {h.key !== 'detail' && h.key !== 'confidence' && (
                    <SortIcon active={sortKey === h.key} asc={sortAsc} />
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((fund) => (
              <React.Fragment key={fund.ticker}>
                <tr
                  onClick={() => setExpanded(expanded === fund.ticker ? null : fund.ticker)}
                  className={`border-b border-gray-800/50 cursor-pointer transition-colors row-sweep
                    ${expanded === fund.ticker ? 'bg-gray-800/30' : 'hover:bg-gray-800/20'}`}
                >
                  {/* Rank */}
                  <td className="px-4 py-3 text-center">
                    <span className="font-mono-data text-xs text-gray-600">
                      {fund[hz.rankKey] ?? fund.rank}
                    </span>
                  </td>

                  {/* Ticker + name — left border colored by sentiment */}
                  <td
                    className="px-4 py-3"
                    style={{
                      borderLeft: `3px solid ${
                        fund.sentiment?.sentiment === 'bullish' ? 'rgba(16,185,129,0.6)'
                        : fund.sentiment?.sentiment === 'bearish' ? 'rgba(239,68,68,0.6)'
                        : 'rgba(245,158,11,0.4)'
                      }`
                    }}
                  >
                    <div className="font-mono-data text-sm font-medium text-white">{fund.ticker}</div>
                    <div className="font-sans text-xs text-gray-600 truncate max-w-[160px]">{fund.fund_name}</div>
                  </td>

                  {/* Horizon score */}
                  <td className="px-4 py-3">
                    <MiniBar value={fund[hz.scoreKey] ?? fund.composite_score} />
                  </td>

                  {/* Sentiment */}
                  <td className="px-4 py-3">
                    <span className={`font-sans text-xs px-2 py-0.5 rounded border capitalize ${
                      SENTIMENT_PILL[fund.sentiment?.sentiment] || SENTIMENT_PILL.neutral
                    }`}>
                      {fund.sentiment?.sentiment ?? 'neutral'}
                    </span>
                  </td>

                  {/* 5d Return */}
                  <td className="px-4 py-3 text-right">
                    {typeof fund.return_5d === 'number' ? (
                      <span className={`font-mono-data text-xs ${fund.return_5d >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {fund.return_5d >= 0 ? '+' : ''}{fund.return_5d.toFixed(2)}%
                      </span>
                    ) : (
                      <span className="text-gray-700 text-xs">—</span>
                    )}
                  </td>

                  {/* Confidence */}
                  <td className="px-4 py-3 text-center">
                    <span className={`font-sans text-xs capitalize ${CONFIDENCE_PILL[fund.confidence_level] || 'text-gray-500'}`}>
                      {fund.confidence_level}
                    </span>
                  </td>

                  {/* Expand toggle */}
                  <td className="px-4 py-3 text-right">
                    <span className="text-gray-600 text-xs">
                      {expanded === fund.ticker ? '▲' : '▼'}
                    </span>
                  </td>
                </tr>

                <AnimatePresence>
                  {expanded === fund.ticker && (
                    <ExpandedRow key={`${fund.ticker}-expanded`} fund={fund} />
                  )}
                </AnimatePresence>
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

FundTable.propTypes = {
  funds: PropTypes.arrayOf(PropTypes.object).isRequired,
  horizon: PropTypes.string,
};
