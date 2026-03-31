import React, { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import PropTypes from 'prop-types';
import HeroSection from './components/HeroSection';
import ForecastCard from './components/ForecastCard';
import FundTable from './components/FundTable';
import SectorHeatmap from './components/SectorHeatmap';
import BacktestPanel from './components/BacktestPanel';
import TrackRecord from './components/TrackRecord';
import ModelInsights from './components/ModelInsights';
import MethodologyPanel from './components/MethodologyPanel';
import MarketMoodBar from './components/MarketMoodBar';
import JumpNav from './components/JumpNav';
import HorizonSelector from './components/HorizonSelector';

const DATA_BASE    = process.env.PUBLIC_URL || '';
const SNAPSHOT_URL = DATA_BASE + '/snapshot.json';
const CACHE_KEY    = 'iff_forecast_cache';
const CACHE_TS_KEY = 'iff_forecast_ts';

function ErrorBanner({ message }) {
  return (
    <div className="mx-auto max-w-7xl px-4 mb-6">
      <div className="bg-red-900/30 border border-red-700/50 rounded-lg p-4 text-red-300 font-sans text-sm">
        <span className="font-semibold">Error: </span>{message}
      </div>
    </div>
  );
}
ErrorBanner.propTypes = { message: PropTypes.string.isRequired };


function LoadingSkeleton() {
  return (
    <div className="mx-auto max-w-7xl px-4 space-y-6">
      {/* Hero card skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-card rounded-xl p-6 animate-pulse lg:col-span-1">
          <div className="h-4 bg-gray-700/80 rounded w-1/3 mb-4" />
          <div className="h-10 bg-gray-700/80 rounded w-1/2 mb-6" />
          <div className="h-28 bg-gray-700/80 rounded-full w-28 mx-auto mb-6" />
          <div className="space-y-2.5">
            <div className="h-2 bg-gray-700/80 rounded" />
            <div className="h-2 bg-gray-700/80 rounded w-5/6" />
            <div className="h-2 bg-gray-700/80 rounded w-4/6" />
          </div>
        </div>
        {[2, 3].map(i => (
          <div key={i} className="bg-card rounded-xl p-6 animate-pulse">
            <div className="h-4 bg-gray-700/60 rounded w-1/3 mb-4" />
            <div className="h-8 bg-gray-700/60 rounded w-1/2 mb-6" />
            <div className="h-24 bg-gray-700/60 rounded-full w-24 mx-auto mb-6" />
            <div className="space-y-2.5">
              <div className="h-2 bg-gray-700/60 rounded" />
              <div className="h-2 bg-gray-700/60 rounded w-5/6" />
            </div>
          </div>
        ))}
      </div>
      {/* Heatmap skeleton */}
      <div className="bg-card rounded-xl p-6 animate-pulse">
        <div className="h-5 bg-gray-700/60 rounded w-1/4 mb-4" />
        <div className="grid grid-cols-5 sm:grid-cols-8 gap-2">
          {[...Array(20)].map((_, i) => (
            <div key={i} className="h-20 bg-gray-700/40 rounded-lg" />
          ))}
        </div>
      </div>
      {/* Table skeleton */}
      <div className="bg-card rounded-xl p-4 animate-pulse space-y-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-10 bg-gray-700/40 rounded" />
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [sourceStatus, setSourceStatus] = useState({});
  const [horizon, setHorizon] = useState('7d');
  const hasCachedDataRef = useRef(false);

  const applyData = useCallback((data) => {
    setForecast(data);
    setLastUpdated(data.last_updated);
    setSourceStatus(data.data_source_status || {});
  }, []);

  const fetchForecast = useCallback(async (isRefresh = false) => {
    setError(null);
    if (isRefresh) setRefreshing(true);

    // ── Step 1: seed UI from localStorage (returning visitors)
    if (!isRefresh) {
      try {
        const raw = localStorage.getItem(CACHE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed?.funds?.length > 0) {
            applyData(parsed);
            setLoading(false);
            hasCachedDataRef.current = true;
          }
        }
      } catch (_) {}
    }

    // ── Step 2: fetch snapshot.json (updated every 4h by GitHub Actions)
    try {
      const res = await fetch(SNAPSHOT_URL + '?t=' + Date.now());
      if (!res.ok) throw new Error(`Snapshot returned ${res.status}`);
      const data = await res.json();

      if (data?.funds?.length > 0) {
        applyData(data);
          // Persist for next visit
        localStorage.setItem(CACHE_KEY, JSON.stringify(data));
        localStorage.setItem(CACHE_TS_KEY, new Date().toISOString());
      }
    } catch (err) {
      if (!hasCachedDataRef.current) {
        setError(err.message || 'Failed to load forecast data.');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [applyData]);

  const handleRefresh = useCallback(async () => {
    await fetchForecast(true);
  }, [fetchForecast]);

  useEffect(() => {
    fetchForecast();
  }, [fetchForecast]);

  const top3 = forecast?.funds?.slice(0, 3) ?? [];
  const allFunds = forecast?.funds ?? [];
  const fearGreed = forecast?.fear_greed ?? null;

  return (
    <div className="min-h-screen bg-depth" style={{ backgroundColor: '#0a0e1a' }}>
      {/* Market Mood Command Bar */}
      <MarketMoodBar
        status={sourceStatus}
        lastUpdated={lastUpdated}
        fearGreed={fearGreed}
        onRefresh={handleRefresh}
        refreshing={refreshing}
      />

      <main className="pb-20">
        <HeroSection
          onRefresh={handleRefresh}
          refreshing={refreshing}
          lastUpdated={lastUpdated}
          fundCount={forecast?.total_funds ?? 49}
        />

        {error && <ErrorBanner message={error} />}

        <AnimatePresence mode="wait">
          {loading ? (
            <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <LoadingSkeleton />
            </motion.div>
          ) : forecast ? (
            <motion.div
              key="content"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4 }}
              className="space-y-10"
            >
              {/* Horizon Selector */}
              <div className="mx-auto max-w-7xl px-4">
                <HorizonSelector active={horizon} onChange={setHorizon} />
              </div>

              {/* Top 3 Featured Cards */}
              {top3.length > 0 && (
                <section id="section-top-picks" className="mx-auto max-w-7xl px-4 scroll-mt-16">
                  <div className="flex items-center gap-3 mb-5">
                    <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">Top Ranked Funds</h2>
                    <div className="flex-1 h-px bg-gray-800" />
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {top3.map((fund, idx) => (
                      <motion.div
                        key={fund.ticker}
                        initial={{ opacity: 0, y: 24 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, delay: idx * 0.1 }}
                      >
                        <ForecastCard fund={fund} isHero={fund.rank === 1} horizon={horizon} />
                      </motion.div>
                    ))}
                  </div>
                </section>
              )}

              {/* Sector Heatmap */}
              {allFunds.length > 0 && (
                <section id="section-heatmap" className="mx-auto max-w-7xl px-4 scroll-mt-16">
                  <SectorHeatmap funds={allFunds} fearGreed={fearGreed} horizon={horizon} />
                </section>
              )}

              {/* Full Rankings Table */}
              {allFunds.length > 0 && (
                <section id="section-all-funds" className="mx-auto max-w-7xl px-4 scroll-mt-16">
                  <div className="flex items-center gap-3 mb-5">
                    <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">All Tracked Funds</h2>
                    <div className="flex-1 h-px bg-gray-800" />
                    <span className="font-mono-data text-xs text-gray-600">{allFunds.length} funds</span>
                  </div>
                  <FundTable funds={allFunds} horizon={horizon} />
                </section>
              )}

              {/* Backtest Panel */}
              {allFunds.length > 0 && (
                <section id="section-backtest" className="mx-auto max-w-7xl px-4 scroll-mt-16">
                  <BacktestPanel funds={allFunds} />
                </section>
              )}

              {/* Track Record + Model Insights */}
              <section id="section-track-record" className="mx-auto max-w-7xl px-4 scroll-mt-16">
                <div className="flex items-center gap-3 mb-5">
                  <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">Performance & Self-Learning</h2>
                  <div className="flex-1 h-px bg-gray-800" />
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <TrackRecord />
                  <ModelInsights />
                </div>
              </section>

              {/* Methodology */}
              <section className="mx-auto max-w-7xl px-4">
                <MethodologyPanel />
              </section>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </main>

      {/* Floating jump navigation */}
      <JumpNav />
    </div>
  );
}
