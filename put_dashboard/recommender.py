# -*- coding: utf-8 -*-
"""
Weekly Dynamic Short Put Quantitative Scoring & Recommendation Engine.
Covers:
- US Stocks & ETFs (us_stk)
- US Futures (us_fut)
- China Futures (cn_fut)
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from data_engine import (
    ensure_all_bars_loaded,
    get_instrument_bars,
    get_macro_vol_regime,
)
from http_utils import cached, get_week_context, now_bj
from options_math import build_payoff_curve, build_put_tiers
from universe import ALL_INSTRUMENTS, get_instrument

logger = logging.getLogger(__name__)


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


def _hv_percentile_1y(closes: List[float], cur_hv20: float) -> float:
    """Compute 1-year percentile rank (0-100) of 20-day realized volatility."""
    sub = closes[-265:]
    if len(sub) < 45:
        return 50.0
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
        return 50.0
    below = sum(1 for v in hvs if v <= cur_hv20)
    return round((below / len(hvs)) * 100.0, 1)


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


def _calibrate_implied_vol(
    inst: Dict[str, Any],
    hv20: float,
    hv60: float,
    hv_rank: float,
    rsi14: float,
    ret_1w: float,
    macro_regime: Dict[str, Any],
) -> Tuple[float, float, float]:
    """
    Calibrate realistic ATM Implied Volatility (IV), IV Rank, and VRP (IV - HV20)
    by combining realized HV20/HV60, market volatility indices (VIX/VXN/OVX/GVZ),
    and empirical downside fear premium when RSI/weekly return drops.
    """
    blended_hv = 0.65 * hv20 + 0.35 * hv60
    mkt = inst["market"]
    sector = inst.get("sector", "")

    vix = float(macro_regime.get("vix") or 18.5) / 100.0
    vxn = float(macro_regime.get("vxn") or 22.0) / 100.0
    ovx = float(macro_regime.get("ovx") or 34.0) / 100.0
    gvz = float(macro_regime.get("gvz") or 17.5) / 100.0

    # Base Variance Risk Premium multiplier (options price in ~15% vol premium over realized)
    vrp_mult = 1.16
    regime_anchor = blended_hv

    if mkt == "us_stk":
        if inst["symbol"] == "SPY":
            regime_anchor = vix
            vrp_mult = 1.08
        elif inst["symbol"] == "QQQ":
            regime_anchor = vxn
            vrp_mult = 1.08
        elif sector in ("AI/半导体", "科技巨头"):
            regime_anchor = max(blended_hv, vxn * 1.15)
            vrp_mult = 1.18
        else:
            regime_anchor = max(blended_hv, vix * 1.05)
            vrp_mult = 1.15
    elif mkt == "us_fut":
        if sector == "能源":
            regime_anchor = 0.55 * blended_hv + 0.45 * ovx
            vrp_mult = 1.16
        elif sector == "贵金属":
            regime_anchor = 0.60 * blended_hv + 0.40 * gvz
            vrp_mult = 1.14
        elif inst["symbol"] == "ES=F":
            regime_anchor = vix
            vrp_mult = 1.06
        elif inst["symbol"] == "NQ=F":
            regime_anchor = vxn
            vrp_mult = 1.06
        else:
            regime_anchor = blended_hv
            vrp_mult = 1.15
    else:  # cn_fut
        regime_anchor = blended_hv
        vrp_mult = 1.15

    # Pullback fear spike: when price drops over the past week or RSI < 42, IV expands
    fear_bump = 0.0
    if ret_1w < -2.0:
        fear_bump += min(0.06, abs(ret_1w) * 0.008)
    if rsi14 < 42.0:
        fear_bump += (42.0 - rsi14) * 0.0015

    atm_iv = (0.65 * blended_hv + 0.35 * regime_anchor) * vrp_mult + fear_bump
    atm_iv = max(0.08, min(atm_iv, 1.45))

    vrp_pts = (atm_iv - hv20) * 100.0
    # IV Rank reflects HV Rank + fear expansion
    iv_rank = min(99.0, max(5.0, hv_rank * 0.85 + (15.0 if fear_bump > 0.015 else 8.0)))
    return atm_iv, round(iv_rank, 1), round(vrp_pts, 1)


def analyze_single_instrument(
    inst: Dict[str, Any],
    bars: List[Dict[str, Any]],
    macro_regime: Dict[str, Any],
    target_dte: int = 30,
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

    ma20 = _sma(closes, 20) or spot
    ma60 = _sma(closes, 60) or spot
    ma120 = _sma(closes, 120) or ma60
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
    hv_rank = _hv_percentile_1y(closes, hv20)
    atm_iv, iv_rank, vrp_pts = _calibrate_implied_vol(
        inst, hv20, hv60, hv_rank, rsi, ret_1w, macro_regime
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

    tiers = build_put_tiers(inst, spot, atm_iv, dte=target_dte, supports=supports)
    bal_tier = tiers["balanced"]
    cons_tier = tiers["conservative"]
    agg_tier = tiers["aggressive"]

    # Evaluate Cost / Fundamental Floor
    cost_cfg = inst.get("cost")
    cost_info: Optional[Dict[str, Any]] = None
    if cost_cfg:
        cash_c = float(cost_cfg["cash_cost"])
        prim_c = float(cost_cfg["primary_cost"])
        high_c = float(cost_cfg["comfort_high"])
        vs_prim = ((spot / prim_c) - 1.0) * 100.0
        vs_cash = ((spot / cash_c) - 1.0) * 100.0
        if spot <= cash_c * 1.02:
            c_status = "破现金成本·极强减产底"
            c_tone = "bull"
        elif spot <= prim_c * 1.03:
            c_status = "跌破完全成本·亏损磨底"
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
            "status": c_status,
            "tone": c_tone,
            "label": cost_cfg.get("label", ""),
            "source": cost_cfg.get("source", ""),
        }

    # -----------------------------------------------------------------------
    # 5-FACTOR SHORT PUT QUANTITATIVE SCORING (0 - 100)
    # -----------------------------------------------------------------------
    # 1. Floor & Valuation Safety (0 - 30 pts)
    floor_score = 15.0
    if cost_info:
        vp = cost_info["vsPrimaryPct"]
        if vp <= -8:
            floor_score = 29.0
        elif vp <= 2:
            floor_score = 27.0
        elif vp <= 12:
            floor_score = 23.5
        elif vp <= 25:
            floor_score = 18.5
        elif vp <= 45:
            floor_score = 13.5
        else:
            floor_score = 9.0
        # Blend with 3Y/5Y low percentile
        low_pct_blend = 0.5 * pct_3y + 0.5 * pct_5y
        if low_pct_blend <= 25:
            floor_score = min(30.0, floor_score + 3.0)
        elif low_pct_blend >= 85 and vp > 35:
            floor_score = max(6.0, floor_score - 3.0)
    else:
        # US Stocks / Financial Futures: Moat + Pullback from 52W High + MA60/MA120 proximity
        q_bonus = 4.0 if inst.get("quality_tier") == "S" else 2.0
        # Sweet spot drawdown from 52W high is -5% to -28%
        dd = abs(dd_52w_pct)
        if 5.0 <= dd <= 26.0:
            dd_pts = 18.0
        elif 2.0 <= dd < 5.0:
            dd_pts = 15.0
        elif 26.0 < dd <= 38.0:
            dd_pts = 14.5
        else:
            dd_pts = 11.5
        # Proximity to MA60 / Boll Low
        vs_ma60 = ((spot / ma60) - 1.0) * 100.0
        ma_pts = 6.5 if (-6.0 <= vs_ma60 <= 5.0) else (4.5 if vs_ma60 > 5.0 else 3.5)
        floor_score = min(30.0, q_bonus + dd_pts + ma_pts)

    # 2. Volatility & Premium Richness (0 - 25 pts)
    ann_ret = bal_tier["annReturnMarginPct"] if inst["market"] != "us_stk" else bal_tier["annReturnCashPct"]
    ivr_pts = min(13.0, max(4.0, iv_rank * 0.14))
    if inst["market"] == "us_stk":
        ret_pts = min(12.0, max(3.0, ann_ret * 0.52))
    else:
        ret_pts = min(12.0, max(3.0, ann_ret * 0.28))
    vol_score = min(25.0, round(ivr_pts + ret_pts, 1))

    # 3. Technical Support & RSI Stabilization (0 - 20 pts)
    # Ideal RSI for selling put is 30 - 52 (pullback/oversold stabilizing)
    if 30.0 <= rsi <= 50.0:
        tech_score = 18.5
    elif 50.0 < rsi <= 60.0:
        tech_score = 15.5
    elif 24.0 <= rsi < 30.0:
        tech_score = 16.0 if ret_1d_stabilizing(chg_1d, ret_1w) else 12.5
    elif 60.0 < rsi <= 68.0:
        tech_score = 12.0
    elif rsi > 68.0:
        tech_score = 8.0
    else:
        tech_score = 9.0
    # Bonus if balanced strike sits below Bollinger lower band or S1
    if bal_tier["strike"] <= boll_low * 1.005:
        tech_score = min(20.0, tech_score + 1.5)

    # 4. Trend Health & Anti-Knife Filter (0 - 15 pts)
    trend_score = 11.0
    if ret_1w < -9.5 and chg_1d < -2.5:
        # Sharp falling knife penalty
        trend_score = 4.5
    elif -6.5 <= ret_1w <= 1.5 and spot >= low_20d * 0.99:
        # Healthy pullback holding support
        trend_score = 14.0
    elif spot >= ma60 and ma20 >= ma60 * 0.98:
        # Steady uptrend support
        trend_score = 13.0
    elif cost_info and cost_info["vsPrimaryPct"] <= 5.0 and abs(ret_1w) <= 4.0:
        # Low-volatility bottoming consolidation near cost floor
        trend_score = 14.0

    # 5. Moat & Liquidity Bonus (0 - 10 pts)
    moat_score = 9.0 if inst.get("quality_tier") == "S" else 8.2
    if inst["symbol"] in (
        "SPY", "QQQ", "NVDA", "AAPL", "MSFT",
        "IM0", "IF0", "IH0",
        "M0", "RB0", "AU0", "TA0", "SA0", "GC=F", "CL=F", "ES=F",
    ):
        moat_score = 9.6

    total_score = round(floor_score + vol_score + tech_score + trend_score + moat_score, 1)
    total_score = max(18.0, min(98.0, total_score))

    # Choose optimal recommended tier for current market state
    if cost_info and cost_info["vsPrimaryPct"] <= 0 and rsi <= 48:
        rec_tier_key = "balanced"
    elif rsi >= 65 or pct_5y >= 82 or hv20 >= 0.48:
        rec_tier_key = "conservative"
    elif inst["market"] == "us_stk" and inst.get("quality_tier") == "S" and rsi <= 42 and dd_52w_pct <= -10:
        rec_tier_key = "aggressive"
    else:
        rec_tier_key = "balanced"

    rec_tier = tiers[rec_tier_key]

    # Classify Strategy Archetype & Verdict Badge
    archetype, badge_tone, thesis_tags = _classify_archetype(
        inst, spot, rsi, pct_3y, pct_5y, dd_52w_pct, iv_rank, cost_info, total_score
    )

    playbook = _build_weekly_playbook(
        inst, spot, rsi, pct_5y, iv_rank, hv20, cost_info, supports, tiers, rec_tier_key, archetype, target_dte
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
        "ivRank": iv_rank,
        "vrpPts": vrp_pts,
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
        },
        "archetype": archetype,
        "badgeTone": badge_tone,
        "thesisTags": thesis_tags,
        "recommendedTierKey": rec_tier_key,
        "recommendedTier": rec_tier,
        "tiers": tiers,
        "playbook": playbook,
        "asof": bars[-1]["t"],
    }


def ret_1d_stabilizing(chg_1d: float, ret_1w: float) -> bool:
    return chg_1d >= -0.8 and ret_1w > -8.0


def _classify_archetype(
    inst: Dict[str, Any],
    spot: float,
    rsi: float,
    pct_3y: float,
    pct_5y: float,
    dd_52w: float,
    iv_rank: float,
    cost_info: Optional[Dict[str, Any]],
    total_score: float,
) -> Tuple[str, str, List[str]]:
    tags: List[str] = []
    mkt = inst["market"]

    if cost_info:
        vp = cost_info["vsPrimaryPct"]
        vc = cost_info["vsCashPct"]
        if vc <= 2.0:
            tags.append("破现金成本铁底")
        elif vp <= 3.0:
            tags.append("跌破完全成本")
        elif vp <= 15.0:
            tags.append("贴近成本支撑")

    if pct_5y <= 25.0:
        tags.append(f"5年低分位({pct_5y:.0f}%)")
    elif mkt == "us_stk" and dd_52w <= -8.0:
        tags.append(f"距高点回调{dd_52w:.1f}%")

    if 28.0 <= rsi <= 45.0:
        tags.append(f"RSI超卖企稳({rsi:.0f})")
    elif 45.0 < rsi <= 56.0:
        tags.append(f"RSI中性舒适({rsi:.0f})")

    if iv_rank >= 60.0:
        tags.append(f"高IV溢价(IVR {iv_rank:.0f}%)")
    else:
        tags.append(f"IVR {iv_rank:.0f}%")

    if total_score < 62.0:
        return "高位或趋势偏弱 · 仅限极深虚值观察", "neutral", tags[:4]

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

    if cost_info and cost_info["vsCashPct"] <= 3.0:
        return "破现金成本 · 深虚值铁底收租", "bull", tags[:4]
    if cost_info and cost_info["vsPrimaryPct"] <= 8.0:
        return "贴近产业成本 · 底部磨底卖Put", "bull", tags[:4]
    if mkt == "us_stk" and dd_52w <= -7.0 and rsi <= 48.0:
        return "核心龙头回调 · 以接货之心卖Put", "bull", tags[:4]
    if iv_rank >= 62.0 and rsi <= 55.0:
        return "高IV恐慌溢价 · 波动率回归收租", "gold", tags[:4]
    if mkt == "us_stk":
        return "慢牛均线支撑 · 现金担保收租(CSP)", "gold", tags[:4]
    return "关键支撑位保护 · 顺势虚值收租", "gold", tags[:4]


def _build_weekly_playbook(
    inst: Dict[str, Any],
    spot: float,
    rsi: float,
    pct_5y: float,
    iv_rank: float,
    hv20: float,
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

    headline = (
        f"【{archetype}】推荐卖出 {target_dte}天到期、行权价 {cur}{rec['strike']:g} Put（{rec['label']}，"
        f"Delta {rec['delta']:.2f}），安全垫 {rec['otmPct']:.1f}%，到期胜率 {rec['popPct']:.1f}%。"
    )

    if cost_info:
        why_now = (
            f"{inst['name']}现价 {spot:g} {unit}（近5年价格分位 {pct_5y:.1f}%，RSI {rsi:.1f}）。"
            f"产业锚方面，{cost_info['label']}约 {cost_info['primaryCost']:g} {unit}，现金成本约 {cost_info['cashCost']:g} {unit}，"
            f"现价相对完全成本 {cost_info['vsPrimaryPct']:+.1f}%（{cost_info['status']}）。"
            f"{inst.get('moat_note', '')}"
        )
    else:
        why_now = (
            f"{inst['name']}现价 {cur}{spot:g}（RSI {rsi:.1f}，20日历史波动率 {hv20*100:.1f}%，IV分位 {iv_rank:.0f}%）。"
            f"技术面60日均线位于 {cur}{supports['ma60']:g}，布林下轨位于 {cur}{supports['bollLow']:g}。"
            f"{inst.get('moat_note', '')}"
        )

    if inst["market"] == "us_stk":
        yield_str = f"全额现金担保年化收益 {rec['annReturnCashPct']:.1f}%（Reg-T保证金口径年化 {rec['annReturnMarginPct']:.1f}%）"
    else:
        yield_str = f"交易所保证金口径年化收益 {rec['annReturnMarginPct']:.1f}%（名义本金口径年化 {rec['annReturnCashPct']:.1f}%）"

    strike_logic = (
        f"主力推荐【{rec['label']}】行权价 {cur}{rec['strike']:g}：单张可收权利金约 {cur}{rec['contractPremium']:g} "
        f"（每单位 {rec['premium']:g}），盈亏平衡点低至 {cur}{rec['breakeven']:g}（需从现价下跌 {rec['breakevenBufferPct']:.1f}% 才开始实质亏损），"
        f"{yield_str}。若追求极致安全可选【保守档】{cur}{cons['strike']:g}（胜率 {cons['popPct']:.1f}%）；"
        f"若希望低位拿货建仓可选【进取档】{cur}{agg['strike']:g}。"
    )

    stop_px = round(rec["breakeven"] * 0.985, int(inst.get("dp", 2)))
    risk_control = (
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

        all_rows: List[Dict[str, Any]] = []
        for inst in ALL_INSTRUMENTS:
            b = bars_map.get(inst["id"])
            if not b:
                continue
            row = analyze_single_instrument(inst, b, macro_regime, target_dte=week_ctx["targetDte"])
            if row:
                all_rows.append(row)

        all_rows.sort(key=lambda x: x["putScore"], reverse=True)

        us_stk_list = [r for r in all_rows if r["market"] == "us_stk"]
        us_fut_list = [r for r in all_rows if r["market"] == "us_fut"]
        cn_fut_list = [r for r in all_rows if r["market"] == "cn_fut"]

        # Weekly Top Picks per market (diversified across sectors where possible)
        top_us_stk = _select_diversified_top(us_stk_list, top_n=6, max_per_sector=2)
        top_us_fut = _select_diversified_top(us_fut_list, top_n=6, max_per_sector=2)
        top_cn_fut = _select_diversified_top(cn_fut_list, top_n=6, max_per_sector=2)

        # Dedicated A-share Index Options trio (IM0, IF0, IH0) ordered specifically
        idx_order = {"CN_FUT:IM0": 0, "CN_FUT:IF0": 1, "CN_FUT:IH0": 2}
        cn_index_options = sorted(
            [r for r in all_rows if r["id"] in idx_order],
            key=lambda x: idx_order.get(x["id"], 99),
        )

        # Summary KPIs
        avg_score = round(sum(r["putScore"] for r in all_rows) / max(len(all_rows), 1), 1)
        below_cost_count = sum(
            1 for r in all_rows if r.get("cost") and r["cost"]["vsPrimaryPct"] <= 3.0
        )
        high_ivr_count = sum(1 for r in all_rows if r["ivRank"] >= 60.0)

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
    sorted_rows: List[Dict[str, Any]], top_n: int = 6, max_per_sector: int = 2
) -> List[Dict[str, Any]]:
    picked: List[Dict[str, Any]] = []
    sector_counts: Dict[str, int] = {}
    for r in sorted_rows:
        if len(picked) >= top_n:
            break
        sec = r.get("sector", "其他")
        if sector_counts.get(sec, 0) >= max_per_sector:
            continue
        picked.append(r)
        sector_counts[sec] = sector_counts.get(sec, 0) + 1

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
    bars = get_instrument_bars(inst["id"], force=force)
    if not bars:
        raise ValueError(f"No historical bars for {inst_id}")

    analysis = analyze_single_instrument(inst, bars, macro_regime, target_dte=actual_dte)
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
        "weekContext": week_ctx,
        "kline": {
            "bars": kline_bars,
            "ma20": ma20_arr,
            "ma60": ma60_arr,
            "bollUp": boll_up_arr,
            "bollLow": boll_low_arr,
        },
        "selectedTierKey": chosen_tier_key,
        "payoff": payoff,
        "updatedAt": now_bj(),
    }
