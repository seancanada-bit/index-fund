# Index Fund Forecaster

An AI-powered full-stack web application that ranks 20 major index funds by their likelihood of increasing over the next 7 days, combining live market data, macroeconomic indicators, and AI-synthesized sentiment analysis.

![Screenshot placeholder — add screenshot here after first run]

---

## Overview

The forecaster combines three data pipelines:

| Signal | Weight | Sources |
|--------|--------|---------|
| **Technical Analysis** | 40% | yfinance / Alpha Vantage (RSI, MACD, Bollinger Bands, SMA crossovers, volume, momentum) |
| **Macroeconomic** | 30% | FRED (VIX, Fed Funds Rate, CPI, yield curve, unemployment, GDP) |
| **Sentiment** | 30% | NewsAPI + Reddit PRAW → Claude AI synthesis |

Rankings are refreshed automatically every 30 minutes. You can force a refresh via the UI or the `/api/refresh` endpoint.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- API keys for the services below (all free tiers available)

---

## API Keys — Where to Get Them

| Key | Where to Get | Free Tier |
|-----|-------------|-----------|
| `ALPHA_VANTAGE_KEY` | [alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key) | 25 calls/day |
| `FRED_API_KEY` | [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html) | Unlimited |
| `NEWS_API_KEY` | [newsapi.org/register](https://newsapi.org/register) | 100 req/day |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) | Pay-per-use |
| `REDDIT_CLIENT_ID` + `SECRET` | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) — create "script" app | Free |

---

## Setup

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd index-fund-forecaster

# 2. Copy and fill in environment variables
cp .env.example .env
# Edit .env and add your API keys

# 3. Start all services (production build)
docker compose up --build

# OR: Start in development mode (hot reload)
docker compose -f docker-compose.dev.yml up --build
```

The app will be available at:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs

---

## Development Mode

The dev compose file mounts source directories as volumes for hot reload:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Changes to `backend/*.py` or `frontend/src/**` will auto-reload.

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/forecast` | Full ranked forecast for all 20 funds (cached 30 min) |
| `GET /api/fund/{ticker}` | Detailed breakdown for a single fund |
| `GET /api/refresh` | Invalidate cache and trigger background rebuild |
| `GET /api/health` | Health check |
| `GET /api/meta` | Last updated timestamp and data source statuses |
| `GET /docs` | Interactive Swagger UI |

---

## Caching Architecture

```
Request → Redis cache hit? → Return cached result (< 30 min old)
                ↓ miss
         Build fresh forecast
                ↓
         Store in Redis (TTL: 30 min)
                ↓
         Return result
```

**Cache TTLs:**
- Full forecast: 30 minutes
- Price history: 30 minutes
- Real-time quotes: 5 minutes
- News: 1 hour per ticker
- Reddit: 2 hours per ticker
- Macro data: 6 hours

**Redis unavailable?** The backend falls back to an in-memory dict — data is still cached within the process lifetime but won't persist across restarts.

### Force a Refresh

```bash
# Via API
curl http://localhost:8000/api/refresh

# Via UI
Click the "Refresh Data" button in the top right
```

---

## Scoring Methodology

### Technical Score (40%)
Computed from 9 indicators on 60 days of price history:

- **RSI (14)** — Oversold (<40) = +20pts; Overbought (>70) = -20pts
- **MACD (12/26/9)** — Positive histogram, trending up = +15pts
- **Price vs 50-day SMA** — Above = +10pts
- **Price vs 200-day SMA** — Above = +10pts
- **Golden/Death Cross** — Detected in last 10 days = ±15pts
- **Volume Ratio** (5-day vs 30-day) — Above 1.2x = +10pts
- **5-day Momentum** — Positive = +10pts
- **Bollinger %B** — Not at extremes (0.2–0.8) = +5pts

### Macro Score (30%)
Category-aware scoring using FRED data:

- VIX, Fed Funds Rate trend, yield curve, CPI trend, unemployment, GDP
- Each fund is classified (equity broad, growth/tech, small cap, international, fixed income, commodities, financials, real estate)
- Signals fire differently per category (e.g., inverted yield curve is bullish for TLT, bearish for SPY)

### Sentiment Score (30%)
1. **Keyword pre-scoring** — Bullish/bearish word counts across news + Reddit posts, weighted by recency
2. **Claude AI synthesis** — Structured JSON analysis of headlines: sentiment, confidence, key themes, risk flags
3. **Blend** — Final = Claude score × 0.7 + keyword score × 0.3

### Confidence Levels
- **High** — All 3 sub-scores within 15 points (strong consensus)
- **Medium** — 2 of 3 sub-scores agree within 20 points
- **Low** — Signals contradict each other significantly

---

## Known Limitations

- **Alpha Vantage free tier** is limited to 25 API calls/day. The 30-minute cache ensures the 20 tracked tickers can complete multiple cycles daily without hitting the limit. yfinance is always attempted first.
- **NewsAPI free tier** limits to 100 requests/day and only returns articles up to 1 month old. Developer (paid) plan removes these limits.
- **Reddit PRAW** requires creating a Reddit "script" app. Heavily upvoted posts may bias sentiment.
- **Claude API costs** vary by usage. Each forecast run makes up to 23 Claude calls (20 sentiment analyses + 3 rationale generations). With claude-sonnet-4-20250514, this is approximately $0.05–0.20 per full rebuild depending on content length.
- Forecasts reflect available data and AI analysis at time of generation — they are **not financial advice**.

---

## Tracked Funds

| Ticker | Name | Category |
|--------|------|----------|
| SPY | SPDR S&P 500 ETF Trust | Equity Broad |
| QQQ | Invesco QQQ Trust (Nasdaq-100) | Growth/Tech |
| DIA | SPDR Dow Jones Industrial ETF | Equity Broad |
| IWM | iShares Russell 2000 ETF | Small Cap |
| VTI | Vanguard Total Stock Market ETF | Equity Broad |
| VOO | Vanguard S&P 500 ETF | Equity Broad |
| ARKK | ARK Innovation ETF | Growth/Tech |
| GLD | SPDR Gold Shares | Commodities |
| TLT | iShares 20+ Year Treasury Bond ETF | Fixed Income |
| EFA | iShares MSCI EAFE ETF | International |
| EEM | iShares MSCI Emerging Markets ETF | International |
| VNQ | Vanguard Real Estate ETF | Real Estate |
| XLF | Financial Select Sector SPDR Fund | Financials |
| XLK | Technology Select Sector SPDR Fund | Growth/Tech |
| XLE | Energy Select Sector SPDR Fund | Commodities |
| SCHD | Schwab US Dividend Equity ETF | Equity Broad |
| VIG | Vanguard Dividend Appreciation ETF | Equity Broad |
| BND | Vanguard Total Bond Market ETF | Fixed Income |
| IAU | iShares Gold Trust | Commodities |
| PDBC | Invesco Optimum Yield Diversified Commodity Strategy ETF | Commodities |

---

## Disclaimer

**This application is for informational and educational purposes only.** It does not constitute financial advice, investment advice, trading advice, or a recommendation to buy or sell any security. The AI-generated rankings and rationales are algorithmic outputs based on publicly available data and should not be used as the sole basis for any investment decision. Past performance does not guarantee future results. Always consult a qualified financial advisor before making investment decisions.
