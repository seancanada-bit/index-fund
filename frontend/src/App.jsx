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

const API_BASE     = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const SNAPSHOT_URL = (process.env.PUBLIC_URL || '') + '/snapshot.json';
const CACHE_KEY    = 'iff_forecast_cache';
const CACHE_TS_KEY = 'iff_forecast_ts';

function timeAgo(isoString) {
  if (!isoString) return '';
  const diff = Math.floor((Date.now() - new Date(isoString)) / 1000);
  if (diff < 60)   return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

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

function StaleBanner({ cachedAt }) {
  return (
    <div className="mx-auto max-w-7xl px-4 mb-4">
      <div className="bg-amber-900/20 border border-amber-700/30 rounded-lg px-4 py-2 text-amber-400/70 text-xs flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
        Showing snapshot from {timeAgo(cachedAt)} — live data is loading in the background
      </div>
    </div>
  );
}
StaleBanner.propTypes = { cachedAt: PropTypes.string.isRequired };

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
  // cachedAt: ISO string of when we last successfully saved to localStorage
  // non-null while we're showing stale data waiting for live refresh
  const [cachedAt, setCachedAt] = useState(null);
  // ref so fetchForecast can check without being in the dep array (avoids infinite loop)
  const hasCachedDataRef = useRef(false);

  const applyData = useCallback((data) => {
    setForecast(data);
    setLastUpdated(data.last_updated);
    setSourceStatus(data.data_source_status || {});
  }, []);

  const fetchForecast = useCallback(async (isRefresh = false) => {
    setError(null);

    // ── Step 1: seed UI immediately so no visitor ever sees skeletons
    if (!isRefresh) {
      let seeded = false;

      // 1a. localStorage — freshest option (returning visitors)
      try {
        const raw = localStorage.getItem(CACHE_KEY);
        const ts  = localStorage.getItem(CACHE_TS_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed?.funds?.length > 0) {
            applyData(parsed);
            setLoading(false);
            setCachedAt(ts || new Date(0).toISOString());
            hasCachedDataRef.current = true;
            seeded = true;
          }
        }
      } catch (_) {}

      // 1b. Static snapshot.json on cPanel — first-time visitors, no cold start
      if (!seeded) {
        try {
          const snap = await fetch(SNAPSHOT_URL);
          if (snap.ok) {
            const snapData = await snap.json();
            if (snapData?.funds?.length > 0) {
              applyData(snapData);
              setLoading(false);
              setCachedAt(snapData.last_updated || new Date(0).toISOString());
              hasCachedDataRef.current = true;
            }
          }
        } catch (_) {}
      }
    }

    if (isRefresh) setRefreshing(true);

    // ── Step 2: fetch live data with a 90-second timeout
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 90_000);

    try {
      const res = await fetch(`${API_BASE}/api/forecast`, { signal: controller.signal });
      clearTimeout(timer);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();

      applyData(data);
      setCachedAt(null);  // live data arrived — hide stale banner

      // Persist for next visit
      localStorage.setItem(CACHE_KEY, JSON.stringify(data));
      localStorage.setItem(CACHE_TS_KEY, new Date().toISOString());
    } catch (err) {
      clearTimeout(timer);
      if (err.name === 'AbortError') {
        // Render still spinning up — if stale data is showing, just add a soft note
        if (!hasCachedDataRef.current) {
          setError('Live data is taking longer than usual (Render cold start). Retrying…');
        }
        // Retry once more after 60 s — Render is usually warm by then
        setTimeout(() => fetchForecast(true), 60_000);
      } else {
        if (!hasCachedDataRef.current) setError(err.message || 'Failed to load forecast data. Is the backend running?');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [applyData]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await fetch(`${API_BASE}/api/refresh`);
      await new Promise(r => setTimeout(r, 2000));
      await fetchForecast(true);
    } catch (err) {
      setError('Refresh failed: ' + err.message);
      setRefreshing(false);
    }
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
        />

        {cachedAt && !refreshing && <StaleBanner cachedAt={cachedAt} />}
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
