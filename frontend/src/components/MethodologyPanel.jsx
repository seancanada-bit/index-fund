import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { motion, AnimatePresence } from 'framer-motion';

function AccordionItem({ title, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-gray-800 last:border-0">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex justify-between items-center py-4 text-left group"
      >
        <span className="font-sans text-sm font-medium text-gray-300 group-hover:text-white transition-colors">
          {title}
        </span>
        <span className="text-gray-600 group-hover:text-gray-400 transition-colors">
          {open ? '▲' : '▼'}
        </span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="pb-4 font-sans text-sm text-gray-500 leading-relaxed space-y-2">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
AccordionItem.propTypes = { title: PropTypes.string, children: PropTypes.node };

export default function MethodologyPanel() {
  return (
    <div className="bg-card rounded-xl p-6">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="font-sans text-base font-semibold text-gray-300">Methodology & Data Sources</h2>
        <div className="flex-1 h-px bg-gray-800" />
      </div>

      <div className="space-y-0">
        <AccordionItem title="Technical Score (40% weight)">
          <p>Computed from 9 indicators on 60 days of OHLCV price data:</p>
          <ul className="list-disc list-inside space-y-1 ml-2">
            <li><strong className="text-gray-400">RSI (14-day)</strong> — Relative Strength Index. Below 40 = oversold signal (+20 pts), above 70 = overbought (-20 pts)</li>
            <li><strong className="text-gray-400">MACD (12/26/9)</strong> — Moving Average Convergence/Divergence. Positive histogram trending up adds +15 pts</li>
            <li><strong className="text-gray-400">Bollinger Bands (20-day, 2σ)</strong> — %B position; extremes are mean-reversion signals</li>
            <li><strong className="text-gray-400">50-day & 200-day SMA</strong> — Price above each adds +10 pts each</li>
            <li><strong className="text-gray-400">Golden/Death Cross</strong> — 50-SMA crossing 200-SMA in last 10 days: ±15 pts</li>
            <li><strong className="text-gray-400">Volume Ratio</strong> — 5-day vs 30-day average. Ratio &gt;1.2 adds +10 pts</li>
            <li><strong className="text-gray-400">5-day Momentum</strong> — Positive return adds +10 pts</li>
            <li><strong className="text-gray-400">Stochastic Oscillator %K/%D (14-day)</strong> — Overbought/oversold extremes</li>
            <li><strong className="text-gray-400">ATR (14-day)</strong> — Normalized volatility as % of price</li>
          </ul>
        </AccordionItem>

        <AccordionItem title="Macro Score (30% weight)">
          <p>Pulled from FRED (Federal Reserve Economic Data), cached for 6 hours. Scoring is category-specific:</p>
          <ul className="list-disc list-inside space-y-1 ml-2">
            <li><strong className="text-gray-400">VIX (VIXCLS)</strong> — Fear index. Below 20 is favorable for equities; above 30 favors bonds/gold</li>
            <li><strong className="text-gray-400">Yield Curve (T10Y2Y)</strong> — 10-year minus 2-year spread. Inversion signals recession risk</li>
            <li><strong className="text-gray-400">Fed Funds Rate (FEDFUNDS)</strong> — Rising rates hurt bonds/growth; falling rates help TLT, QQQ</li>
            <li><strong className="text-gray-400">CPI (CPIAUCSL)</strong> — Rising inflation favors commodities/energy; hurts bonds</li>
            <li><strong className="text-gray-400">Unemployment (UNRATE)</strong> — Rising unemployment favors defensive dividend funds</li>
            <li><strong className="text-gray-400">GDP</strong> — Positive growth supports broad equity and small-cap funds</li>
          </ul>
        </AccordionItem>

        <AccordionItem title="Sentiment Score (30% weight)">
          <p>Three-step pipeline combining keyword analysis and AI synthesis:</p>
          <ol className="list-decimal list-inside space-y-1 ml-2">
            <li><strong className="text-gray-400">NewsAPI</strong> — Top 20 headlines from last 3 days, weighted by recency (1.0x / 0.7x / 0.4x decay)</li>
            <li><strong className="text-gray-400">Reddit PRAW</strong> — Top 15 posts from r/investing, r/stocks, r/ETFs in last 48 hours, weighted by upvotes</li>
            <li><strong className="text-gray-400">Claude AI Synthesis</strong> — Claude claude-sonnet-4-20250514 analyzes headlines + posts, returns structured JSON with sentiment, confidence, themes, and risk flags. Final score = Claude (70%) + keyword (30%)</li>
          </ol>
          <p>If Claude API is unavailable, falls back to keyword-only scoring (flagged in data source status).</p>
        </AccordionItem>

        <AccordionItem title="Composite Score & Confidence">
          <p>
            <strong className="text-gray-400">Composite = Technical × 0.40 + Macro × 0.30 + Sentiment × 0.30</strong>
          </p>
          <p>Confidence level reflects signal agreement:</p>
          <ul className="list-disc list-inside space-y-1 ml-2">
            <li><strong className="text-gray-400">High</strong> — All three sub-scores within 15 points (strong consensus)</li>
            <li><strong className="text-gray-400">Medium</strong> — Two of three sub-scores agree within 20 points</li>
            <li><strong className="text-gray-400">Low</strong> — Signals diverge significantly (contradictory evidence)</li>
          </ul>
          <p>Rankings refresh automatically every 30 minutes via APScheduler background job.</p>
        </AccordionItem>

        <AccordionItem title="Data Sources & Caching">
          <ul className="list-disc list-inside space-y-1 ml-2">
            <li><strong className="text-gray-400">yfinance</strong> — Primary price source, no API key required</li>
            <li><strong className="text-gray-400">Alpha Vantage</strong> — Fallback price source (25 calls/day free tier — caching prevents limit exhaustion)</li>
            <li><strong className="text-gray-400">FRED</strong> — Macro data (free, requires key). Cached 6 hours</li>
            <li><strong className="text-gray-400">NewsAPI</strong> — News headlines. Cached 1 hour per ticker</li>
            <li><strong className="text-gray-400">Reddit PRAW</strong> — Social sentiment. Cached 2 hours per ticker</li>
            <li><strong className="text-gray-400">Redis</strong> — Primary cache. Falls back to in-memory dict if Redis is unavailable</li>
          </ul>
        </AccordionItem>

        <AccordionItem title="Disclaimer">
          <div className="bg-amber-900/20 border border-amber-800/40 rounded-lg p-3 text-amber-300/80 text-xs leading-relaxed">
            This tool is for <strong>informational and educational purposes only</strong>. It does not constitute financial advice, investment advice, or a recommendation to buy or sell any security. Past performance and algorithmic scores do not guarantee future results. All investment decisions should be made in consultation with a qualified financial advisor. The operators of this tool accept no liability for investment decisions made based on its output.
          </div>
        </AccordionItem>
      </div>
    </div>
  );
}
