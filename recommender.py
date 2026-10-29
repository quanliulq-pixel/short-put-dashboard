# -*- coding: utf-8 -*-
"""
Weekly Dynamic Short Put Quantitative Scoring & Recommendation Engine (v2 Institutional Audit Upgrade).
Covers:
- US Stocks & ETFs (us_stk)
- US Futures (us_fut)
- China Futures & CFFEX Index Options (cn_fut)

Key Institutional Upgrades:
1. Multi-timeframe Trend Regime Classification (MA5/MA20/MA60/MA120 + Slopes) to eliminate Bear-Channel Grinding Traps.
2. Smooth Continuous Cost-Floor Valuation + Dynamic Cost × Trend Matrix (eliminating step-function cliffs & static cost lag).
3. Non-circular Implied Volatility & True VRP (IV - HV20) + Risk-Adjusted Carry (ATR Buffer Multiple & Return-to-Vol Ratio).
4. Bollinger Band-Walk Breakdown Filter + Right-side Candlestick Stabilization check.
5. 4-Tier Option Chain Liquidity & Bid-Ask Slippage Scoring (spanning 4.2 to 10.0 pts).
6. US Single-Stock Quarterly Earnings Window Gap-Risk Detection & Penalty.
7. Hard Risk Circuit Breakers (Falling Knife Cap, Bear Channel Cap, Parabolic Bubble Top Cap).
"""
from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from data_engine import (
    ensure_all_bars_loaded,
    get_instrument_bars,
    get_macro_vol_regime,
    get_real_iv_map,
)
from http_utils import cached, get_week_context, load_pickle, now_bj, save_pickle
from options_math import build_payoff_curve, build_put_tiers
from universe import ALL_INSTRUMENTS, get_instrument

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Option Chain Liquidity & Bid-Ask Slippage Tiers (0 - 10 scale anchor)
# ---------------------------------------------------------------------------
_OPT_LIQUIDITY_TIER: Dict[str, Tuple[str, float]] = {
    # S+ Tier (9.6 - 10.0): Ultra-tight bid-ask (<0.5%), massive institutional open interest
    "SPY": ("S+ 极高流动(点差极窄)", 9.9),
    "QQQ": ("S+ 极高流动(点差极窄)", 9.9),
    "IWM": ("S+ 极高流动(点差极窄)", 9.6),
    "TLT": ("S+ 极高流动(点差极窄)", 9.6),
    "GLD": ("S+ 极高流动(点差极窄)", 9.6),
    "NVDA": ("S+ 极高流动(全美第一)", 9.9),
    "AAPL": ("S+ 极高流动(点差1美分)", 9.8),
    "MSFT": ("S+ 极高流动(点差极窄)", 9.7),
    "AMZN": ("S+ 极高流动(点差1美分)", 9.7),
    "META": ("S+ 极高流动(深度极佳)", 9.6),
    "TSLA": ("S+ 极高流动(期权之王)", 9.6),
    "GOOGL": ("S+ 极高流动(点差极窄)", 9.6),
    "AMD": ("S+ 极高流动(交投极活跃)", 9.4),
    "ES=F": ("S+ 全球股指期权核心", 9.9),
    "NQ=F": ("S+ 纳指期权主力", 9.7),
    "GC=F": ("S+ COMEX期金主力", 9.6),
    "CL=F": ("S+ NYMEX原油主力", 9.6),
    "ZN=F": ("S+ 美债期权主力", 9.5),
    "IM0": ("S+ 中金所MO极高流动", 9.7),
    "IF0": ("S+ 中金所IO蓝筹主力", 9.7),
    "IH0": ("S+ 中金所HO核心宽基", 9.5),
    "M0": ("S+ 国内商品期权标杆", 9.6),
    "AU0": ("S+ 上期所沪金极活跃", 9.5),
    "AG0": ("S+ 上期所沪银极活跃", 9.4),
    "SR0": ("S+ 郑商所白糖主力", 9.3),
    "TA0": ("S+ 郑商所PTA主力", 9.3),
    # A Tier (7.6 - 8.8): Liquid primary contracts, narrow spread (~1%)
    "SMH": ("A 高流动性(ETF主力)", 8.8),
    "IBIT": ("A 高流动性(期权活跃)", 8.5),
    "AVGO": ("A 高流动性(拆股后活跃)", 8.7),
    "TSM": ("A 高流动性(ADR主力)", 8.7),
    "MU": ("A 高流动性(存储龙头)", 8.3),
    "NFLX": ("A 高流动性(科技蓝筹)", 8.5),
    "PLTR": ("A 高流动性(散户/机构活跃)", 8.5),
    "BRK-B": ("A 稳健流动性(价值锚)", 8.6),
    "JPM": ("A 高流动性(金融龙头)", 8.6),
    "XOM": ("A 高流动性(能源蓝筹)", 8.5),
    "BABA": ("A 高流动性(中概期权王)", 8.3),
    "PDD": ("A 高流动性(中概活跃)", 8.2),
    "SI=F": ("A COMEX白银主力", 8.6),
    "HG=F": ("A COMEX铜期权", 8.2),
    "NG=F": ("A NYMEX天然气期权", 8.5),
    "ZS=F": ("A CBOT大豆期权", 8.5),
    "ZC=F": ("A CBOT玉米期权", 8.4),
    "CU0": ("A 上期所沪铜主力", 8.8),
    "AL0": ("A 上期所沪铝主力", 8.5),
    "RB0": ("A 上期所螺纹主力", 8.7),
    "I0": ("A 大商所铁矿主力", 8.6),
    "MA0": ("A 郑商所甲醇主力", 8.5),
    "SA0": ("A 郑商所纯碱期权", 8.3),
    "FG0": ("A 郑商所玻璃期权", 8.1),
    "RM0": ("A 郑商所菜粕主力", 8.2),
    "Y0": ("A 大商所豆油主力", 8.2),
    "P0": ("A 大商所棕榈油主力", 8.2),
    "C0": ("A 大商所玉米主力", 8.3),
    "CF0": ("A 郑商所棉花主力", 8.2),
    "LC0": ("A 广期所碳酸锂活跃", 8.1),
    # B Tier (5.8 - 7.2): Moderate liquidity, limit orders recommended
    "ASML": ("B 中等流动性(宜挂限价单)", 6.8),
    "COST": ("B 中等流动性(高单价蓝筹)", 7.2),
    "LLY": ("B 中等流动性(医药龙头)", 7.2),
    "BZ=F": ("B ICE布油期权(次于WTI)", 6.8),
    "ZW=F": ("B CBOT小麦期权", 6.8),
    "ZM=F": ("B CBOT豆粕期权", 6.5),
    "ZL=F": ("B CBOT豆油期权", 6.4),
    "SB=F": ("B ICE原糖期权", 6.6),
    "CT=F": ("B ICE美棉期权", 6.2),
    "ZN0": ("B 上期所沪锌期权", 6.8),
    "AO0": ("B 上期所氧化铝期权", 6.7),
    "SC0": ("B 上期能源原油期权", 7.0),
    "PP0": ("B 大商所PP期权", 6.6),
    "L0": ("B 大商所塑料期权", 6.7),
    "V0": ("B 大商所PVC期权", 6.5),
    "RU0": ("B 上期所天胶期权", 6.9),
    "UR0": ("B 郑商所尿素期权", 6.3),
    "SI0": ("B 广期所工业硅期权", 6.4),
    # C Tier (4.2 - 5.5): Thinner order book, watch bid-ask slippage
    "PL=F": ("C 盘口偏薄(注意买卖滑点)", 4.8),
    "KC=F": ("C 盘口偏薄(注意买卖滑点)", 5.0),
    "SM0": ("C 盘口偏薄(限价挂单)", 5.2),
    "SF0": ("C 盘口偏薄(限价挂单)", 5.0),
    "LH0": ("C 生猪期权盘口偏薄", 4.8),
}

# Approximate quarterly earnings reporting day-of-year windows for single US stocks
# Used to warn when a 30-DTE option crosses an imminent quarterly earnings report
_US_STK_EARNINGS_MONTH_DAYS: Dict[str, List[Tuple[int, int]]] = {
    # Fiscal calendar: (month, typical_day) for Q1, Q2, Q3, Q4 releases
    "AAPL": [(1, 30), (5, 2), (8, 1), (10, 31)],
    "MSFT": [(1, 29), (4, 25), (7, 30), (10, 29)],
    "GOOGL": [(1, 30), (4, 25), (7, 24), (10, 29)],
    "AMZN": [(2, 1), (4, 30), (8, 1), (10, 31)],
    "META": [(2, 1), (4, 24), (7, 31), (10, 30)],
    "TSLA": [(1, 24), (4, 23), (7, 23), (10, 23)],
    "NFLX": [(1, 21), (4, 18), (7, 18), (10, 17)],
    "AMD": [(1, 30), (4, 30), (7, 30), (10, 29)],
    "ASML": [(1, 24), (4, 17), (7, 17), (10, 16)],
    "TSM": [(1, 18), (4, 18), (7, 18), (10, 17)],
    "PLTR": [(2, 5), (5, 6), (8, 5), (11, 4)],
    "BRK-B": [(2, 24), (5, 4), (8, 3), (11, 2)],
    "JPM": [(1, 14), (4, 12), (7, 12), (10, 11)],
    "LLY": [(2, 6), (4, 30), (8, 8), (10, 30)],
    "XOM": [(2, 2), (4, 26), (8, 2), (11, 1)],
    # Off-cycle fiscal reporters (NVDA, AVGO, MU, COST, BABA, PDD)
    "NVDA": [(2, 24), (5, 24), (8, 26), (11, 20)],
    "AVGO": [(3, 7), (6, 12), (9, 5), (12, 12)],
    "MU": [(3, 20), (6, 26), (9, 25), (12, 18)],
    "COST": [(3, 7), (5, 30), (9, 26), (12, 12)],
    "BABA": [(2, 7), (5, 14), (8, 15), (11, 15)],
    "PDD": [(3, 20), (5, 22), (8, 26), (11, 21)],
}


def _fetch_real_earnings_dates() -> Dict[str, List[str]]:
    """
    Fetch upcoming earnings dates from Yahoo via yfinance (if installed & reachable).
    Result is cached in memory (6h) and on disk (24h). Returns {symbol: ["YYYY-MM-DD", ...]}.
    Any failure silently falls back to the approximate calendar table above.
    """

    def _load() -> Dict[str, List[str]]:
        disk = load_pickle("earnings_dates_v1.pkl", max_age_sec=86400.0)
        if isinstance(disk, dict) and disk:
            return disk
        try:
            import yfinance as yf  # optional dependency
        except Exception:
            return {}

        def _one(sym: str) -> Tuple[str, List[str]]:
            try:
                cal = yf.Ticker(sym).calendar
                raw = cal.get("Earnings Date") if isinstance(cal, dict) else None
                if not raw:
                    return sym, []
                if not isinstance(raw, (list, tuple)):
                    raw = [raw]
                return sym, [str(x)[:10] for x in raw if x]
            except Exception:
                return sym, []

        out: Dict[str, List[str]] = {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            for sym, dates in pool.map(_one, list(_US_STK_EARNINGS_MONTH_DAYS.keys())):
                if dates:
                    out[sym] = dates
        if out:
            save_pickle("earnings_dates_v1.pkl", out)
        return out

    try:
        return cached("earnings_dates", 6 * 3600.0, _load)
    except Exception:
        return {}


def _check_earnings_risk(inst: Dict[str, Any], asof_str: str, target_dte: int) -> Optional[Dict[str, Any]]:
    """
    Detect if a single US stock has a quarterly earnings report within the option's DTE window.
    Priority: real Yahoo earnings date -> approximate fiscal calendar fallback.
    """
    if inst["market"] != "us_stk":
        return None
    sym = inst["symbol"]
    schedule = _US_STK_EARNINGS_MONTH_DAYS.get(sym)
    if not schedule:
        return None
    try:
        cur_dt = datetime.strptime(asof_str[:10], "%Y-%m-%d").date()
    except Exception:
        cur_dt = datetime.now().date()

    candidates: List[date] = []
    source = "估算"
    real_dates = _fetch_real_earnings_dates().get(sym) or []
    for ds in real_dates:
        try:
            candidates.append(datetime.strptime(ds, "%Y-%m-%d").date())
        except ValueError:
            continue
    if candidates:
        source = "Yahoo"
    else:
        for y in (cur_dt.year, cur_dt.year + 1):
            for m, d in schedule:
                # Clamp to the real last day of the month (not a fixed 28th)
                last_day = calendar.monthrange(y, m)[1]
                candidates.append(date(y, m, min(d, last_day)))

    best_days = 999
    best_date_str = ""
    for ed in candidates:
        diff = (ed - cur_dt).days
        if 0 <= diff <= target_dte and diff < best_days:
            best_days = diff
            best_date_str = ed.strftime("%m-%d")

    if 0 <= best_days <= target_dte:
        # Gap-risk discount: stronger if earnings is within 12 days
        penalty = 4.5 if best_days <= 12 else 2.5
        day_txt = "今日" if best_days == 0 else f"{best_days} 天后"
        return {
            "inWindow": True,
            "daysToEarnings": best_days,
            "estDate": best_date_str,
            "source": source,
            "penalty": penalty,
            "warning": f"⚠️ 跨财报期预警（{source}日期 {best_date_str} 披露季报，{day_txt}）：防财报跳空已折价 -{penalty:g}分，已自动切换保守档",
        }
    return None


def _sma(vals: List[float], n: int) -> Optional[float]:
    if len(vals) < n or n <= 0:
        return None
    return sum(vals[-n:]) / float(n)


def _std(vals: List[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    var = sum((x - m) ** 2 for x in vals) / (len(vals) - 1)
    return math.sqrt(max(0.0, var))


def _rsi14(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = 0.0
    losses = 0.0
    start = max(1, len(closes) - period * 3)
    for i in range(start, start + period):
        if i >= len(closes):
            break
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_g = gains / period
    avg_l = losses / period
    for i in range(start + period, len(closes)):
        diff = closes[i] - closes[i - 1]
        g = max(0.0, diff)
        l = max(0.0, -diff)
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
    if avg_l <= 1e-9:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1.0 + rs))


def _atr14(bars: List[Dict[str, Any]], period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs: List[float] = []
    sub = bars[-(period + 15) :]
    for i in range(1, len(sub)):
        h = sub[i]["h"]
        l = sub[i]["l"]
        pc = sub[i - 1]["c"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if not trs:
        return 0.0
    win = trs[-period:]
    return sum(win) / len(win)


def _realized_vol(closes: List[float], window: int = 20) -> float:
    if len(closes) < window + 1:
        return 0.22
    sub = closes[-(window + 1) :]
    log_rets: List[float] = []
    for i in range(1, len(sub)):
        if sub[i - 1] > 0 and sub[i] > 0:
            r = math.log(sub[i] / sub[i - 1])
            # Filter continuous contract roll jump outliers (>28% single day)
            if abs(r) < 0.28:
                log_rets.append(r)
    if len(log_rets) < 5:
        return 0.22
    return max(0.06, min(_std(log_rets) * math.sqrt(252.0), 1.80))


def _hv_stats_1y(closes: List[float], cur_hv20: float) -> Tuple[float, float]:
    """Compute 1-year percentile rank (0-100) and 1-year median of 20-day realized volatility."""
    sub = closes[-265:]
    if len(sub) < 45:
        return 50.0, cur_hv20
    hvs: List[float] = []
    for end_idx in range(21, len(sub) + 1, 3):
        seg = sub[end_idx - 21 : end_idx]
        rets = [
            math.log(seg[j] / seg[j - 1])
            for j in range(1, len(seg))
            if seg[j - 1] > 0 and seg[j] > 0 and abs(math.log(seg[j] / seg[j - 1])) < 0.28
        ]
        if len(rets) >= 10:
            hvs.append(_std(rets) * math.sqrt(252.0))
    if not hvs:
        return 50.0, cur_hv20
    below = sum(1 for v in hvs if v <= cur_hv20)
    s_hvs = sorted(hvs)
    med_hv = s_hvs[len(s_hvs) // 2]
    return round((below / len(hvs)) * 100.0, 1), med_hv


def _price_percentile(closes: List[float], cur: float, years: int) -> float:
    n = years * 252
    sub = closes[-n:] if len(closes) >= n else closes
    if not sub:
        return 50.0
    below = sum(1 for x in sub if x <= cur)
    return round((below / len(sub)) * 100.0, 1)


def _ret_pct(closes: List[float], days: int) -> float:
    if len(closes) <= days:
        return 0.0
    base = closes[-days - 1]
    cur = closes[-1]
    if base <= 0:
        return 0.0
    return round(((cur / base) - 1.0) * 100.0, 2)


def _interp_linear(x: float, pts: List[Tuple[float, float]]) -> float:
    """Smooth piecewise-linear interpolation without step-function cliffs."""
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if x0 <= x <= x1:
            if abs(x1 - x0) < 1e-9:
                return y1
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return pts[-1][1]


def _calibrate_implied_vol(
    inst: Dict[str, Any],
    hv20: float,
    hv60: float,
    hv_med_1y: float,
    hv_rank: float,
    rsi14: float,
    ret_1w: float,
    macro_regime: Dict[str, Any],
    real_iv_entry: Optional[Dict[str, Any]] = None,
    earnings_in_window: bool = False,
) -> Tuple[float, float, float, str, bool]:
    """
    Hybrid Real-Market + De-circularized ATM Implied Volatility (IV), IV Rank, and VRP (IV - HV20):
    - Primary: Uses real option-chain / CBOE / CFFEX ATM IV when available (`is_real_iv = True`).
    - Fallback: Anchors structural IV to 1-year median HV, 60-day HV, and macro implied vol indices
      (`is_real_iv = False`, explicitly labeled `"⚪ 估算IV"` so synthetic VRP never inflates scores).
    """
    structural_hv = 0.40 * hv20 + 0.35 * hv60 + 0.25 * hv_med_1y
    mkt = inst["market"]
    sector = inst.get("sector", "")

    vix = float(macro_regime.get("vix") or 18.5) / 100.0
    vxn = float(macro_regime.get("vxn") or 22.0) / 100.0
    ovx = float(macro_regime.get("ovx") or 34.0) / 100.0
    gvz = float(macro_regime.get("gvz") or 17.5) / 100.0

    real_ok = bool(real_iv_entry and 0.04 < float(real_iv_entry.get("atmIv", 0.0)) < 1.80)
    stale_quote = False
    if real_ok and "期权链" in str(real_iv_entry.get("ivSource", "")):
        # Sanity guard for single-name chain quotes (off-hours stale mids / wide spreads):
        # reject if IV > 1.6x realized vol (2.2x when an earnings event sits inside the window).
        rv_ref = max(hv20, hv60, 0.10)
        ratio_cap = 2.2 if earnings_in_window else 1.6
        if float(real_iv_entry["atmIv"]) > rv_ref * ratio_cap:
            real_ok = False
            stale_quote = True

    if real_ok:
        atm_iv = float(real_iv_entry["atmIv"])
        iv_source = str(real_iv_entry.get("ivSource") or "🟢 实盘IV")
        is_real_iv = True
    else:
        vrp_mult = 1.14
        regime_anchor = structural_hv

        if mkt == "us_stk":
            if inst["symbol"] == "SPY":
                regime_anchor = vix
                vrp_mult = 1.06
            elif inst["symbol"] == "QQQ":
                regime_anchor = vxn
                vrp_mult = 1.06
            elif sector in ("AI/半导体", "科技巨头"):
                regime_anchor = 0.55 * structural_hv + 0.45 * (vxn * 1.22)
                vrp_mult = 1.15
            else:
                regime_anchor = 0.60 * structural_hv + 0.40 * (vix * 1.10)
                vrp_mult = 1.13
        elif mkt == "us_fut":
            if sector == "能源":
                regime_anchor = 0.50 * structural_hv + 0.50 * ovx
                vrp_mult = 1.14
            elif sector == "贵金属":
                regime_anchor = 0.55 * structural_hv + 0.45 * gvz
                vrp_mult = 1.12
            elif inst["symbol"] == "ES=F":
                regime_anchor = vix
                vrp_mult = 1.05
            elif inst["symbol"] == "NQ=F":
                regime_anchor = vxn
                vrp_mult = 1.05
            else:
                regime_anchor = structural_hv
                vrp_mult = 1.13
        else:  # cn_fut
            if sector == "股指期权":
                regime_anchor = 0.70 * structural_hv + 0.30 * max(vix, 0.20)
                vrp_mult = 1.16
            else:
                regime_anchor = structural_hv
                vrp_mult = 1.13

        # Moderate fear skew expansion on pullbacks, capped to avoid synthetic runaway
        fear_bump = 0.0
        if -8.5 <= ret_1w < -2.0:
            fear_bump += min(0.045, abs(ret_1w) * 0.006)
        elif ret_1w < -8.5:
            fear_bump += 0.050
        if 28.0 <= rsi14 < 42.0:
            fear_bump += (42.0 - rsi14) * 0.0012

        atm_iv = (0.55 * structural_hv + 0.45 * regime_anchor) * vrp_mult + fear_bump
        atm_iv = max(0.08, min(atm_iv, 1.45))
        iv_source = "⚪ 估算IV(期权链报价异常已剔除)" if stale_quote else "⚪ 估算IV"
        is_real_iv = False

    # Variance Risk Premium: ATM IV minus 20-day realized volatility
    vrp_pts = (atm_iv - hv20) * 100.0

    # IV Rank blends HV rank with current IV/HV_median ratio
    iv_vs_med = (atm_iv / max(hv_med_1y, 0.08)) - 1.0
    iv_rank = min(99.0, max(5.0, hv_rank * 0.72 + 22.0 + iv_vs_med * 35.0))
    return atm_iv, round(iv_rank, 1), round(vrp_pts, 1), iv_source, is_real_iv


def _classify_trend_regime(
    inst: Dict[str, Any],
    spot: float,
    ma5: float,
    ma20: float,
    ma60: float,
    ma120: float,
    ma20_slope_pct: float,
    ma60_slope_pct: float,
    boll_low: float,
    low_20d: float,
    chg_1d: float,
    ret_1w: float,
    ret_1m: float,
    rsi: float,
    stab_signals: Optional[Dict[str, bool]] = None,
) -> Tuple[str, float, float]:
    """
    Classify multi-timeframe trend structure into institutional regimes.
    Returns (trend_regime_label, trend_score_0_to_15, bear_channel_discount).

    stab_signals (right-side stabilization confirmations, need >= 2 of 3):
      - above_ma5_2d:  last 2 closes both above their MA5
      - higher_low:    the 20-day low was set >= 5 sessions ago and recent 5-day lows are higher
      - rsi_recover:   RSI back >= 35 and rising vs. 3 sessions ago
    """
    stab_signals = stab_signals or {}
    n_confirm = sum(1 for v in stab_signals.values() if v)

    # 1. Active falling knife / breakdown below Bollinger lower band
    if (ret_1w < -8.0 and chg_1d < -1.8) or (spot < boll_low * 0.995 and chg_1d < -1.5 and ret_1w < -5.5):
        return "破位急跌飞刀", 3.0, -6.0

    # 2. Bear-Trend Alignment Check (spot < MA20 < MA60 and MA60 sloping down)
    is_bear_alignment = (spot < ma20 * 0.998) and (ma20 < ma60 * 0.995) and (ma60_slope_pct < -0.8)
    if is_bear_alignment and ret_1m < -4.0:
        # Stabilization requires at least 2 independent confirmations AND price off the 20D low.
        # (Same rule for every asset class; no discretionary "policy support" exemption.)
        if n_confirm >= 2 and spot >= low_20d * 1.015:
            return "空头超跌初企稳", 9.5, -2.0
        # Pure grinding bear market: strictly cap trend_score and apply bear channel discount!
        return "空头阴跌通道", 5.5, -6.5

    # 3. Healthy Pullback in Primary Uptrend (多头趋势回踩支撑: MA60 rising/flat, spot pulling back near MA20/MA60)
    if ma60_slope_pct >= -0.5 and ma20 >= ma60 * 0.985:
        if -7.0 <= ret_1w <= 1.2 and spot >= ma60 * 0.965 and 30.0 <= rsi <= 55.0:
            return "多头趋势回调甜点", 14.5, 0.0
        if spot >= ma20 and rsi <= 64.0:
            return "多头上升通道", 13.0, 0.0
        if spot >= ma20 and rsi > 64.0:
            return "多头高位偏热", 10.2, 0.0

    # 4. Confirmed Right-Side Bottoming Consolidation (底部企稳筑底)
    if spot >= low_20d * 1.012 and abs(ma20_slope_pct) <= 1.8 and -4.5 <= ret_1w <= 3.0:
        if spot >= ma20 * 0.99 or (spot >= ma5 and chg_1d >= -0.3):
            return "底部企稳筑底", 13.5, 0.0

    # 5. Moderate pullback testing lower support without structural bear breakdown
    if -6.5 <= ret_1w < 0.0 and chg_1d >= -0.8 and spot >= boll_low:
        return "回调测试支撑", 11.8, 0.0

    return "区间宽幅震荡", 10.5, 0.0


def analyze_single_instrument(
    inst: Dict[str, Any],
    bars: List[Dict[str, Any]],
    macro_regime: Dict[str, Any],
    target_dte: int = 30,
    real_iv_entry: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not bars or len(bars) < 35:
        return None

    dp = int(inst.get("dp", 2))
    closes = [b["c"] for b in bars]
    spot = float(closes[-1])
    prev = float(closes[-2]) if len(closes) > 1 else spot
    chg_1d = ((spot - prev) / prev * 100.0) if prev > 0 else 0.0

    ret_1w = _ret_pct(closes, 5)
    ret_1m = _ret_pct(closes, 21)
    ret_3m = _ret_pct(closes, 63)
    ret_1y = _ret_pct(closes, 252)

    ma5 = _sma(closes, 5) or spot
    ma20 = _sma(closes, 20) or spot
    ma60 = _sma(closes, 60) or spot
    ma120 = _sma(closes, 120) or ma60

    # Compute 20-day slopes of MA20 and MA60 to detect trend direction & band-walk
    ma20_prev20 = _sma(closes[:-20], 20) if len(closes) > 40 else ma20
    ma60_prev20 = _sma(closes[:-20], 60) if len(closes) > 80 else ma60
    ma20_slope_pct = (((ma20 / ma20_prev20) - 1.0) * 100.0) if (ma20_prev20 and ma20_prev20 > 0) else 0.0
    ma60_slope_pct = (((ma60 / ma60_prev20) - 1.0) * 100.0) if (ma60_prev20 and ma60_prev20 > 0) else 0.0

    sd20 = _std(closes[-20:])
    boll_up = ma20 + 2.0 * sd20
    boll_low = max(spot * 0.5, ma20 - 2.0 * sd20)

    rsi = _rsi14(closes, 14)
    atr = _atr14(bars, 14)
    atr_pct = (atr / spot * 100.0) if spot > 0 else 1.5

    high_20d = max(b["h"] for b in bars[-20:])
    low_20d = min(b["l"] for b in bars[-20:])
    bars_52w = bars[-252:]
    high_52w = max(b["h"] for b in bars_52w)
    low_52w = min(b["l"] for b in bars_52w)
    dd_52w_pct = ((spot / high_52w) - 1.0) * 100.0 if high_52w > 0 else 0.0

    # Classic 20D Pivot supports S1 & S2
    pivot = (high_20d + low_20d + spot) / 3.0
    s1 = max(low_20d, 2.0 * pivot - high_20d)
    s2 = pivot - (high_20d - low_20d)

    pct_1y = _price_percentile(closes, spot, 1)
    pct_3y = _price_percentile(closes, spot, 3)
    pct_5y = _price_percentile(closes, spot, 5)

    hv20 = _realized_vol(closes, 20)
    hv60 = _realized_vol(closes, 60)
    hv_rank, hv_med_1y = _hv_stats_1y(closes, hv20)
    earnings_info = _check_earnings_risk(inst, bars[-1]["t"], target_dte)
    atm_iv, iv_rank, vrp_pts, iv_source, is_real_iv = _calibrate_implied_vol(
        inst, hv20, hv60, hv_med_1y, hv_rank, rsi, ret_1w, macro_regime,
        real_iv_entry=real_iv_entry,
        earnings_in_window=bool(earnings_info and earnings_info.get("inWindow")),
    )

    supports = {
        "ma20": round(ma20, dp),
        "ma60": round(ma60, dp),
        "ma120": round(ma120, dp),
        "bollLow": round(boll_low, dp),
        "bollUp": round(boll_up, dp),
        "low20d": round(low_20d, dp),
        "low52w": round(low_52w, dp),
        "high52w": round(high_52w, dp),
        "s1": round(s1, dp),
        "s2": round(s2, dp),
    }

    tiers = build_put_tiers(
        inst,
        spot,
        atm_iv,
        dte=target_dte,
        supports=supports,
        atr_pct=atr_pct,
        hv20=hv20,
        closes=closes,
    )
    bal_tier = tiers["balanced"]
    cons_tier = tiers["conservative"]
    agg_tier = tiers["aggressive"]

    # Right-side stabilization confirmations (used only inside bear alignment)
    above_ma5_2d = (
        len(closes) >= 7
        and closes[-1] > (_sma(closes, 5) or spot)
        and closes[-2] > (_sma(closes[:-1], 5) or closes[-2])
    )
    low_5d = min(b["l"] for b in bars[-5:])
    higher_low = low_5d > low_20d * 1.005
    rsi_3ago = _rsi14(closes[:-3], 14) if len(closes) > 20 else rsi
    rsi_recover = rsi >= 35.0 and rsi > rsi_3ago + 2.0
    stab_signals = {"above_ma5_2d": bool(above_ma5_2d), "higher_low": bool(higher_low), "rsi_recover": bool(rsi_recover)}

    # Classify Multi-Timeframe Trend Regime FIRST so Cost × Trend matrix can use it
    trend_regime, trend_score, bear_discount = _classify_trend_regime(
        inst=inst,
        stab_signals=stab_signals,
        spot=spot,
        ma5=ma5,
        ma20=ma20,
        ma60=ma60,
        ma120=ma120,
        ma20_slope_pct=ma20_slope_pct,
        ma60_slope_pct=ma60_slope_pct,
        boll_low=boll_low,
        low_20d=low_20d,
        chg_1d=chg_1d,
        ret_1w=ret_1w,
        ret_1m=ret_1m,
        rsi=rsi,
    )

    # Evaluate Cost / Fundamental Floor
    cost_cfg = inst.get("cost")
    cost_info: Optional[Dict[str, Any]] = None
    if cost_cfg:
        cash_c = float(cost_cfg["cash_cost"])
        prim_c = float(cost_cfg["primary_cost"])
        high_c = float(cost_cfg["comfort_high"])
        vs_prim = ((spot / prim_c) - 1.0) * 100.0
        vs_cash = ((spot / cash_c) - 1.0) * 100.0
        # Stale-anchor guard: a price that sits >10% BELOW the table's cash cost means the
        # cost data no longer reflects reality (upstream inputs fell / oversupply), not a hard floor.
        anchor_valid = vs_cash >= -10.0
        if not anchor_valid:
            c_status = f"成本锚失效·现价低于表中现金成本{abs(vs_cash):.0f}%(成本数据待更新)"
            c_tone = "neutral"
        elif spot <= cash_c * 1.02:
            if trend_regime == "空头阴跌通道":
                c_status = "破现金成本·过剩寻底期(防阴跌)"
                c_tone = "gold"
            else:
                c_status = "破现金成本·企稳减产铁底"
                c_tone = "bull"
        elif spot <= prim_c * 1.03:
            if trend_regime == "空头阴跌通道":
                c_status = "跌破完全成本·空头未止跌"
                c_tone = "gold"
            else:
                c_status = "跌破完全成本·亏损磨底企稳"
                c_tone = "bull"
        elif spot <= prim_c * 1.16:
            c_status = "贴近完全成本支撑带"
            c_tone = "gold"
        elif spot <= high_c:
            c_status = "覆盖成本·合理利润区"
            c_tone = "neutral"
        else:
            c_status = "高于成本激励上沿"
            c_tone = "bear"
        cost_info = {
            "cashCost": cash_c,
            "primaryCost": prim_c,
            "comfortHigh": high_c,
            "vsPrimaryPct": round(vs_prim, 1),
            "vsCashPct": round(vs_cash, 1),
            "anchorValid": anchor_valid,
            "status": c_status,
            "tone": c_tone,
            "label": cost_cfg.get("label", ""),
            "source": cost_cfg.get("source", ""),
        }

    # -----------------------------------------------------------------------
    # UPGRADED 5-FACTOR SHORT PUT QUANTITATIVE SCORING (0 - 100)
    # -----------------------------------------------------------------------
    # 1. Floor & Valuation Safety (0 - 30 pts) — Smooth Continuous Interpolation + Cost × Trend Matrix
    low_pct_blend = 0.45 * pct_3y + 0.55 * pct_5y
    if cost_info:
        vp = cost_info["vsPrimaryPct"]
        # Smooth continuous curve instead of step-function cliffs
        raw_cost_pts = _interp_linear(
            vp,
            [
                (-15.0, 28.5),
                (-5.0, 27.5),
                (2.0, 25.8),
                (12.0, 22.0),
                (25.0, 17.5),
                (45.0, 12.5),
                (65.0, 8.0),
            ],
        )
        # Historical 3Y/5Y percentile smooth adjustment (-3.5 to +3.0 pts)
        pct_adj = _interp_linear(low_pct_blend, [(10.0, 3.0), (30.0, 1.5), (55.0, 0.0), (85.0, -2.5), (95.0, -4.0)])
        if cost_info["anchorValid"]:
            floor_score = raw_cost_pts + pct_adj
        else:
            # Stale cost anchor -> neutral floor (only the historical percentile still counts)
            floor_score = 13.0 + pct_adj
            for _t in tiers.values():
                _t["anchorTags"] = [x for x in _t.get("anchorTags", []) if "成本" not in x]

        # Cost × Trend Matrix: if commodity is below/near static cost but still in a grinding bear channel,
        # discount static cost score to guard against raw-material cost deflation & oversupply traps!
        if trend_regime in ("空头阴跌通道", "破位急跌飞刀"):
            floor_score -= 4.2
        elif trend_regime == "空头超跌初企稳":
            floor_score -= 1.5
        floor_score = max(6.0, min(30.0, floor_score))

    elif inst.get("sector") == "股指期权":
        # Dedicated CFFEX Index Options (IM0/IF0/IH0) Valuation + Basis Cushion Model
        sym = inst["symbol"]
        basis_bonus = {"IM0": 5.5, "IF0": 5.0, "IH0": 5.2}.get(sym, 4.5)
        val_pts = _interp_linear(low_pct_blend, [(15.0, 18.5), (35.0, 16.5), (55.0, 14.0), (75.0, 11.0), (92.0, 7.5)])
        vs_ma60 = ((spot / ma60) - 1.0) * 100.0
        ma_pts = _interp_linear(abs(vs_ma60), [(0.0, 6.2), (4.0, 5.5), (10.0, 3.8), (18.0, 2.2)])
        floor_score = max(8.0, min(30.0, basis_bonus + val_pts + ma_pts))

    else:
        # US Stocks / ETFs / Financial Futures: Continuous Drawdown + 5Y Valuation Percentile + MA60 Support
        q_bonus = 4.2 if inst.get("quality_tier") == "S" else 2.2
        dd = abs(dd_52w_pct)
        # Smooth continuous drawdown curve (sweet spot is 6% - 22% pullback from 52W high)
        dd_pts = _interp_linear(
            dd,
            [
                (0.0, 12.5),
                (4.0, 15.5),
                (10.0, 18.2),
                (20.0, 17.8),
                (30.0, 14.2),
                (45.0, 9.5),
            ],
        )
        vs_ma60 = ((spot / ma60) - 1.0) * 100.0
        ma_pts = _interp_linear(vs_ma60, [(-15.0, 3.2), (-6.0, 6.2), (0.0, 6.8), (5.0, 5.5), (15.0, 3.0)])
        # Penalize stocks at extreme 5-year valuation highs with near-zero pullback
        val_adj = -2.5 if (low_pct_blend >= 88.0 and dd < 4.0) else (1.2 if low_pct_blend <= 35.0 else 0.0)
        floor_score = max(7.0, min(30.0, q_bonus + dd_pts + ma_pts + val_adj))

    # 2. Volatility Risk Premium & Risk-Adjusted Carry (0 - 25 pts)
    #    - 10 pts: IV Rank (0-6.5) + True VRP = IV - HV20 (0-3.5; capped at neutral 1.8 if estimated IV)
    #    - 9 pts:  Risk-Adjusted Return-to-Vol Ratio + Capped Yield
    #    - 6 pts:  ATR Safety Cushion Multiple (Breakeven Buffer / Daily ATR14)
    ivr_pts = _interp_linear(iv_rank, [(10.0, 2.5), (35.0, 4.2), (60.0, 5.6), (85.0, 6.5)])
    raw_vrp_score = _interp_linear(vrp_pts, [(-3.0, 0.5), (0.0, 1.5), (3.5, 2.8), (7.0, 3.5)])
    vrp_score_pts = raw_vrp_score if is_real_iv else min(1.8, raw_vrp_score)
    # Earnings event vol inside the window is jump risk, not a harvestable premium:
    # cap IVR & VRP sub-scores at neutral so pre-earnings IV inflation cannot offset the earnings penalty.
    if earnings_info and earnings_info.get("inWindow"):
        ivr_pts = min(ivr_pts, 4.2)
        vrp_score_pts = min(vrp_score_pts, 1.5)

    ret_to_vol = bal_tier["returnToVolRatio"]
    ann_ret = bal_tier["annReturnMarginPct"] if inst["market"] != "us_stk" else bal_tier["annReturnCashPct"]
    rtv_pts = _interp_linear(ret_to_vol, [(0.18, 2.0), (0.35, 3.8), (0.55, 5.0), (0.80, 5.5)])
    if inst["market"] == "us_stk":
        yield_pts = _interp_linear(ann_ret, [(5.0, 1.2), (12.0, 2.5), (22.0, 3.5)])
    else:
        yield_pts = _interp_linear(ann_ret, [(10.0, 1.2), (24.0, 2.6), (40.0, 3.5)])

    atr_mult = bal_tier["atrBufferMultiple"]
    atr_cushion_pts = _interp_linear(atr_mult, [(2.2, 1.2), (3.5, 3.2), (4.8, 5.0), (6.2, 6.0)])

    vol_score = max(4.0, min(25.0, round(ivr_pts + vrp_score_pts + rtv_pts + yield_pts + atr_cushion_pts, 1)))

    # 3. Technical Support, Stabilization & Anti-Band-Walk (0 - 20 pts)
    # Smooth RSI curve with right-side stabilization verification
    is_stabilizing = (chg_1d >= -0.5 and spot >= low_20d * 1.008) or (spot >= ma5 and chg_1d >= 0.0)
    base_rsi_pts = _interp_linear(
        rsi,
        [
            (18.0, 11.5),
            (28.0, 15.8),
            (38.0, 18.2),
            (48.0, 17.8),
            (58.0, 14.8),
            (68.0, 10.0),
            (78.0, 6.5),
        ],
    )
    if rsi < 33.0 and not is_stabilizing:
        # Oversold but still printing lower lows without bounce -> deduct knife risk
        base_rsi_pts -= 3.0
    elif 30.0 <= rsi <= 48.0 and is_stabilizing:
        base_rsi_pts += 1.0

    # Bollinger Lower Band bonus ONLY if not in a steep downward band-walk (ma20_slope_pct >= -1.8%)
    boll_bonus = 0.0
    if bal_tier["strike"] <= boll_low * 1.005:
        if ma20_slope_pct >= -1.5:
            boll_bonus = 1.8
        elif ma20_slope_pct >= -2.8:
            boll_bonus = 0.6
        else:
            boll_bonus = -1.0  # Band-walk breakdown penalty
    tech_score = max(5.0, min(20.0, round(base_rsi_pts + boll_bonus, 1)))

    # 4. Trend Health & Multi-Timeframe Structure (0 - 15 pts)
    trend_score = round(max(2.0, min(15.0, trend_score)), 1)

    # 5. Moat & Option Chain Liquidity Tier (0 - 10 pts, wide 4.8 - 9.9 range)
    liq_label, moat_score = _OPT_LIQUIDITY_TIER.get(
        inst["symbol"],
        ("A 主力活跃期权" if inst.get("quality_tier") == "S" else "B 中等流动性期权", 8.0 if inst.get("quality_tier") == "S" else 6.6),
    )

    # -----------------------------------------------------------------------
    # SYNTHESIS, EARNINGS GAP FILTER & HARD RISK CIRCUIT BREAKERS
    # -----------------------------------------------------------------------
    raw_total = floor_score + vol_score + tech_score + trend_score + moat_score + bear_discount

    risk_notes: List[str] = []
    if bear_discount < 0:
        risk_notes.append(f"空头趋势折价({bear_discount:+.1f}分)：均线空头向下未站稳MA20，严防破成本阴跌")
    stale_anchor = bool(cost_info and not cost_info.get("anchorValid", True))
    if stale_anchor:
        risk_notes.append(
            f"⚠️ 成本锚失效：现价低于表中现金成本 {abs(cost_info['vsCashPct']):.0f}%，成本数据可能已过时，"
            f"底部安全垫按中性计分，不再视为铁底"
        )

    if earnings_info and earnings_info.get("inWindow"):
        raw_total -= float(earnings_info["penalty"])
        risk_notes.append(earnings_info["warning"])

    # Hard Circuit Breakers (Institutional Score Caps)
    score_cap = 98.0
    if trend_regime == "破位急跌飞刀":
        score_cap = min(score_cap, 62.0)
        risk_notes.append("🛑 破位急跌熔断：周线重挫且未收复下轨，总分封顶62分，暂缓接刀")
    elif trend_regime == "空头阴跌通道":
        score_cap = min(score_cap, 73.5)
        risk_notes.append("⚠️ 空头通道限分：现价<MA20<MA60且月线阴跌，总分封顶73.5分，右侧企稳前仅限极深虚值")
    if pct_5y >= 92.0 and rsi >= 68.0:
        score_cap = min(score_cap, 68.0)
        risk_notes.append("⚠️ 历史极高分位过热熔断：5年分位>92%且RSI超买，总分封顶68分，防高位闪崩")

    total_score = round(max(18.0, min(score_cap, raw_total)), 1)

    # Choose optimal recommended tier for current market state
    if (
        (earnings_info and earnings_info.get("inWindow"))
        or stale_anchor
        or trend_regime in ("空头阴跌通道", "破位急跌飞刀")
        or rsi >= 65
        or pct_5y >= 84
        or hv20 >= 0.48
    ):
        rec_tier_key = "conservative"
    elif (
        inst["market"] == "us_stk"
        and inst.get("quality_tier") == "S"
        and trend_regime in ("多头趋势回调甜点", "底部企稳筑底")
        and rsi <= 44
        and dd_52w_pct <= -9
    ):
        rec_tier_key = "aggressive"
    else:
        rec_tier_key = "balanced"

    rec_tier = tiers[rec_tier_key]

    # Classify Strategy Archetype & Verdict Badge
    archetype, badge_tone, thesis_tags = _classify_archetype(
        inst=inst,
        spot=spot,
        rsi=rsi,
        pct_3y=pct_3y,
        pct_5y=pct_5y,
        dd_52w=dd_52w_pct,
        iv_rank=iv_rank,
        vrp_pts=vrp_pts,
        atr_mult=rec_tier["atrBufferMultiple"],
        trend_regime=trend_regime,
        earnings_info=earnings_info,
        cost_info=cost_info,
        total_score=total_score,
    )

    playbook = _build_weekly_playbook(
        inst=inst,
        spot=spot,
        rsi=rsi,
        pct_5y=pct_5y,
        iv_rank=iv_rank,
        vrp_pts=vrp_pts,
        hv20=hv20,
        iv_source=iv_source,
        is_real_iv=is_real_iv,
        trend_regime=trend_regime,
        liq_label=liq_label,
        risk_notes=risk_notes,
        cost_info=cost_info,
        supports=supports,
        tiers=tiers,
        rec_key=rec_tier_key,
        archetype=archetype,
        target_dte=target_dte,
    )

    return {
        "id": inst["id"],
        "symbol": inst["symbol"],
        "name": inst["name"],
        "sub": inst["sub"],
        "market": inst["market"],
        "marketLabel": {"us_stk": "美股/ETF", "us_fut": "美国期货", "cn_fut": "中国期货"}[inst["market"]],
        "sector": inst["sector"],
        "exchange": inst["exchange"],
        "unit": inst["unit"],
        "currency": inst["currency"],
        "dp": dp,
        "multiplier": inst["multiplier"],
        "price": round(spot, dp),
        "prevClose": round(prev, dp),
        "change1dPct": round(chg_1d, 2),
        "ret1wPct": ret_1w,
        "ret1mPct": ret_1m,
        "ret3mPct": ret_3m,
        "ret1yPct": ret_1y,
        "rsi14": round(rsi, 1),
        "atr14": round(atr, dp),
        "atrPct": round(atr_pct, 2),
        "pct1y": pct_1y,
        "pct3y": pct_3y,
        "pct5y": pct_5y,
        "drawdown52wPct": round(dd_52w_pct, 1),
        "hv20Pct": round(hv20 * 100.0, 1),
        "hv60Pct": round(hv60 * 100.0, 1),
        "atmIvPct": round(atm_iv * 100.0, 1),
        "ivSource": iv_source,
        "isRealIv": is_real_iv,
        "ivRank": iv_rank,
        "vrpPts": vrp_pts,
        "trendRegime": trend_regime,
        "liquidityLabel": liq_label,
        "earningsInfo": earnings_info,
        "riskNotes": risk_notes,
        "highCorrPeers": [],
        "supports": supports,
        "cost": cost_info,
        "moatNote": inst.get("moat_note", ""),
        "putScore": total_score,
        "scoreBreakdown": {
            "floor": round(floor_score, 1),     # /30
            "vol": round(vol_score, 1),         # /25
            "tech": round(tech_score, 1),       # /20
            "trend": round(trend_score, 1),     # /15
            "moat": round(moat_score, 1),       # /10
            "penalty": round(bear_discount - (float(earnings_info["penalty"]) if earnings_info else 0.0), 1),
        },
        "archetype": archetype,
        "badgeTone": badge_tone,
        "thesisTags": thesis_tags,
        "thesisSummary": playbook["whyNow"],
        "recommendedTierKey": rec_tier_key,
        "recommendedTier": rec_tier,
        "tiers": tiers,
        "playbook": playbook,
        "asof": bars[-1]["t"],
    }


def _classify_archetype(
    inst: Dict[str, Any],
    spot: float,
    rsi: float,
    pct_3y: float,
    pct_5y: float,
    dd_52w: float,
    iv_rank: float,
    vrp_pts: float,
    atr_mult: float,
    trend_regime: str,
    earnings_info: Optional[Dict[str, Any]],
    cost_info: Optional[Dict[str, Any]],
    total_score: float,
) -> Tuple[str, str, List[str]]:
    tags: List[str] = []
    mkt = inst["market"]

    if earnings_info and earnings_info.get("inWindow"):
        tags.append(f"⚠️ 距财报约{max(1, earnings_info['daysToEarnings'])}天")

    tags.append(trend_regime)

    if cost_info:
        vp = cost_info["vsPrimaryPct"]
        vc = cost_info["vsCashPct"]
        if not cost_info.get("anchorValid", True):
            tags.append("成本锚待更新")
        elif vc <= 2.0:
            tags.append("破现金成本铁底")
        elif vp <= 3.0:
            tags.append("跌破完全成本")
        elif vp <= 15.0:
            tags.append("贴近成本支撑")

    if atr_mult >= 5.0:
        tags.append(f"{atr_mult:.1f}倍ATR安全垫")
    elif pct_5y <= 25.0:
        tags.append(f"5年低分位({pct_5y:.0f}%)")
    elif mkt == "us_stk" and dd_52w <= -8.0:
        tags.append(f"距高点回调{dd_52w:.1f}%")

    if vrp_pts >= 3.5:
        tags.append(f"VRP溢价+{vrp_pts:.1f}%")
    elif iv_rank >= 60.0:
        tags.append(f"高IV溢价(IVR {iv_rank:.0f}%)")
    else:
        tags.append(f"IVR {iv_rank:.0f}%")

    if trend_regime == "破位急跌飞刀":
        return "破位急跌熔断 · 严禁盲目接刀(仅观察)", "neutral", tags[:4]
    if trend_regime == "空头阴跌通道":
        return "空头通道未止跌 · 仅限保守档深虚值观察", "neutral", tags[:4]
    if earnings_info and earnings_info.get("inWindow"):
        return f"跨季报窗口({earnings_info['estDate']}) · 防跳空建议选保守档", "neutral", tags[:4]
    if total_score < 66.0:
        return "高位或性价比偏弱 · 仅限极深虚值观察", "neutral", tags[:4]

    if inst.get("sector") == "股指期权":
        if inst["symbol"] == "IM0":
            tags.insert(0, "远月贴水保护")
            return "高隐波+贴水保护 · 急跌卖深虚值Put(MO)", "bull", tags[:4]
        if inst["symbol"] == "IF0":
            tags.insert(0, "宽基ETF托底")
            return "核心宽基估值底 · 顺势收租卖Put(IO)", "bull", tags[:4]
        if inst["symbol"] == "IH0":
            tags.insert(0, "高股息防御底")
            return "高股息央企护盘 · 稳健防御卖Put(HO)", "gold", tags[:4]

    anchor_ok = bool(cost_info and cost_info.get("anchorValid", True))
    if anchor_ok and cost_info["vsCashPct"] <= 3.0:
        return "破现金成本+企稳 · 深虚值铁底收租", "bull", tags[:4]
    if anchor_ok and cost_info["vsPrimaryPct"] <= 8.0:
        return "贴近产业成本+筑底 · 底部企稳卖Put", "bull", tags[:4]
    if cost_info and not anchor_ok:
        return "成本锚失效 · 仅按技术面保守档参考", "neutral", tags[:4]
    if mkt == "us_stk" and dd_52w <= -7.0 and rsi <= 48.0:
        return "核心龙头回调企稳 · 以接货之心卖Put", "bull", tags[:4]
    if iv_rank >= 62.0 and vrp_pts >= 3.0 and rsi <= 55.0:
        return "高VRP恐慌溢价 · 波动率均值回归收租", "gold", tags[:4]
    if mkt == "us_stk":
        return "慢牛均线支撑 · 现金担保收租(CSP)", "gold", tags[:4]
    return "多周期支撑保护 · 顺势虚值收租", "gold", tags[:4]


def _build_weekly_playbook(
    inst: Dict[str, Any],
    spot: float,
    rsi: float,
    pct_5y: float,
    iv_rank: float,
    vrp_pts: float,
    hv20: float,
    iv_source: str,
    is_real_iv: bool,
    trend_regime: str,
    liq_label: str,
    risk_notes: List[str],
    cost_info: Optional[Dict[str, Any]],
    supports: Dict[str, Any],
    tiers: Dict[str, Dict[str, Any]],
    rec_key: str,
    archetype: str,
    target_dte: int,
) -> Dict[str, Any]:
    rec = tiers[rec_key]
    cons = tiers["conservative"]
    agg = tiers["aggressive"]
    cur = inst["currency"]
    unit = inst["unit"]

    bsm_pop = rec.get("bsmPopPct", rec["popPct"])
    emp_pop = rec.get("empiricalPopPct", rec["popPct"])
    headline = (
        f"【{archetype}】推荐卖出 {target_dte}天到期、行权价 {cur}{rec['strike']:g} Put（{rec['label']}，"
        f"Delta {rec['delta']:.2f}），安全垫 {rec['otmPct']:.1f}%（合 {rec['atrBufferMultiple']:.1f} 倍日均ATR），"
        f"双轨取低胜率 {rec['popPct']:.1f}%（BSM肥尾 {bsm_pop:.1f}% / 5年历史实证 {emp_pop:.1f}%）。"
    )

    iv_note = (
        f"{iv_source}，实盘VRP {vrp_pts:+.1f}个百分点"
        if is_real_iv
        else f"{iv_source}，模型推算VRP {vrp_pts:+.1f}个百分点（已锁定中性VRP得分防虚高）"
    )

    if cost_info:
        why_now = (
            f"{inst['name']}现价 {spot:g} {unit}（趋势状态：【{trend_regime}】，近5年分位 {pct_5y:.1f}%，RSI {rsi:.1f}）。"
            f"产业锚方面，{cost_info['label']}约 {cost_info['primaryCost']:g} {unit}，现金成本约 {cost_info['cashCost']:g} {unit}，"
            f"现价相对完全成本 {cost_info['vsPrimaryPct']:+.1f}%（{cost_info['status']}）。"
            f"期权盘口评级为【{liq_label}】（{iv_note}）。{inst.get('moat_note', '')}"
        )
    else:
        why_now = (
            f"{inst['name']}现价 {cur}{spot:g}（趋势状态：【{trend_regime}】，RSI {rsi:.1f}，"
            f"20日历史波动率 {hv20*100:.1f}%，IV分位 {iv_rank:.0f}%，{iv_note}）。"
            f"技术面60日均线位于 {cur}{supports['ma60']:g}，布林下轨位于 {cur}{supports['bollLow']:g}，"
            f"期权流动性评级为【{liq_label}】。{inst.get('moat_note', '')}"
        )

    if inst["market"] == "us_stk":
        yield_str = (
            f"全额现金担保年化收益 {rec['annReturnCashPct']:.1f}%（单位波动收益比 {rec['returnToVolRatio']:.2f}，"
            f"Reg-T保证金口径年化 {rec['annReturnMarginPct']:.1f}%）"
        )
    else:
        yield_str = (
            f"交易所保证金口径年化收益 {rec['annReturnMarginPct']:.1f}%（名义本金口径年化 {rec['annReturnCashPct']:.1f}%，"
            f"单位波动收益比 {rec['returnToVolRatio']:.2f}）"
        )

    strike_logic = (
        f"主力推荐【{rec['label']}】行权价 {cur}{rec['strike']:g}：单张可收权利金约 {cur}{rec['contractPremium']:g} "
        f"（每单位 {rec['premium']:g}），盈亏平衡点低至 {cur}{rec['breakeven']:g}（需从现价下跌 {rec['breakevenBufferPct']:.1f}%、"
        f"相当于连续 {rec['atrBufferMultiple']:.1f} 个日均ATR波幅才开始实质亏损），"
        f"{yield_str}。若追求极致防穿仓可选【保守档】{cur}{cons['strike']:g}（胜率 {cons['popPct']:.1f}%，{cons['atrBufferMultiple']:.1f}倍ATR缓冲）；"
        f"若希望低位拿货建仓可选【进取档】{cur}{agg['strike']:g}。"
    )

    stop_px = round(rec["breakeven"] * 0.985, int(inst.get("dp", 2)))
    risk_prefix = f"【风控预警：{'；'.join(risk_notes)}】 " if risk_notes else ""
    risk_control = (
        f"{risk_prefix}"
        f"① 止盈规则：当权利金衰减至初始值的 25%~30%（已赚取70%+时间价值）时建议提前平仓锁定胜局；"
        f"② 展期/防御规则：若标的价格放量跌破行权价 {cur}{rec['strike']:g} 且逼近盈亏平衡点 {cur}{rec['breakeven']:g}，"
        f"切勿硬扛深实值伽马风险，可向后展期（Roll Out & Down）至下一月更低行权价，或以 {cur}{stop_px:g} 作为风控复核线；"
        f"③ 仓位上限：单一品种卖Put保证金占用不超过账户总权益的 8%~12%。"
    )

    return {
        "headline": headline,
        "whyNow": why_now,
        "strikeLogic": strike_logic,
        "riskControl": risk_control,
    }


def _compute_60d_corr_map(
    bars_map: Dict[str, List[Dict[str, Any]]],
    window: int = 60,
) -> Dict[Tuple[str, str], float]:
    """
    Compute pairwise 60-day daily log-return Pearson correlation across instruments.
    Aligns by date `b['t']` when >= 25 overlapping dates exist, falling back to tail alignment.
    """
    ret_by_date: Dict[str, Dict[str, float]] = {}
    ret_series: Dict[str, List[float]] = {}

    for inst_id, bars in bars_map.items():
        if not bars or len(bars) < 25:
            continue
        sub = bars[-(window + 5) :]
        dmap: Dict[str, float] = {}
        rlist: List[float] = []
        for i in range(1, len(sub)):
            c0 = float(sub[i - 1]["c"])
            c1 = float(sub[i]["c"])
            if c0 > 0 and c1 > 0:
                r = math.log(c1 / c0)
                dmap[sub[i]["t"]] = r
                rlist.append(r)
        if len(rlist) >= 20:
            ret_by_date[inst_id] = dmap
            ret_series[inst_id] = rlist[-window:]

    ids = list(ret_series.keys())
    corr_map: Dict[Tuple[str, str], float] = {}

    for i in range(len(ids)):
        id_a = ids[i]
        map_a = ret_by_date[id_a]
        for j in range(i + 1, len(ids)):
            id_b = ids[j]
            map_b = ret_by_date[id_b]
            common_dates = [d for d in map_a if d in map_b]
            if len(common_dates) >= 25:
                xs = [map_a[d] for d in common_dates[-window:]]
                ys = [map_b[d] for d in common_dates[-window:]]
            else:
                ra = ret_series[id_a]
                rb = ret_series[id_b]
                m = min(len(ra), len(rb), window)
                if m < 20:
                    continue
                xs = ra[-m:]
                ys = rb[-m:]

            n = len(xs)
            mx = sum(xs) / n
            my = sum(ys) / n
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            vx = sum((x - mx) ** 2 for x in xs)
            vy = sum((y - my) ** 2 for y in ys)
            if vx > 1e-12 and vy > 1e-12:
                rho = round(cov / math.sqrt(vx * vy), 2)
                corr_map[(id_a, id_b)] = rho
                corr_map[(id_b, id_a)] = rho

    return corr_map


def get_weekly_recommendations(
    target_dte: int = 30,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Build the complete weekly Short Put recommendation payload across all 3 markets.
    """
    target_dte = max(5, min(int(target_dte or 30), 90))

    def _compute() -> Dict[str, Any]:
        week_ctx = get_week_context(target_dte=target_dte)
        macro_regime = get_macro_vol_regime(force=force)
        bars_map = ensure_all_bars_loaded(force=force)
        real_iv_map = get_real_iv_map(target_dte=week_ctx["targetDte"], macro_regime=macro_regime, force=force)
        corr_map = _compute_60d_corr_map(bars_map, window=60)

        all_rows: List[Dict[str, Any]] = []
        for inst in ALL_INSTRUMENTS:
            b = bars_map.get(inst["id"])
            if not b:
                continue
            row = analyze_single_instrument(
                inst,
                b,
                macro_regime,
                target_dte=week_ctx["targetDte"],
                real_iv_entry=real_iv_map.get(inst["id"]),
            )
            if row:
                all_rows.append(row)

        all_rows.sort(key=lambda x: x["putScore"], reverse=True)

        # Populate highCorrPeers (same-market peers with 60D correlation >= 0.70)
        by_id = {r["id"]: r for r in all_rows}
        for r in all_rows:
            peers: List[Dict[str, Any]] = []
            for other_id, other_row in by_id.items():
                if other_id == r["id"] or other_row["market"] != r["market"]:
                    continue
                rho = corr_map.get((r["id"], other_id), 0.0)
                if rho >= 0.70:
                    peers.append({"symbol": other_row["symbol"], "name": other_row["name"], "corr": rho})
            peers.sort(key=lambda x: x["corr"], reverse=True)
            r["highCorrPeers"] = peers[:3]

        us_stk_list = [r for r in all_rows if r["market"] == "us_stk"]
        us_fut_list = [r for r in all_rows if r["market"] == "us_fut"]
        cn_fut_list = [r for r in all_rows if r["market"] == "cn_fut"]

        # Weekly Top Picks per market (diversified across sectors AND deduplicated by 60D return correlation <= 0.70)
        top_us_stk = _select_diversified_top(us_stk_list, top_n=6, max_per_sector=2, corr_map=corr_map, max_corr=0.70)
        top_us_fut = _select_diversified_top(us_fut_list, top_n=6, max_per_sector=2, corr_map=corr_map, max_corr=0.70)
        top_cn_fut = _select_diversified_top(cn_fut_list, top_n=6, max_per_sector=2, corr_map=corr_map, max_corr=0.70)

        # Dedicated A-share Index Options trio (IM0, IF0, IH0) ordered specifically
        idx_order = {"CN_FUT:IM0": 0, "CN_FUT:IF0": 1, "CN_FUT:IH0": 2}
        cn_index_options = sorted(
            [r for r in all_rows if r["id"] in idx_order],
            key=lambda x: idx_order.get(x["id"], 99),
        )

        # Summary KPIs
        avg_score = round(sum(r["putScore"] for r in all_rows) / max(len(all_rows), 1), 1)
        below_cost_count = sum(
            1
            for r in all_rows
            if r.get("cost") and r["cost"].get("anchorValid", True) and r["cost"]["vsPrimaryPct"] <= 3.0
        )
        high_ivr_count = sum(1 for r in all_rows if r["ivRank"] >= 60.0)
        real_iv_count = sum(1 for r in all_rows if r.get("isRealIv"))

        return {
            "weekContext": week_ctx,
            "macroRegime": macro_regime,
            "summary": {
                "totalCount": len(all_rows),
                "usStkCount": len(us_stk_list),
                "usFutCount": len(us_fut_list),
                "cnFutCount": len(cn_fut_list),
                "avgScore": avg_score,
                "belowCostCount": below_cost_count,
                "highIvrCount": high_ivr_count,
                "realIvCount": real_iv_count,
            },
            "cnIndexOptions": cn_index_options,
            "topPicks": {
                "us_stk": top_us_stk,
                "us_fut": top_us_fut,
                "cn_fut": top_cn_fut,
            },
            "markets": {
                "us_stk": us_stk_list,
                "us_fut": us_fut_list,
                "cn_fut": cn_fut_list,
            },
            "all": all_rows,
            "updatedAt": now_bj(),
        }

    return cached(f"weekly_recs:{target_dte}", 60.0, _compute, force=force)


def _select_diversified_top(
    sorted_rows: List[Dict[str, Any]],
    top_n: int = 6,
    max_per_sector: int = 2,
    corr_map: Optional[Dict[Tuple[str, str], float]] = None,
    max_corr: float = 0.70,
) -> List[Dict[str, Any]]:
    picked: List[Dict[str, Any]] = []
    sector_counts: Dict[str, int] = {}
    corr_map = corr_map or {}

    for r in sorted_rows:
        if len(picked) >= top_n:
            break
        # Do not feature falling-knife or bear-channel items in Top 6 unless no alternatives
        if r.get("trendRegime") in ("破位急跌飞刀", "空头阴跌通道"):
            continue
        sec = r.get("sector", "其他")
        if sector_counts.get(sec, 0) >= max_per_sector:
            continue
        # Correlation clustering check: avoid stacking assets with 60D return correlation > max_corr
        if any(corr_map.get((r["id"], p["id"]), 0.0) > max_corr for p in picked):
            continue
        picked.append(r)
        sector_counts[sec] = sector_counts.get(sec, 0) + 1

    # Second pass: relax correlation cap to 0.85 if fewer than top_n qualified
    if len(picked) < top_n:
        have_ids = {x["id"] for x in picked}
        for r in sorted_rows:
            if len(picked) >= top_n:
                break
            if r["id"] in have_ids:
                continue
            if r.get("trendRegime") in ("破位急跌飞刀", "空头阴跌通道"):
                continue
            if any(corr_map.get((r["id"], p["id"]), 0.0) > 0.85 for p in picked):
                continue
            picked.append(r)
            have_ids.add(r["id"])

    if len(picked) < top_n:
        have_ids = {x["id"] for x in picked}
        for r in sorted_rows:
            if len(picked) >= top_n:
                break
            if r["id"] not in have_ids:
                picked.append(r)
    return picked


def get_instrument_detail(
    inst_id: str,
    target_dte: int = 30,
    tier_key: Optional[str] = None,
    custom_strike: Optional[float] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Return K-line bars + technical overlays + 3-tier Put strikes + Payoff diagram curve
    for a specific instrument.
    """
    inst = get_instrument(inst_id)
    if not inst:
        raise KeyError(f"Unknown instrument: {inst_id}")

    week_ctx = get_week_context(target_dte=target_dte)
    actual_dte = week_ctx["targetDte"]
    macro_regime = get_macro_vol_regime(force=False)
    real_iv_map = get_real_iv_map(target_dte=actual_dte, macro_regime=macro_regime, force=False)
    bars = get_instrument_bars(inst["id"], force=force)
    if not bars:
        raise ValueError(f"No historical bars for {inst_id}")

    analysis = analyze_single_instrument(
        inst,
        bars,
        macro_regime,
        target_dte=actual_dte,
        real_iv_entry=real_iv_map.get(inst["id"]),
    )
    if not analysis:
        raise ValueError(f"Insufficient data to analyze {inst_id}")

    dp = int(inst.get("dp", 2))
    kline_bars = bars[-260:]  # 1-year daily K-line for fast charting
    closes = [b["c"] for b in kline_bars]

    # Compute rolling MA20, MA60, Bollinger Bands, and RSI14 for the chart
    ma20_arr: List[Optional[float]] = []
    ma60_arr: List[Optional[float]] = []
    boll_up_arr: List[Optional[float]] = []
    boll_low_arr: List[Optional[float]] = []

    all_closes = [b["c"] for b in bars]
    offset = len(all_closes) - len(kline_bars)
    for idx in range(len(kline_bars)):
        g_idx = offset + idx + 1
        seg20 = all_closes[max(0, g_idx - 20) : g_idx]
        seg60 = all_closes[max(0, g_idx - 60) : g_idx]
        m20 = sum(seg20) / len(seg20) if len(seg20) >= 5 else closes[idx]
        m60 = sum(seg60) / len(seg60) if len(seg60) >= 15 else m20
        sd = _std(seg20) if len(seg20) >= 5 else 0.0
        ma20_arr.append(round(m20, dp))
        ma60_arr.append(round(m60, dp))
        boll_up_arr.append(round(m20 + 2.0 * sd, dp))
        boll_low_arr.append(round(max(0.01, m20 - 2.0 * sd), dp))

    chosen_tier_key = tier_key if tier_key in ("conservative", "balanced", "aggressive") else analysis["recommendedTierKey"]
    chosen_tier = analysis["tiers"][chosen_tier_key]

    strike_for_payoff = float(custom_strike) if (custom_strike and custom_strike > 0) else chosen_tier["strike"]
    payoff = build_payoff_curve(
        inst=inst,
        spot=analysis["price"],
        strike=strike_for_payoff,
        dte=actual_dte,
        iv=chosen_tier["ivPct"] / 100.0,
        premium=chosen_tier["premium"],
    )

    return {
        "analysis": analysis,
        "instrument": analysis,
        "weekContext": week_ctx,
        "selectedTierKey": chosen_tier_key,
        "chosenTierKey": chosen_tier_key,
        "chosenTier": chosen_tier,
        "kline": {
            "bars": kline_bars,
            "dates": [b["t"] for b in kline_bars],
            "ohlc": [[b["o"], b["c"], b["l"], b["h"]] for b in kline_bars],
            "volumes": [b["v"] for b in kline_bars],
            "ma20": ma20_arr,
            "ma60": ma60_arr,
            "bollUp": boll_up_arr,
            "bollLow": boll_low_arr,
        },
        "payoff": payoff,
        "updatedAt": now_bj(),
    }
