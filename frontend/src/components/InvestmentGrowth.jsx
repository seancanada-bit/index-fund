import React, { useState, useMemo } from 'react';
import PropTypes from 'prop-types';
import { motion } from 'framer-motion';

const HIST_PERIODS = [
  { key: '1m',  label: '1 month ago',   short: '1M' },
  { key: '3m',  label: '3 months ago',  short: '3M' },
  { key: '6m',  label: '6 months ago',  short: '6M' },
  { key: '1y',  label: '1 year ago',    short: '1Y' },
  { key: '3y',  label: '3 years ago',   short: '3Y' },
  { key: '5y',  label: '5 years ago',   short: '5Y' },
];

const FWD_PERIODS = [
  { key: '6m',  label: '6 months'  },
  { key: '1y',  label: '1 year'    },
  { key: '3y',  label: '3 years'   },
  { key: '5y',  label: '5 years'   },
  { key: '10y', label: '10 years'  },
];

function fmt(val, currency) {
  const sym = currency === 'CAD' ? 'CA$' : '$';
  if (val >= 1000000) return sym + (val / 1000000).toFixed(1) + 'M';
  if (val >= 10000)   return sym + Math.round(val).toLocaleString();
  return sym + val.toLocaleString('en', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function AmountInput({ amount, rawInput, onChange, onBlur, currency, onCurrency, ticker }) {
  return (
    <div className="flex flex-wrap items-center gap-3 mb-5">
      <div className="flex items-center bg-gray-900 border border-gray-700 rounded-lg overflow-hidden focus-within:border-emerald-600/60 transition-colors">
        <span className="pl-3 pr-1 text-gray-500 font-sans text-sm select-none">$</span>
        <input
          type="text"
          inputMode="numeric"
          value={rawInput}
          onChange={onChange}
          onBlur={onBlur}
          className="bg-transparent text-white font-mono-data text-sm w-28 py-2 pr-3 outline-none"
        />
      </div>
      <div className="flex rounded-lg border border-gray-700 overflow-hidden text-xs font-sans">
        {['CAD', 'USD'].map(c => (
          <button
            key={c}
            onClick={() => onCurrency(c)}
            className={`px-3 py-2 transition-colors ${currency === c ? 'bg-emerald-600/80 text-white' : 'text-gray-500 hover:text-gray-300'}`}
          >
            {c}
          </button>
        ))}
      </div>
      <span className="font-sans text-xs text-gray-600">invested in <span className="text-gray-500">{ticker}</span></span>
    </div>
  );
}
AmountInput.propTypes = {
  amount: PropTypes.number, rawInput: PropTypes.string, onChange: PropTypes.func,
  onBlur: PropTypes.func, currency: PropTypes.string, onCurrency: PropTypes.func, ticker: PropTypes.string,
};

function HistoricalBars({ historical, amount, currency }) {
  const available = HIST_PERIODS.filter(p => historical[p.key] !== undefined);
  if (available.length === 0) return null;
  const maxAbsPct = Math.max(...available.map(p => Math.abs(historical[p.key])), 1);

  return (
    <div>
      <p className="font-sans text-xs text-gray-500 uppercase tracking-widest mb-3 flex items-center gap-2">
        <span className="text-base">📅</span> If you had invested...
      </p>
      <div className="space-y-3">
        {available.map(({ key, label }, i) => {
          const pct = historical[key];
          const result = amount * (1 + pct / 100);
          const isPos = pct >= 0;
          const barPct = Math.min((Math.abs(pct) / maxAbsPct) * 100, 100);
          return (
            <div key={key}>
              <div className="flex items-center justify-between mb-1">
                <span className="font-sans text-xs text-gray-500">{label}</span>
                <div className="flex items-center gap-3">
                  <span className={`font-sans text-xs tabular-nums ${isPos ? 'text-emerald-400' : 'text-red-400'}`}>
                    {isPos ? '+' : ''}{pct.toFixed(1)}%
                  </span>
                  <span className={`font-mono-data text-sm font-semibold tabular-nums ${isPos ? 'text-emerald-300' : 'text-red-300'}`}>
                    {fmt(result, currency)}
                  </span>
                </div>
              </div>
              <div className="h-1.5 bg-gray-800/80 rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${barPct}%` }}
                  transition={{ duration: 0.6, ease: 'easeOut', delay: i * 0.06 }}
                  className="h-full rounded-full"
                  style={{ backgroundColor: isPos ? '#10b981' : '#ef4444' }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
HistoricalBars.propTypes = { historical: PropTypes.object, amount: PropTypes.number, currency: PropTypes.string };

function ProjectedRanges({ projections, amount, currency, baseRate, annVol }) {
  const maxMult = useMemo(() => {
    const bulls = FWD_PERIODS.map(p => projections[p.key]?.bull || 1);
    return Math.max(...bulls, 1);
  }, [projections]);

  const available = FWD_PERIODS.filter(p => projections[p.key]);

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <p className="font-sans text-xs text-gray-500 uppercase tracking-widest flex items-center gap-2">
          <span className="text-base">📈</span> Projected growth
        </p>
      </div>
      <p className="font-sans text-xs text-gray-600 mb-4">
        {baseRate > 0 ? '+' : ''}{baseRate}% annual return · ±{annVol}% volatility band
      </p>

      <div className="space-y-4">
        {available.map(({ key, label }, i) => {
          const proj = projections[key];
          const bearAmt = amount * proj.bear;
          const baseAmt = amount * proj.base;
          const bullAmt = amount * proj.bull;
          const maxAmt = amount * maxMult;

          const bearPct = Math.max((bearAmt / maxAmt) * 100, 0);
          const basePct = Math.min((baseAmt / maxAmt) * 100, 99.5);
          const bullPct = Math.min((bullAmt / maxAmt) * 100, 100);
          const isGain = proj.base >= 1;
          const gainPct = ((proj.base - 1) * 100).toFixed(0);

          return (
            <div key={key}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-sans text-xs text-gray-500">In {label}</span>
                <div className="flex items-center gap-2">
                  <span className={`font-sans text-xs tabular-nums ${isGain ? 'text-emerald-400' : 'text-red-400'}`}>
                    {isGain ? '+' : ''}{gainPct}%
                  </span>
                  <span className={`font-mono-data text-sm font-semibold tabular-nums ${isGain ? 'text-gray-200' : 'text-red-300'}`}>
                    {fmt(baseAmt, currency)}
                  </span>
                </div>
              </div>

              {/* Range bar */}
              <div className="relative h-3 bg-gray-800/80 rounded-full">
                {/* Bear-to-bull fill */}
                <motion.div
                  initial={{ width: 0, left: `${bearPct}%` }}
                  animate={{ width: `${bullPct - bearPct}%`, left: `${bearPct}%` }}
                  transition={{ duration: 0.7, ease: 'easeOut', delay: i * 0.08 }}
                  className="absolute h-full rounded-full"
                  style={{ backgroundColor: isGain ? '#10b981' : '#ef4444', opacity: 0.28 }}
                />
                {/* Base marker */}
                <motion.div
                  initial={{ left: '0%' }}
                  animate={{ left: `calc(${basePct}% - 1px)` }}
                  transition={{ duration: 0.7, ease: 'easeOut', delay: i * 0.08 }}
                  className="absolute top-0 h-full w-0.5 rounded-full"
                  style={{ backgroundColor: isGain ? '#10b981' : '#ef4444' }}
                />
              </div>

              {/* Bear / Bull labels */}
              <div className="flex justify-between mt-0.5">
                <span className="font-sans text-xs text-red-400/50 tabular-nums">{fmt(bearAmt, currency)}</span>
                <span className="font-sans text-xs text-emerald-400/50 tabular-nums">{fmt(bullAmt, currency)}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex items-start gap-1.5 bg-amber-900/10 border border-amber-800/25 rounded-lg px-3 py-2">
        <span className="text-amber-400/60 text-xs mt-px shrink-0">⚠</span>
        <p className="font-sans text-xs text-gray-600 leading-relaxed">
          Projections use historical CAGR ± annualised volatility. Past returns do not guarantee future results. Not financial advice.
        </p>
      </div>
    </div>
  );
}
ProjectedRanges.propTypes = {
  projections: PropTypes.object, amount: PropTypes.number, currency: PropTypes.string,
  baseRate: PropTypes.number, annVol: PropTypes.number,
};

export default function InvestmentGrowth({ fund, compact = false }) {
  const [amount, setAmount] = useState(1000);
  const [rawInput, setRawInput] = useState('1,000');
  const [currency, setCurrency] = useState(fund?.currency || 'CAD');

  const sc = fund?.investment_scenarios;
  if (!sc) return null;

  const { historical, projections, base_annual_rate, annual_volatility } = sc;

  const handleChange = (e) => {
    const raw = e.target.value.replace(/[^0-9.]/g, '');
    setRawInput(raw);
    const num = parseFloat(raw);
    if (!isNaN(num) && num > 0) setAmount(num);
  };

  const handleBlur = () => setRawInput(Number(amount).toLocaleString());

  if (compact) {
    // Slim version for hero cards — just 3 key historical periods + 2 projections
    const histKeys = ['1y', '3y', '5y'].filter(k => historical[k] !== undefined);
    const fwdKeys  = ['1y', '5y'].filter(k => projections[k]);
    return (
      <div className="space-y-4">
        <AmountInput amount={amount} rawInput={rawInput} onChange={handleChange} onBlur={handleBlur}
          currency={currency} onCurrency={setCurrency} ticker={fund.ticker} />
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="font-sans text-xs text-gray-600 uppercase tracking-widest mb-2">Historical</p>
            {histKeys.map(k => {
              const period = HIST_PERIODS.find(p => p.key === k);
              const pct = historical[k];
              const result = amount * (1 + pct / 100);
              const isPos = pct >= 0;
              return (
                <div key={k} className="flex justify-between items-center py-1 border-b border-gray-800/60 last:border-0">
                  <span className="font-sans text-xs text-gray-600">{period.short}</span>
                  <span className={`font-mono-data text-xs font-semibold ${isPos ? 'text-emerald-300' : 'text-red-300'}`}>
                    {fmt(result, currency)}
                  </span>
                </div>
              );
            })}
          </div>
          <div>
            <p className="font-sans text-xs text-gray-600 uppercase tracking-widest mb-2">Projected</p>
            {fwdKeys.map(k => {
              const period = FWD_PERIODS.find(p => p.key === k);
              const baseAmt = amount * projections[k].base;
              const isGain = projections[k].base >= 1;
              return (
                <div key={k} className="flex justify-between items-center py-1 border-b border-gray-800/60 last:border-0">
                  <span className="font-sans text-xs text-gray-600">{period.label}</span>
                  <span className={`font-mono-data text-xs font-semibold ${isGain ? 'text-gray-300' : 'text-red-300'}`}>
                    {fmt(baseAmt, currency)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
        <p className="font-sans text-xs text-gray-700">
          Based on {base_annual_rate > 0 ? '+' : ''}{base_annual_rate}% CAGR. Not financial advice.
        </p>
      </div>
    );
  }

  return (
    <div>
      <AmountInput amount={amount} rawInput={rawInput} onChange={handleChange} onBlur={handleBlur}
        currency={currency} onCurrency={setCurrency} ticker={fund.ticker} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <HistoricalBars historical={historical} amount={amount} currency={currency} />
        <ProjectedRanges projections={projections} amount={amount} currency={currency}
          baseRate={base_annual_rate} annVol={annual_volatility} />
      </div>
    </div>
  );
}

InvestmentGrowth.propTypes = {
  fund: PropTypes.object.isRequired,
  compact: PropTypes.bool,
};
