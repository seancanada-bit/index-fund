import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { motion, AnimatePresence } from 'framer-motion';
import ScoreGauge from './ScoreGauge';
import PriceSparkline from './PriceSparkline';
import CountUp from './CountUp';
import { getHorizon } from './HorizonSelector';
import InvestmentGrowth from './InvestmentGrowth';

const RANK_STYLES = {
  1: { badge: 'bg-yellow-500/20 text-yellow-400 border-yellow-600/40', label: '#1' },
  2: { badge: 'bg-gray-400/20 text-gray-300 border-gray-500/40', label: '#2' },
  3: { badge: 'bg-amber-700/20 text-amber-600 border-amber-700/40', label: '#3' },
};

const CONFIDENCE_STYLES = {
  high: 'bg-emerald-500/15 text-emerald-400 border-emerald-700/40',
  medium: 'bg-amber-500/15 text-amber-400 border-amber-700/40',
  low: 'bg-red-500/15 text-red-400 border-red-700/40',
};

const SENTIMENT_STYLES = {
  bullish: 'text-emerald-400',
  bearish: 'text-red-400',
  neutral: 'text-amber-400',
};

function signalColor(score) {
  if (score >= 65) return '#10b981';
  if (score >= 40) return '#f59e0b';
  return '#ef4444';
}

function fmt(v, decimals = 1, suffix = '') {
  if (v == null) return '—';
  return `${Number(v).toFixed(decimals)}${suffix}`;
}

/** T / M / S consensus cluster below gauge */
function ConsensusCluster({ technical, macro, sentiment }) {
  const items = [
    { label: 'T', score: technical?.technical_score ?? 50, title: `Technical: ${(technical?.technical_score ?? 50).toFixed(1)}` },
    { label: 'M', score: macro?.macro_score ?? 50,         title: `Macro: ${(macro?.macro_score ?? 50).toFixed(1)}` },
    { label: 'S', score: sentiment?.final_sentiment_score ?? 50, title: `Sentiment: ${(sentiment?.final_sentiment_score ?? 50).toFixed(1)}` },
  ];
  return (
    <div className="flex items-center justify-center gap-1.5 mt-2">
      {items.map(({ label, score, title }) => {
        const color = signalColor(score);
        return (
          <motion.div
            key={label}
            title={title}
            className="w-6 h-6 rounded flex items-center justify-center"
            style={{ backgroundColor: color + '22', border: `1px solid ${color}55` }}
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: 'spring', stiffness: 400, damping: 20, delay: 0.8 }}
          >
            <span className="font-mono-data font-bold" style={{ fontSize: 9, color }}>{label}</span>
          </motion.div>
        );
      })}
    </div>
  );
}
ConsensusCluster.propTypes = { technical: PropTypes.object, macro: PropTypes.object, sentiment: PropTypes.object };

/** Cross-horizon consensus badge */
function ConsensusBadge({ fund }) {
  const allTop = [fund.rank_7d, fund.rank_30d, fund.rank_1y, fund.rank_5y].every(r => r != null && r <= 7);
  if (!allTop) return null;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      className="flex items-center gap-1.5 px-2 py-1 rounded border"
      style={{ backgroundColor: 'rgba(167,139,250,0.12)', borderColor: 'rgba(167,139,250,0.4)' }}
    >
      <span style={{ color: '#a78bfa', fontSize: 11 }}>★</span>
      <span className="font-sans text-xs font-semibold" style={{ color: '#a78bfa' }}>All Horizons</span>
    </motion.div>
  );
}
ConsensusBadge.propTypes = { fund: PropTypes.object.isRequired };

function SubScoreBar({ label, value }) {
  const color = signalColor(value);
  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <span className="font-sans text-xs text-gray-500">{label}</span>
        <span className="font-mono-data text-xs" style={{ color }}>
          <CountUp value={Math.round(value)} delay={400} />
        </span>
      </div>
      <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
        <motion.div className="h-full rounded-full" style={{ backgroundColor: color }}
          initial={{ width: 0 }} animate={{ width: `${value}%` }}
          transition={{ duration: 0.8, ease: 'easeOut', delay: 0.4 }} />
      </div>
    </div>
  );
}
SubScoreBar.propTypes = { label: PropTypes.string, value: PropTypes.number };

function SignalIcon({ direction }) {
  if (direction === 'bullish') return <span className="text-emerald-400">↑</span>;
  if (direction === 'bearish') return <span className="text-red-400">↓</span>;
  return <span className="text-amber-400">—</span>;
}
SignalIcon.propTypes = { direction: PropTypes.string };

function Section({ title, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-gray-800">
      <button onClick={() => setOpen(v => !v)}
        className="w-full flex justify-between items-center py-2.5 text-left group">
        <span className="font-sans text-xs text-gray-500 group-hover:text-gray-300 transition-colors uppercase tracking-wider">{title}</span>
        <span className="text-gray-600 group-hover:text-gray-400 transition-colors text-xs">{open ? '▲' : '▼'}</span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
            <div className="pb-3">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
Section.propTypes = { title: PropTypes.string, children: PropTypes.node, defaultOpen: PropTypes.bool };

/** Horizon-specific metric rows */
function HorizonMetrics({ fund, horizonKey }) {
  const lm = fund.long_metrics || {};

  const rows7d = [
    { label: 'RSI',        value: fmt(fund.technical?.rsi, 1) },
    { label: 'MACD',       value: fund.technical?.macd != null ? (fund.technical.macd >= 0 ? '▲ positive' : '▼ negative') : '—',
      color: fund.technical?.macd >= 0 ? '#10b981' : '#ef4444' },
    { label: '5D Return',  value: fund.return_5d != null ? `${fund.return_5d >= 0 ? '+' : ''}${fund.return_5d.toFixed(2)}%` : '—',
      color: fund.return_5d >= 0 ? '#10b981' : '#ef4444' },
    { label: 'Sentiment',  value: fund.sentiment?.sentiment ?? '—' },
  ];

  const rows30d = [
    { label: '1M Return',   value: fund.return_1m != null ? `${fund.return_1m >= 0 ? '+' : ''}${fund.return_1m.toFixed(2)}%` : '—',
      color: fund.return_1m >= 0 ? '#10b981' : '#ef4444' },
    { label: 'Above SMA50', value: fund.technical?.price_above_sma50 ? 'Yes ✓' : 'No ✗',
      color: fund.technical?.price_above_sma50 ? '#10b981' : '#ef4444' },
    { label: 'VIX',         value: fmt(fund.macro?.vix, 1) },
    { label: 'Macro Score', value: fmt(fund.macro?.macro_score, 1) },
  ];

  const rows1y = [
    { label: '1Y CAGR',      value: fmt(lm.cagr_1y, 1, '%'), color: lm.cagr_1y >= 0 ? '#10b981' : '#ef4444' },
    { label: 'Sharpe 1Y',    value: fmt(lm.sharpe_1y, 2) },
    { label: 'Max DD 1Y',    value: fmt(lm.max_drawdown_1y, 1, '%'), color: '#f87171' },
    { label: 'Expense Ratio',value: lm.expense_ratio != null ? `${(lm.expense_ratio * 100).toFixed(2)}%` : '—' },
  ];

  const rows5y = [
    { label: '5Y CAGR',      value: fmt(lm.cagr_5y, 1, '%'), color: lm.cagr_5y >= 0 ? '#10b981' : '#ef4444' },
    { label: 'Sharpe 5Y',    value: fmt(lm.sharpe_5y, 2) },
    { label: 'Max DD 5Y',    value: fmt(lm.max_drawdown_5y, 1, '%'), color: '#f87171' },
    { label: 'Expense Ratio',value: lm.expense_ratio != null ? `${(lm.expense_ratio * 100).toFixed(2)}%` : '—' },
  ];

  const rowMap = { '7d': rows7d, '30d': rows30d, '1y': rows1y, '5y': rows5y };
  const rows = rowMap[horizonKey] || rows7d;

  return (
    <motion.div
      key={horizonKey}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="grid grid-cols-2 gap-x-4 gap-y-1.5"
    >
      {rows.map(({ label, value, color }) => (
        <div key={label}>
          <span className="font-sans text-xs text-gray-600">{label} </span>
          <span className="font-mono-data text-xs" style={{ color: color || '#d1d5db' }}>{value}</span>
        </div>
      ))}
    </motion.div>
  );
}
HorizonMetrics.propTypes = { fund: PropTypes.object.isRequired, horizonKey: PropTypes.string.isRequired };

export default function ForecastCard({ fund, isHero = false, horizon = '7d' }) {
  const {
    fund_name, composite_score, confidence_level,
    technical, macro, sentiment, price_history, ai_rationale, key_signals,
    current_price, return_5d,
  } = fund;

  const hz = getHorizon(horizon);
  const activeScore = fund[hz.scoreKey] ?? composite_score;
  const activeRank  = fund[hz.rankKey]  ?? fund.rank;

  const rankStyleKey = activeRank <= 3 ? activeRank : null;
  const rankStyle = rankStyleKey ? RANK_STYLES[rankStyleKey] : null;

  const confStyle = CONFIDENCE_STYLES[confidence_level] || CONFIDENCE_STYLES.low;
  const sentColor = SENTIMENT_STYLES[sentiment?.sentiment] || 'text-gray-400';
  const gaugeSize = isHero ? 120 : 100;

  const cardGlow = isHero ? 'glow-hero'
    : activeScore >= 65 ? 'glow-emerald'
    : activeScore < 40  ? 'glow-red'
    : '';

  return (
    <div
      className={`bg-card rounded-xl p-5 flex flex-col gap-4 ${cardGlow} transition-all`}
      style={isHero ? { borderColor: 'rgba(16,185,129,0.3)' } : {}}
    >
      {/* Hero crown */}
      {isHero && (
        <div className="flex items-center gap-2 -mb-1">
          <span className="font-mono-data text-xs text-emerald-400 tracking-widest uppercase">★ Top Pick</span>
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        </div>
      )}

      {/* Header row */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          {rankStyle ? (
            <span className={`font-mono-data text-xs font-semibold px-2 py-0.5 rounded border ${rankStyle.badge}`}>
              {hz.short} #{activeRank}
            </span>
          ) : (
            <span className="font-mono-data text-xs text-gray-600 px-2 py-0.5 rounded border border-gray-800">
              {hz.short} #{activeRank}
            </span>
          )}
          <ConsensusBadge fund={fund} />
        </div>
        <span className={`font-sans text-xs px-2 py-0.5 rounded border capitalize ${confStyle}`}>
          {confidence_level} confidence
        </span>
      </div>

      {/* Ticker + name */}
      <div>
        <div className="flex items-baseline gap-3">
          <h3 className="font-mono-data font-semibold text-white" style={{ fontSize: isHero ? '2rem' : '1.5rem' }}>
            {fund.ticker}
          </h3>
          {current_price && (
            <span className="font-mono-data text-sm text-gray-400">${current_price.toFixed(2)}</span>
          )}
          {typeof return_5d === 'number' && (
            <span className={`font-mono-data text-xs ${return_5d >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {return_5d >= 0 ? '+' : ''}{return_5d.toFixed(2)}%
            </span>
          )}
        </div>
        <p className="font-sans text-xs text-gray-500 mt-0.5 truncate">{fund_name}</p>
      </div>

      {/* Gauge */}
      <div className="flex flex-col items-center">
        <ScoreGauge score={activeScore} size={gaugeSize} strokeWidth={isHero ? 10 : 8} />
      </div>

      {/* Sub-score bars (always technical/macro/sentiment for context) */}
      <div className="space-y-2.5">
        <SubScoreBar label="Technical" value={technical?.technical_score ?? 50} />
        <SubScoreBar label="Macro"     value={macro?.macro_score ?? 50} />
        <SubScoreBar label="Sentiment" value={sentiment?.final_sentiment_score ?? 50} />
      </div>

      {/* Horizon-specific metrics */}
      <HorizonMetrics fund={fund} horizonKey={horizon} />

      {/* Sentiment + source tag */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-sans text-xs text-gray-600">Sentiment:</span>
        <span className={`font-mono-data text-xs capitalize font-medium ${sentColor}`}>
          {sentiment?.sentiment ?? 'neutral'}
        </span>
        {sentiment?.data_source && (
          <span className="font-mono-data text-xs text-gray-700 border border-gray-800 px-1.5 py-0.5 rounded">
            {sentiment.data_source.includes('finbert') ? '🧠 FinBERT' : sentiment.data_source}
          </span>
        )}
      </div>

      {/* Fund stats row */}
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {fund.dividend_yield != null && (
          <div>
            <span className="font-sans text-xs text-gray-600">Yield </span>
            <span className="font-mono-data text-xs text-gray-300">{(fund.dividend_yield * 100).toFixed(2)}%</span>
          </div>
        )}
        {fund.beta != null && (
          <div>
            <span className="font-sans text-xs text-gray-600">Beta </span>
            <span className="font-mono-data text-xs text-gray-300">{fund.beta.toFixed(2)}</span>
          </div>
        )}
        {fund.technical?.week_52_position != null && (
          <div>
            <span className="font-sans text-xs text-gray-600">52wk </span>
            <span className="font-mono-data text-xs text-gray-300">{(fund.technical.week_52_position * 100).toFixed(0)}th %ile</span>
          </div>
        )}
        {fund.backtest?.accuracy != null && (
          <div>
            <span className="font-sans text-xs text-gray-600">Backtest </span>
            <span className={`font-mono-data text-xs ${fund.backtest.accuracy >= 65 ? 'text-emerald-400' : fund.backtest.accuracy >= 50 ? 'text-amber-400' : 'text-red-400'}`}>
              {fund.backtest.accuracy}%
            </span>
          </div>
        )}
        {fund.google_trends_score != null && (
          <div>
            <span className="font-sans text-xs text-gray-600">Trends </span>
            <span className="font-mono-data text-xs text-gray-300">
              {fund.google_trends_score.toFixed(0)}
              {fund.google_trends_direction === 1 ? ' ↑' : fund.google_trends_direction === -1 ? ' ↓' : ''}
            </span>
          </div>
        )}
      </div>

      {/* Sparkline */}
      <PriceSparkline priceHistory={price_history} sentiment={sentiment?.sentiment} />

      {/* Expandable sections */}
      <div className="space-y-0">
        {ai_rationale && (
          <Section title="AI Outlook" defaultOpen={isHero || fund.rank === 1}>
            <p className="font-sans text-xs text-gray-400 leading-relaxed whitespace-pre-line">{ai_rationale}</p>
          </Section>
        )}
        {key_signals?.length > 0 && (
          <Section title="Key Signals" defaultOpen={isHero}>
            <ul className="space-y-1.5">
              {key_signals.map((sig, i) => (
                <li key={i} className="flex items-start gap-2">
                  <SignalIcon direction={sig.direction} />
                  <span className="font-sans text-xs text-gray-400">{sig.label}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}
        {sentiment?.risk_flags?.length > 0 && (
          <Section title="Risk Flags">
            <ul className="space-y-1.5">
              {sentiment.risk_flags.map((flag, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-amber-500">⚠</span>
                  <span className="font-sans text-xs text-amber-400/80">{flag}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}
        {fund.investment_scenarios && (
          <Section title="💰 Investment Calculator">
            <InvestmentGrowth fund={fund} compact={!isHero} />
          </Section>
        )}
      </div>
    </div>
  );
}

ForecastCard.propTypes = {
  isHero: PropTypes.bool,
  horizon: PropTypes.string,
  fund: PropTypes.shape({
    ticker: PropTypes.string,
    fund_name: PropTypes.string,
    composite_score: PropTypes.number,
    confidence_level: PropTypes.string,
    rank: PropTypes.number,
    score_7d: PropTypes.number,
    score_30d: PropTypes.number,
    score_1y: PropTypes.number,
    score_5y: PropTypes.number,
    rank_7d: PropTypes.number,
    rank_30d: PropTypes.number,
    rank_1y: PropTypes.number,
    rank_5y: PropTypes.number,
    fundamental_score_1y: PropTypes.number,
    fundamental_score_5y: PropTypes.number,
    investment_scenarios: PropTypes.object,
    technical: PropTypes.object,
    macro: PropTypes.object,
    sentiment: PropTypes.object,
    long_metrics: PropTypes.object,
    price_history: PropTypes.array,
    ai_rationale: PropTypes.string,
    key_signals: PropTypes.array,
    current_price: PropTypes.number,
    return_5d: PropTypes.number,
    return_1m: PropTypes.number,
    dividend_yield: PropTypes.number,
    beta: PropTypes.number,
    pe_ratio: PropTypes.number,
    expense_ratio: PropTypes.number,
    google_trends_score: PropTypes.number,
    google_trends_direction: PropTypes.number,
    backtest: PropTypes.object,
  }).isRequired,
};
