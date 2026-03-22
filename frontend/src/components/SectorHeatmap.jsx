import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { motion } from 'framer-motion';
import { getHorizon } from './HorizonSelector';

const CATEGORIES = {
  'Equity Broad': ['SPY', 'VTI', 'VOO', 'DIA', 'SCHD', 'VIG'],
  'Growth / Tech': ['QQQ', 'ARKK', 'XLK'],
  'Small Cap': ['IWM'],
  'International': ['EFA', 'EEM'],
  'Fixed Income': ['TLT', 'BND'],
  'Real Estate': ['VNQ'],
  'Commodities': ['GLD', 'IAU', 'XLE', 'PDBC'],
  'Financials': ['XLF'],
};

function scoreToColor(score) {
  if (score >= 72) return { bg: 'rgba(16,185,129,0.22)', border: 'rgba(16,185,129,0.55)', text: '#10b981' };
  if (score >= 60) return { bg: 'rgba(16,185,129,0.13)', border: 'rgba(16,185,129,0.35)', text: '#6ee7b7' };
  if (score >= 48) return { bg: 'rgba(245,158,11,0.13)', border: 'rgba(245,158,11,0.35)', text: '#f59e0b' };
  if (score >= 38) return { bg: 'rgba(239,68,68,0.13)', border: 'rgba(239,68,68,0.35)', text: '#f87171' };
  return { bg: 'rgba(239,68,68,0.22)', border: 'rgba(239,68,68,0.55)', text: '#ef4444' };
}

function TrendArrow({ direction }) {
  if (direction === 1) return <span style={{ color: '#10b981', fontSize: 10 }}>↑</span>;
  if (direction === -1) return <span style={{ color: '#ef4444', fontSize: 10 }}>↓</span>;
  return null;
}
TrendArrow.propTypes = { direction: PropTypes.number };

function HeatTile({ fund, onClick, selected, scoreKey }) {
  const score = fund[scoreKey] ?? fund.composite_score;
  const colors = scoreToColor(score);
  const mom5 = fund.return_5d ?? 0;
  const trendsDir = fund.google_trends_direction;

  return (
    <motion.button
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
      whileHover={{ scale: 1.05 }}
      onClick={() => onClick(fund.ticker)}
      className="relative rounded-lg p-3 text-left cursor-pointer transition-all"
      style={{
        backgroundColor: colors.bg,
        border: `1px solid ${selected ? colors.text : colors.border}`,
        boxShadow: selected ? `0 0 16px ${colors.text}50` : `0 0 0 0 transparent`,
        minWidth: 84,
      }}
    >
      <div className="font-mono-data text-base font-bold leading-tight" style={{ color: colors.text }}>
        {fund.ticker}
      </div>
      <div className="font-mono-data text-sm font-semibold mt-1" style={{ color: colors.text }}>
        {Math.round(score)}
        {trendsDir !== undefined && trendsDir !== 0 && <TrendArrow direction={trendsDir} />}
      </div>
      <div className={`font-mono-data text-xs mt-0.5 ${mom5 >= 0 ? 'text-emerald-400/80' : 'text-red-400/80'}`}>
        {mom5 >= 0 ? '+' : ''}{mom5.toFixed(1)}%
      </div>
      <div className="absolute top-1.5 right-2">
        <span className="font-sans text-gray-600" style={{ fontSize: 9 }}>#{fund.rank}</span>
      </div>
    </motion.button>
  );
}
HeatTile.propTypes = {
  fund: PropTypes.object.isRequired,
  onClick: PropTypes.func.isRequired,
  selected: PropTypes.bool,
  scoreKey: PropTypes.string,
};

function FearGreedMeter({ fearGreed }) {
  if (!fearGreed?.available) return null;
  const score = fearGreed.score;
  const rating = fearGreed.rating?.replace(/_/g, ' ') ?? 'neutral';
  const color = score <= 25 ? '#ef4444' : score <= 45 ? '#f87171' : score <= 55 ? '#f59e0b' : score <= 75 ? '#6ee7b7' : '#10b981';
  const pct = score;

  return (
    <div className="flex items-center gap-3 px-3 py-2 rounded-lg border border-gray-800 bg-gray-900/40">
      <div>
        <p className="font-sans text-xs text-gray-500 uppercase tracking-wider">CNN Fear &amp; Greed</p>
        <p className="font-mono-data text-lg font-semibold mt-0.5" style={{ color }}>
          {score.toFixed(0)}
          <span className="font-sans text-xs text-gray-500 ml-1.5 capitalize">{rating}</span>
        </p>
      </div>
      <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 1, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}
FearGreedMeter.propTypes = { fearGreed: PropTypes.object };

export default function SectorHeatmap({ funds, fearGreed, horizon = '7d' }) {
  const [selected, setSelected] = useState(null);

  const hz = getHorizon(horizon);
  const fundMap = Object.fromEntries(funds.map(f => [f.ticker, f]));
  const selectedFund = selected ? fundMap[selected] : null;

  const handleClick = (ticker) => setSelected(prev => prev === ticker ? null : ticker);

  return (
    <div className="bg-card rounded-xl p-5">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="font-sans text-sm font-semibold text-gray-400 uppercase tracking-widest">
          Sector Heatmap
        </h2>
        <div className="flex-1 h-px bg-gray-800" />
        <div className="flex items-center gap-3 text-xs font-sans text-gray-600">
          <span>Score:</span>
          {[['72+', '#10b981'], ['60-72', '#6ee7b7'], ['48-60', '#f59e0b'], ['38-48', '#f87171'], ['<38', '#ef4444']].map(([label, color]) => (
            <span key={label} className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-sm inline-block" style={{ backgroundColor: color + '80' }} />
              {label}
            </span>
          ))}
        </div>
      </div>

      {fearGreed?.available && (
        <div className="mb-4">
          <FearGreedMeter fearGreed={fearGreed} />
        </div>
      )}

      <div className="space-y-4">
        {Object.entries(CATEGORIES).map(([category, tickers]) => {
          const catFunds = tickers.map(t => fundMap[t]).filter(Boolean);
          if (catFunds.length === 0) return null;
          return (
            <div key={category}>
              <p className="font-sans text-xs text-gray-600 mb-2 uppercase tracking-wider">{category}</p>
              <div className="flex flex-wrap gap-2">
                {catFunds.map(fund => (
                  <HeatTile
                    key={fund.ticker}
                    fund={fund}
                    onClick={handleClick}
                    selected={selected === fund.ticker}
                    scoreKey={hz.scoreKey}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected fund detail */}
      {selectedFund && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-5 pt-4 border-t border-gray-800"
        >
          <div className="flex items-start justify-between mb-2">
            <div>
              <span className="font-mono-data text-base font-semibold text-white">{selectedFund.ticker}</span>
              <span className="font-sans text-xs text-gray-500 ml-2">{selectedFund.fund_name}</span>
            </div>
            <button onClick={() => setSelected(null)} className="text-gray-600 hover:text-gray-400 text-xs">✕</button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              ['Composite', `${selectedFund.composite_score.toFixed(1)}`],
              ['Technical', `${selectedFund.technical?.technical_score?.toFixed(1)}`],
              ['Macro', `${selectedFund.macro?.macro_score?.toFixed(1)}`],
              ['Sentiment', `${selectedFund.sentiment?.final_sentiment_score?.toFixed(1)}`],
              ['5d Return', `${selectedFund.return_5d >= 0 ? '+' : ''}${selectedFund.return_5d?.toFixed(2)}%`],
              ['RSI', `${selectedFund.technical?.rsi?.toFixed(1)}`],
              ['Vol Ratio', `${selectedFund.technical?.volume_ratio?.toFixed(2)}x`],
              ...(selectedFund.dividend_yield ? [['Div Yield', `${(selectedFund.dividend_yield * 100).toFixed(2)}%`]] : []),
              ...(selectedFund.beta ? [['Beta', `${selectedFund.beta?.toFixed(2)}`]] : []),
              ...(selectedFund.google_trends_score != null ? [['Trends Interest', `${selectedFund.google_trends_score?.toFixed(0)}/100`]] : []),
              ...(selectedFund.backtest?.accuracy != null ? [['Backtest Acc.', `${selectedFund.backtest.accuracy}%`]] : []),
              ...(selectedFund.technical?.week_52_position != null ? [['52wk Position', `${(selectedFund.technical.week_52_position * 100).toFixed(0)}th %ile`]] : []),
            ].map(([label, val]) => (
              <div key={label} className="bg-gray-800/40 rounded p-2">
                <p className="font-sans text-xs text-gray-500">{label}</p>
                <p className="font-mono-data text-sm text-gray-200 mt-0.5">{val}</p>
              </div>
            ))}
          </div>
          {selectedFund.sentiment?.rationale && (
            <p className="mt-3 font-sans text-xs text-gray-500 italic leading-relaxed">
              {selectedFund.sentiment.rationale}
            </p>
          )}
        </motion.div>
      )}
    </div>
  );
}

SectorHeatmap.propTypes = {
  funds: PropTypes.arrayOf(PropTypes.object).isRequired,
  fearGreed: PropTypes.object,
  horizon: PropTypes.string,
};
