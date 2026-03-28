import logging
import numpy as np

logger = logging.getLogger(__name__)

FUND_CATEGORIES = {
    # US funds
    "SPY": "equity_broad", "VTI": "equity_broad", "VOO": "equity_broad",
    "DIA": "equity_broad", "SCHD": "equity_broad", "VIG": "equity_broad",
    "QQQ": "growth_tech", "ARKK": "growth_tech", "XLK": "growth_tech",
    "IWM": "small_cap",
    "EFA": "international", "EEM": "international",
    "TLT": "fixed_income", "BND": "fixed_income",
    "VNQ": "real_estate",
    "GLD": "commodities", "IAU": "commodities", "PDBC": "commodities", "XLE": "commodities",
    "XLF": "financials",
    # US sector ETFs
    "XLV": "equity_broad", "XLU": "equity_broad", "XLP": "equity_broad",
    "XLY": "equity_broad", "XLI": "equity_broad",
    # Canadian funds (.TO)
    "XIU.TO": "equity_broad", "XIC.TO": "equity_broad", "VCN.TO": "equity_broad",
    "HXT.TO": "equity_broad",
    "XEQT.TO": "equity_broad", "XGRO.TO": "equity_broad",
    "VGRO.TO": "equity_broad", "VBAL.TO": "equity_broad",
    "ZSP.TO": "equity_broad",
    "XDV.TO": "equity_broad", "ZLB.TO": "equity_broad",
    "XEF.TO": "international",
    "ZAG.TO": "fixed_income", "XBB.TO": "fixed_income",
    "ZEB.TO": "financials", "XFN.TO": "financials",
    "XRE.TO": "real_estate",
    "TEC.TO": "growth_tech",
    "ZGD.TO": "commodities",
    # New Canadian funds
    "ZQQ.TO": "growth_tech", "VGG.TO": "equity_broad",
    "XUS.TO": "equity_broad", "ZUQ.TO": "equity_broad",
}

FUND_NAMES = {
    # US funds
    "SPY": "SPDR S&P 500 ETF Trust",
    "QQQ": "Invesco QQQ Trust (Nasdaq-100)",
    "DIA": "SPDR Dow Jones Industrial ETF",
    "IWM": "iShares Russell 2000 ETF",
    "VTI": "Vanguard Total Stock Market ETF",
    "VOO": "Vanguard S&P 500 ETF",
    "ARKK": "ARK Innovation ETF",
    "GLD": "SPDR Gold Shares",
    "TLT": "iShares 20+ Year Treasury Bond ETF",
    "EFA": "iShares MSCI EAFE ETF",
    "EEM": "iShares MSCI Emerging Markets ETF",
    "VNQ": "Vanguard Real Estate ETF",
    "XLF": "Financial Select Sector SPDR Fund",
    "XLK": "Technology Select Sector SPDR Fund",
    "XLE": "Energy Select Sector SPDR Fund",
    "SCHD": "Schwab US Dividend Equity ETF",
    "VIG": "Vanguard Dividend Appreciation ETF",
    "BND": "Vanguard Total Bond Market ETF",
    "IAU": "iShares Gold Trust",
    "PDBC": "Invesco Optimum Yield Diversified Commodity Strategy ETF",
    # US sector ETFs
    "XLV": "Health Care Select Sector SPDR Fund",
    "XLU": "Utilities Select Sector SPDR Fund",
    "XLP": "Consumer Staples Select Sector SPDR Fund",
    "XLY": "Consumer Discretionary Select Sector SPDR Fund",
    "XLI": "Industrial Select Sector SPDR Fund",
    # Canadian funds
    "XIU.TO": "iShares S&P/TSX 60 Index ETF",
    "XIC.TO": "iShares Core S&P/TSX Composite ETF",
    "VCN.TO": "Vanguard FTSE Canada All Cap Index ETF",
    "HXT.TO": "Horizons S&P/TSX 60 Index ETF",
    "XEQT.TO": "iShares Core Equity ETF Portfolio",
    "XGRO.TO": "iShares Core Growth ETF Portfolio",
    "VGRO.TO": "Vanguard Growth ETF Portfolio",
    "VBAL.TO": "Vanguard Balanced ETF Portfolio",
    "ZSP.TO": "BMO S&P 500 Index ETF (CAD)",
    "XDV.TO": "iShares Canadian Select Dividend Index ETF",
    "ZLB.TO": "BMO Low Volatility Canadian Equity ETF",
    "XEF.TO": "iShares Core MSCI EAFE IMI Index ETF",
    "ZAG.TO": "BMO Aggregate Bond Index ETF",
    "XBB.TO": "iShares Core Canadian Universe Bond Index ETF",
    "ZEB.TO": "BMO Equal Weight Banks Index ETF",
    "XFN.TO": "iShares S&P/TSX Capped Financials Index ETF",
    "XRE.TO": "iShares S&P/TSX Capped REIT Index ETF",
    "TEC.TO": "TD Global Technology Leaders Index ETF",
    "ZGD.TO": "BMO Equal Weight Global Gold Index ETF",
    "ZQQ.TO": "Horizons NASDAQ-100 Index ETF",
    "VGG.TO": "Vanguard US Dividend Growth ETF (CAD Hedged)",
    "XUS.TO": "iShares Core S&P 500 Index ETF (CAD)",
    "ZUQ.TO": "BMO MSCI USA Quality Factor ETF",
}

# Currency for each fund — used to set default display in the UI
FUND_CURRENCY = {t: "CAD" for t in FUND_NAMES if t.endswith(".TO")}
# All others default to USD (handled by the fallback in consumers)

EQUITY_CATS = {"equity_broad", "growth_tech", "small_cap", "international", "real_estate", "financials"}
SAFE_HAVEN_CATS = {"commodities", "fixed_income"}


def score_macro_environment(ticker: str, macro_data: dict, fear_greed: dict = None) -> dict:
    category = FUND_CATEGORIES.get(ticker, "equity_broad")
    signals = []
    score = 50.0

    vix_data = macro_data.get("vix")
    fed_data = macro_data.get("fed_funds_rate")
    cpi_data = macro_data.get("cpi")
    unrate_data = macro_data.get("unemployment")
    yield_data = macro_data.get("yield_curve")
    gdp_data = macro_data.get("gdp")

    # --- VIX ---
    if vix_data:
        vix = vix_data["latest"]
        if vix < 20:
            if category in EQUITY_CATS:
                score += 15
                signals.append({"signal": f"VIX={vix:.1f} (low fear)", "direction": "bullish", "impact": +15})
            elif category in SAFE_HAVEN_CATS:
                score -= 5
                signals.append({"signal": f"VIX={vix:.1f} (low fear)", "direction": "bearish", "impact": -5})
        elif vix > 30:
            if category in EQUITY_CATS - {"financials"}:
                score -= 20
                signals.append({"signal": f"VIX={vix:.1f} (high fear)", "direction": "bearish", "impact": -20})
            elif category in SAFE_HAVEN_CATS:
                score += 20
                signals.append({"signal": f"VIX={vix:.1f} (flight to safety)", "direction": "bullish", "impact": +20})

    # --- CNN Fear & Greed ---
    if fear_greed and fear_greed.get("available"):
        fg = fear_greed["score"]
        rating = fear_greed.get("rating", "neutral")
        if fg <= 25:  # Extreme Fear
            if category in SAFE_HAVEN_CATS:
                score += 15
                signals.append({"signal": f"Fear & Greed={fg:.0f} (extreme fear)", "direction": "bullish", "impact": +15})
            elif category in EQUITY_CATS:
                score -= 10
                signals.append({"signal": f"Fear & Greed={fg:.0f} (extreme fear)", "direction": "bearish", "impact": -10})
        elif fg <= 40:  # Fear
            if category in SAFE_HAVEN_CATS:
                score += 7
                signals.append({"signal": f"Fear & Greed={fg:.0f} (fear)", "direction": "bullish", "impact": +7})
        elif fg >= 75:  # Extreme Greed — may signal overbought
            if category in EQUITY_CATS:
                score += 5
                signals.append({"signal": f"Fear & Greed={fg:.0f} (extreme greed)", "direction": "bullish", "impact": +5})
        elif fg >= 60:  # Greed
            if category in EQUITY_CATS:
                score += 8
                signals.append({"signal": f"Fear & Greed={fg:.0f} (greed)", "direction": "bullish", "impact": +8})

    # --- Yield Curve ---
    if yield_data:
        yc = yield_data["latest"]
        if yc > 0:
            if category in EQUITY_CATS - {"financials"}:
                score += 10
                signals.append({"signal": f"Yield curve={yc:.2f}% (normal)", "direction": "bullish", "impact": +10})
            elif category == "financials":
                score += 15
                signals.append({"signal": f"Yield curve={yc:.2f}% (normal)", "direction": "bullish", "impact": +15})
        else:
            if category == "fixed_income":
                score += 15
                signals.append({"signal": f"Yield curve={yc:.2f}% (inverted)", "direction": "bullish", "impact": +15})
            elif category in EQUITY_CATS:
                score -= 10
                signals.append({"signal": f"Yield curve={yc:.2f}% (inverted)", "direction": "bearish", "impact": -10})

    # --- Fed Funds Rate ---
    if fed_data and fed_data.get("3m_ago") is not None:
        current_fed = fed_data["latest"]
        three_mo = fed_data["3m_ago"]
        if current_fed > three_mo + 0.1:
            if category == "commodities":
                score += 10
                signals.append({"signal": f"Fed rate rising ({three_mo:.2f}→{current_fed:.2f}%)", "direction": "bullish", "impact": +10})
            elif category == "fixed_income":
                score -= 15
                signals.append({"signal": f"Fed rate rising ({three_mo:.2f}→{current_fed:.2f}%)", "direction": "bearish", "impact": -15})
            elif category == "financials":
                score += 10
                signals.append({"signal": f"Fed rate rising ({three_mo:.2f}→{current_fed:.2f}%)", "direction": "bullish", "impact": +10})
        elif current_fed < three_mo - 0.1:
            if category == "fixed_income":
                score += 15
                signals.append({"signal": f"Fed rate falling ({three_mo:.2f}→{current_fed:.2f}%)", "direction": "bullish", "impact": +15})
            elif category == "growth_tech":
                score += 10
                signals.append({"signal": f"Fed rate falling ({three_mo:.2f}→{current_fed:.2f}%)", "direction": "bullish", "impact": +10})

    # --- CPI ---
    if cpi_data and cpi_data.get("previous") is not None:
        cpi_now = cpi_data["latest"]
        cpi_prev = cpi_data["previous"]
        if cpi_now > cpi_prev:
            if category == "commodities":
                score += 15
                signals.append({"signal": f"CPI rising ({cpi_prev:.1f}→{cpi_now:.1f})", "direction": "bullish", "impact": +15})
            elif category == "fixed_income":
                score -= 10
                signals.append({"signal": f"CPI rising (inflation pressure)", "direction": "bearish", "impact": -10})

    # --- Unemployment ---
    if unrate_data and unrate_data.get("previous") is not None:
        ur_now = unrate_data["latest"]
        ur_prev = unrate_data["previous"]
        if ur_now > ur_prev + 0.1:
            if ticker in ("VIG", "SCHD"):
                score += 10
                signals.append({"signal": f"Unemployment rising ({ur_prev:.1f}→{ur_now:.1f}%)", "direction": "bullish", "impact": +10})
            elif category == "small_cap":
                score -= 10
                signals.append({"signal": f"Unemployment rising ({ur_prev:.1f}→{ur_now:.1f}%)", "direction": "bearish", "impact": -10})

    # --- GDP ---
    if gdp_data and gdp_data.get("latest") is not None and gdp_data.get("previous") is not None:
        gdp_now = gdp_data["latest"]
        gdp_prev = gdp_data["previous"]
        if gdp_now > gdp_prev:
            if category in ("equity_broad", "small_cap"):
                score += 10
                signals.append({"signal": f"GDP growth ({gdp_prev:.0f}→{gdp_now:.0f}B)", "direction": "bullish", "impact": +10})

    macro_score = float(np.clip(score, 0, 100))

    return {
        "vix": vix_data["latest"] if vix_data else None,
        "fed_funds_rate": fed_data["latest"] if fed_data else None,
        "cpi": cpi_data["latest"] if cpi_data else None,
        "unemployment": unrate_data["latest"] if unrate_data else None,
        "yield_curve": yield_data["latest"] if yield_data else None,
        "gdp": gdp_data["latest"] if gdp_data else None,
        "fear_greed_score": fear_greed["score"] if fear_greed and fear_greed.get("available") else None,
        "fear_greed_rating": fear_greed["rating"] if fear_greed and fear_greed.get("available") else None,
        "macro_score": round(macro_score, 2),
        "triggered_signals": signals,
    }
