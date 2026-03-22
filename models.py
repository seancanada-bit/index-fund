from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TechnicalSignals(BaseModel):
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    bb_percent_b: float
    sma_50: float
    sma_200: float
    price_above_sma50: bool
    price_above_sma200: bool
    golden_cross: bool
    death_cross: bool
    volume_ratio: float
    momentum_1d: float
    momentum_5d: float
    momentum_20d: float
    momentum_1m: Optional[float] = None   # ~21-trading-day return
    atr_pct: float
    stoch_k: float
    stoch_d: float
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    week_52_position: Optional[float] = None  # 0=at 52wk low, 1=at 52wk high
    technical_score: float


class MacroSignals(BaseModel):
    vix: Optional[float] = None
    fed_funds_rate: Optional[float] = None
    cpi: Optional[float] = None
    unemployment: Optional[float] = None
    yield_curve: Optional[float] = None
    gdp: Optional[float] = None
    fear_greed_score: Optional[float] = None
    fear_greed_rating: Optional[str] = None
    macro_score: float
    triggered_signals: list[dict]


class SentimentResult(BaseModel):
    sentiment: str
    confidence: str
    score: float
    key_themes: list[str]
    rationale: str
    risk_flags: list[str]
    raw_keyword_score: float
    finbert_score: Optional[float] = None
    trends_adjustment: Optional[float] = None
    final_sentiment_score: float
    data_source: str


class BacktestResult(BaseModel):
    accuracy: Optional[float] = None
    windows_tested: int = 0
    results: list[dict] = Field(default_factory=list)
    avg_correct_return: Optional[float] = None


class LongHorizonMetrics(BaseModel):
    """Metrics from multi-year price history — drives 1Y and 5Y scoring."""
    cagr_1y: Optional[float] = None         # Annualised return, 1 year (%)
    cagr_3y: Optional[float] = None         # Annualised return, 3 years (%)
    cagr_5y: Optional[float] = None         # Annualised return, 5 years (%)
    sharpe_1y: Optional[float] = None       # Sharpe ratio, 1 year (RF≈4.5%)
    sharpe_5y: Optional[float] = None       # Sharpe ratio, 5 years
    max_drawdown_1y: Optional[float] = None  # Worst peak-to-trough 1Y (negative %)
    max_drawdown_5y: Optional[float] = None  # Worst peak-to-trough 5Y (negative %)
    annualized_vol_1y: Optional[float] = None
    annualized_vol_5y: Optional[float] = None
    expense_ratio: Optional[float] = None   # Annual fee (e.g. 0.0003 = 0.03%)


class InvestmentScenarios(BaseModel):
    historical: dict                    # {period: pct_change}
    projections: dict                   # {period: {base, bull, bear}}
    base_annual_rate: float             # Net CAGR used for projections (%)
    annual_volatility: float            # Annualised vol (%)


class PricePoint(BaseModel):
    date: str
    close: float
    volume: Optional[float] = None


class FundForecast(BaseModel):
    ticker: str
    fund_name: str
    composite_score: float          # Mirrors score_7d
    confidence_level: str
    rank: int                       # Mirrors rank_7d

    # Per-horizon composite scores (0–100)
    score_7d: Optional[float] = None
    score_30d: Optional[float] = None
    score_1y: Optional[float] = None
    score_5y: Optional[float] = None

    # Per-horizon ranks (1 = best)
    rank_7d: Optional[int] = None
    rank_30d: Optional[int] = None
    rank_1y: Optional[int] = None
    rank_5y: Optional[int] = None

    # Sub-scores surfaced for transparency
    fundamental_score_1y: Optional[float] = None
    fundamental_score_5y: Optional[float] = None

    technical: TechnicalSignals
    macro: MacroSignals
    sentiment: SentimentResult
    backtest: Optional[BacktestResult] = None
    long_metrics: Optional[LongHorizonMetrics] = None
    investment_scenarios: Optional[InvestmentScenarios] = None

    currency: str = "USD"
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    volume: Optional[float] = None
    dividend_yield: Optional[float] = None
    beta: Optional[float] = None
    pe_ratio: Optional[float] = None
    expense_ratio: Optional[float] = None

    return_1d: Optional[float] = None
    return_5d: Optional[float] = None
    return_1m: Optional[float] = None

    google_trends_score: Optional[float] = None
    google_trends_direction: Optional[int] = None
    price_history: list[PricePoint] = Field(default_factory=list)
    ai_rationale: Optional[str] = None
    key_signals: list[dict] = Field(default_factory=list)
    last_updated: Optional[datetime] = None


class ForecastResponse(BaseModel):
    funds: list[FundForecast]
    last_updated: datetime
    data_source_status: dict[str, str]
    total_funds: int
    fear_greed: Optional[dict] = None
