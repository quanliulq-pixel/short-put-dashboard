# -*- coding: utf-8 -*-
"""
Direct Stock & Futures Directional Trading Analysis & Vehicle Comparison Engine
(股票/期货直接买卖做多·做空量化分析与「直接买卖标的 vs 卖Put期权」决策对比引擎)

Covers all 79 liquid instruments across:
- US Stocks & ETFs (us_stk): Direct Long Equity/ETF Accumulation, Pullback Swing & Breakout setups
- US Futures (us_fut): Two-way Direct Long & Direct Short Futures Trend / Cost-Reversion setups
- China Futures (cn_fut): Two-way Direct Long & Direct Short Commodity / Financial Index Futures setups
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def _interp(x: float, pts: List[Tuple[float, float]]) -> float:
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
            return y0 + ((x - x0) / (x1 - x0)) * (y1 - y0)
    return pts[-1][1]


def compute_empirical_directional_stats(
    bars: List[Dict[str, Any]],
    direction: str,
    cur_rsi: float,
    cur_above_ma60: bool,
    atr_pct: float,
    hold_days: int = 20,
) -> Dict[str, Any]:
    """
    Run a 5-year historical conditioning backtest on `bars` for a Direct Long or Direct Short trade
    held for `hold_days` (default 20 trading days) with:
      - Hard Stop-Loss = 2.0 * ATR
      - Wave Take-Profit = 3.5 * ATR
    Filters historical entry bars to match the current regime (trend alignment + RSI neighborhood).
    """
    if not bars or len(bars) < hold_days + 65:
        return {
            "sampleCount": 0,
            "winRatePct": 55.0,
            "avgWinPct": round(atr_pct * 2.6, 2),
            "avgLossPct": round(atr_pct * 1.5, 2),
            "profitFactor": 1.75,
            "expectedR": 0.35,
            "avgNetRetPct": round(atr_pct * 0.7, 2),
        }

    closes = [float(b["c"]) for b in bars]
    highs = [float(b["h"]) for b in bars]
    lows = [float(b["l"]) for b in bars]
    n = len(bars)

    stop_dist_pct = max(1.2, atr_pct * 2.0)
    tp_dist_pct = max(2.2, atr_pct * 3.5)

    # Precompute rolling 60-day SMA and rough 14-day RSI for conditioning
    r_multiples: List[float] = []
    wins: List[float] = []
    losses: List[float] = []
    net_rets: List[float] = []

    is_long = direction != "SHORT"

    # Step every 4 trading days to avoid overlapping-window autocorrelation
    for idx in range(60, n - hold_days, 4):
        c0 = closes[idx]
        if c0 <= 0:
            continue
        ma60_i = sum(closes[idx - 60 : idx]) / 60.0
        above_ma60_i = c0 >= ma60_i * 0.995

        # Simple 14-day RSI at idx
        gains = 0.0
        loss_sum = 0.0
        for k in range(idx - 13, idx + 1):
            d = closes[k] - closes[k - 1]
            if d >= 0:
                gains += d
            else:
                loss_sum -= d
        rsi_i = 100.0 - (100.0 / (1.0 + (gains / max(loss_sum, 1e-9))))

        # Match regime: same side of MA60 and RSI within +/- 18 pts
        if above_ma60_i != cur_above_ma60:
            continue
        if abs(rsi_i - cur_rsi) > 18.0:
            continue

        # Simulate path over next hold_days with 2.0*ATR stop and 3.5*ATR target
        outcome_pct = None
        for step in range(1, hold_days + 1):
            hi_pct = ((highs[idx + step] / c0) - 1.0) * 100.0
            lo_pct = ((lows[idx + step] / c0) - 1.0) * 100.0
            if is_long:
                if lo_pct <= -stop_dist_pct:
                    outcome_pct = -stop_dist_pct
                    break
                if hi_pct >= tp_dist_pct:
                    outcome_pct = tp_dist_pct
                    break
            else:
                # Short trade: stop is upside +stop_dist_pct, target is downside -tp_dist_pct
                if hi_pct >= stop_dist_pct:
                    outcome_pct = -stop_dist_pct
                    break
                if lo_pct <= -tp_dist_pct:
                    outcome_pct = tp_dist_pct
                    break

        if outcome_pct is None:
            c_end = closes[idx + hold_days]
            raw_ret = ((c_end / c0) - 1.0) * 100.0
            outcome_pct = raw_ret if is_long else -raw_ret

        r_val = outcome_pct / stop_dist_pct
        r_multiples.append(r_val)
        net_rets.append(outcome_pct)
        if outcome_pct > 0:
            wins.append(outcome_pct)
        else:
            losses.append(abs(outcome_pct))

    # Fallback to unconditional sample if regime filter had < 12 samples
    if len(r_multiples) < 12:
        r_multiples.clear()
        wins.clear()
        losses.clear()
        net_rets.clear()
        for idx in range(60, n - hold_days, 8):
            c0 = closes[idx]
            if c0 <= 0:
                continue
            c_end = closes[idx + hold_days]
            raw_ret = ((c_end / c0) - 1.0) * 100.0
            outcome_pct = _clamp(raw_ret if is_long else -raw_ret, -stop_dist_pct, tp_dist_pct)
            r_val = outcome_pct / stop_dist_pct
            r_multiples.append(r_val)
            net_rets.append(outcome_pct)
            if outcome_pct > 0:
                wins.append(outcome_pct)
            else:
                losses.append(abs(outcome_pct))

    total = max(len(r_multiples), 1)
    win_rate = (len(wins) / total) * 100.0
    avg_win = sum(wins) / len(wins) if wins else stop_dist_pct * 1.4
    avg_loss = sum(losses) / len(losses) if losses else stop_dist_pct * 0.85
    gross_win = sum(wins)
    gross_loss = sum(losses)
    pf = (gross_win / gross_loss) if gross_loss > 1e-6 else 2.20
    exp_r = sum(r_multiples) / total
    avg_net = sum(net_rets) / total

    return {
        "sampleCount": len(r_multiples),
        "winRatePct": round(win_rate, 1),
        "avgWinPct": round(avg_win, 2),
        "avgLossPct": round(avg_loss, 2),
        "profitFactor": round(_clamp(pf, 0.40, 4.50), 2),
        "expectedR": round(exp_r, 2),
        "avgNetRetPct": round(avg_net, 2),
    }


def analyze_direct_underlying_trade(
    inst: Dict[str, Any],
    bars: List[Dict[str, Any]],
    spot: float,
    ma5: float,
    ma20: float,
    ma60: float,
    ma120: float,
    ma20_slope_pct: float,
    ma60_slope_pct: float,
    rsi: float,
    atr: float,
    atr_pct: float,
    hv20: float,
    atm_iv: float,
    iv_rank: float,
    vrp_pts: float,
    pct_3y: float,
    pct_5y: float,
    dd_52w_pct: float,
    ret_1w: float,
    ret_1m: float,
    ret_3m: float,
    trend_regime: str,
    supports: Dict[str, Any],
    cost_info: Optional[Dict[str, Any]],
    rec_put_tier: Dict[str, Any],
    put_score: float,
    target_dte: int = 30,
    basis_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compute a complete institutional analysis for directly buying/selling the underlying
    stock or futures contract, and compare it head-to-head against selling a Put option.
    """
    mkt = inst["market"]
    dp = int(inst.get("dp", 2))
    mult = float(inst.get("multiplier", 100))
    margin_rate = float(inst.get("margin_rate", 1.0 if mkt == "us_stk" else 0.12))
    is_futures = mkt in ("us_fut", "cn_fut")
    cur = inst["currency"]

    high_20d = float(supports.get("high20d") or max(b["h"] for b in bars[-20:]))
    low_20d = float(supports.get("low20d") or min(b["l"] for b in bars[-20:]))
    high_52w = float(supports.get("high52w") or spot * 1.15)
    low_52w = float(supports.get("low52w") or spot * 0.85)
    boll_up = float(supports.get("bollUp") or spot * 1.04)
    boll_low = float(supports.get("bollLow") or spot * 0.96)
    s1 = float(supports.get("s1") or spot * 0.97)
    pivot = (high_20d + low_20d + spot) / 3.0
    r1 = min(high_52w, max(high_20d, 2.0 * pivot - low_20d))

    # -----------------------------------------------------------------------
    # 1. Determine Primary Directional Bias (LONG vs SHORT vs NEUTRAL)
    # -----------------------------------------------------------------------
    # Futures support two-way trading (做多 & 做空).
    # CRITICAL RULE: Only classify as SHORT (顺势做空) when the contract is genuinely in a
    # bearish/downtrend structure (spot < MA20 and MAs sloping down / bearish alignment).
    # NEVER classify a bull trend (spot > MA20 > MA60) as SHORT!
    is_confirmed_downtrend = (
        trend_regime in ("空头阴跌通道", "破位急跌飞刀")
        or (spot < ma20 and ma20 < ma60 and (ma20_slope_pct < -0.2 or ma60_slope_pct < -0.2))
        or (spot < ma20 and ma20_slope_pct < -0.8 and ret_1m < -3.0)
    )

    if is_futures and is_confirmed_downtrend:
        direction = "SHORT"
    elif not is_futures and is_confirmed_downtrend:
        direction = "NEUTRAL_BEAR"
    else:
        direction = "LONG"

    eff_dir = "SHORT" if direction in ("SHORT", "NEUTRAL_BEAR") else "LONG"

    # -----------------------------------------------------------------------
    # 2. Entry, Stop-Loss (2.0*ATR & Structural), and T1 / T2 Profit Targets
    # -----------------------------------------------------------------------
    safe_atr = max(atr, spot * 0.008)
    if eff_dir == "LONG":
        # Ideal pullback entry vs current spot entry
        ideal_entry = round(max(boll_low, min(spot, 0.65 * spot + 0.35 * max(s1, ma20))), dp)
        breakout_entry = round(max(spot * 1.005, min(high_20d, ma20 * 1.015)), dp)
        # Structural + ATR stop-loss (approx 1.8x - 2.2x ATR below spot)
        raw_stop = min(spot - 1.8 * safe_atr, max(spot - 2.4 * safe_atr, min(s1, low_20d) * 0.992))
        stop_loss = round(max(spot * 0.75, raw_stop), dp)
        stop_dist = max(spot - stop_loss, safe_atr * 1.2)
        stop_pct = (stop_dist / spot) * 100.0

        # T1 (Conservative ~ 2.0x-2.4x ATR or R1/BollUp) & T2 (Wave Target ~ 3.8x-4.5x ATR or 52W High / Comfort Cost)
        t1_raw = max(spot + 2.1 * safe_atr, min(r1, boll_up))
        t2_anchor = high_52w
        if cost_info and cost_info.get("comfortHigh", 0) > spot * 1.04:
            t2_anchor = max(min(high_52w, float(cost_info["comfortHigh"])), spot + 3.5 * safe_atr)
        t2_raw = max(spot + 3.8 * safe_atr, min(t2_anchor, spot + 5.2 * safe_atr))

        target1 = round(t1_raw, dp)
        target2 = round(max(t1_raw + safe_atr, t2_raw), dp)
        t1_pct = ((target1 / spot) - 1.0) * 100.0
        t2_pct = ((target2 / spot) - 1.0) * 100.0
    else:
        # SHORT setup (primarily for Futures in bear trend or overbought top)
        ideal_entry = round(min(boll_up, max(spot, 0.65 * spot + 0.35 * ma20)), dp)
        breakout_entry = round(min(spot * 0.995, low_20d * 0.998), dp)
        raw_stop = max(spot + 1.8 * safe_atr, min(spot + 2.4 * safe_atr, max(r1, high_20d) * 1.008))
        stop_loss = round(min(spot * 1.25, raw_stop), dp)
        stop_dist = max(stop_loss - spot, safe_atr * 1.2)
        stop_pct = (stop_dist / spot) * 100.0

        t1_raw = min(spot - 2.1 * safe_atr, max(s1, boll_low))
        t2_anchor = low_52w
        if cost_info and cost_info.get("primaryCost", 0) < spot * 0.96:
            t2_anchor = min(max(low_52w, float(cost_info["primaryCost"])), spot - 3.5 * safe_atr)
        t2_raw = min(spot - 3.8 * safe_atr, max(t2_anchor, spot - 5.2 * safe_atr))

        target1 = round(max(spot * 0.5, t1_raw), dp)
        target2 = round(max(spot * 0.4, min(t1_raw - safe_atr, t2_raw)), dp)
        t1_pct = ((spot - target1) / spot) * 100.0
        t2_pct = ((spot - target2) / spot) * 100.0

    rr_t1 = round(max(0.5, t1_pct / max(stop_pct, 0.4)), 2)
    rr_t2 = round(max(0.8, t2_pct / max(stop_pct, 0.4)), 2)

    # -----------------------------------------------------------------------
    # 3. 5-Year Empirical Conditioning Backtest (20-Day Forward Directional Trade)
    # -----------------------------------------------------------------------
    emp_stats = compute_empirical_directional_stats(
        bars=bars,
        direction=eff_dir,
        cur_rsi=rsi,
        cur_above_ma60=(spot >= ma60),
        atr_pct=atr_pct,
        hold_days=max(10, min(int(target_dte * 0.7), 30)),
    )

    # -----------------------------------------------------------------------
    # 4. 5-Factor Quantitative Scoring for Direct Trading (0 - 100)
    # -----------------------------------------------------------------------
    # Factor 1: Trend & Momentum Alignment (0 - 30 pts)
    if eff_dir == "LONG":
        if trend_regime == "多头趋势回调甜点":
            f_trend = 27.5
        elif trend_regime == "多头上升通道":
            f_trend = 26.8 if 48.0 <= rsi <= 64.0 else 23.5
        elif trend_regime == "底部企稳筑底":
            f_trend = 25.0
        elif trend_regime == "回调测试支撑":
            f_trend = 21.5
        elif trend_regime == "多头高位偏热":
            f_trend = 18.5
        elif trend_regime == "空头超跌初企稳":
            f_trend = 17.5
        elif trend_regime == "区间宽幅震荡":
            f_trend = 19.0
        else:
            f_trend = 9.5

        if ma20_slope_pct > 1.2 and ma60_slope_pct > 0.8:
            f_trend += 2.0
        elif ma20_slope_pct < -2.0:
            f_trend -= 2.5
    else:
        # Short trend scoring (pure trend-following in bearish / downtrend structure)
        if trend_regime == "空头阴跌通道":
            f_trend = 27.5
        elif trend_regime == "破位急跌飞刀":
            f_trend = 25.0 if rsi >= 26.0 else 18.5  # Watch short-squeeze bounce if RSI < 26
        elif spot < ma20 and ma20 < ma60:
            f_trend = 25.8
        else:
            f_trend = 22.0
        if ma20_slope_pct < -1.0 and ma60_slope_pct < -0.5:
            f_trend += 2.2
        elif ma20_slope_pct < -0.5:
            f_trend += 1.2
    f_trend = _clamp(f_trend, 5.0, 30.0)

    # Factor 2: Fundamental Cost & Valuation Margin (0 - 25 pts)
    low_pct_blend = 0.45 * pct_3y + 0.55 * pct_5y
    if eff_dir == "LONG":
        if cost_info and cost_info.get("anchorValid", True):
            vp = float(cost_info["vsPrimaryPct"])
            f_val = _interp(vp, [(-12.0, 23.5), (0.0, 22.0), (10.0, 19.0), (25.0, 14.5), (50.0, 9.0)])
        elif mkt == "us_stk":
            q_bonus = 3.5 if inst.get("quality_tier") == "S" else 1.5
            dd = abs(dd_52w_pct)
            f_val = q_bonus + _interp(dd, [(0.0, 14.0), (8.0, 19.5), (18.0, 20.5), (35.0, 15.0)])
        else:
            f_val = _interp(low_pct_blend, [(15.0, 22.0), (40.0, 18.5), (65.0, 14.5), (90.0, 9.5)])
    else:
        # For trend-following Short trades:
        # Best short candidates are in a confirmed downtrend AND still have ample room above extreme cash-cost floor!
        # If already crushed >8% below cash cost AND at <5% 5Y percentile (e.g. LH0/SA0), downside is compressed.
        if cost_info and cost_info.get("anchorValid", True):
            vp = float(cost_info["vsPrimaryPct"])
            f_val = _interp(vp, [(-15.0, 11.5), (-8.0, 14.5), (-3.0, 20.5), (8.0, 23.0), (25.0, 24.5)])
        else:
            f_val = _interp(low_pct_blend, [(8.0, 12.5), (25.0, 19.5), (55.0, 22.8), (85.0, 24.5)])
    f_val = _clamp(f_val, 5.0, 25.0)

    # Factor 3: Risk-Reward Ratio & Stop Structure (0 - 20 pts)
    f_rr = _interp(rr_t2, [(1.2, 8.0), (1.8, 13.5), (2.4, 17.2), (3.2, 19.5)])
    f_rr = _clamp(f_rr, 5.0, 20.0)

    # Factor 4: 5-Year Empirical Directional Performance (0 - 15 pts)
    f_emp = _interp(emp_stats["winRatePct"], [(42.0, 4.5), (52.0, 7.8), (60.0, 10.5), (68.0, 12.5)]) + _interp(
        emp_stats["expectedR"], [(-0.1, 0.0), (0.2, 1.2), (0.5, 2.2)]
    )
    f_emp = _clamp(f_emp, 3.0, 15.0)

    # Factor 5: Capital & Volatility Efficiency (0 - 10 pts)
    # Direct buying shines when IV is reasonably low/moderate (options don't pay enough premium) or trend velocity is high
    iv_discount_bonus = _interp(iv_rank, [(15.0, 8.8), (45.0, 7.2), (70.0, 5.5), (90.0, 4.2)])
    f_cap = _clamp(iv_discount_bonus + (1.0 if abs(ma20_slope_pct) >= 1.5 else 0.0), 3.0, 10.0)

    basis_adj = 0.0
    basis_note = ""
    if basis_info and basis_info.get("available"):
        if eff_dir == "LONG":
            basis_adj = float(basis_info.get("directLongAdj") or 0.0)
        else:
            basis_adj = float(basis_info.get("directShortAdj") or 0.0)
        basis_note = f"【期现差价：{basis_info.get('badge', '')}】"

    raw_direct_score = f_trend + f_val + f_rr + f_emp + f_cap + basis_adj
    if direction == "NEUTRAL_BEAR":
        # US stock in a bear channel: discourage buying the falling knife
        raw_direct_score = min(raw_direct_score, 58.0)

    direct_score = round(_clamp(raw_direct_score, 20.0, 97.5), 1)

    # -----------------------------------------------------------------------
    # 5. Head-to-Head Comparison: Direct Stock/Futures vs. Short Put
    # -----------------------------------------------------------------------
    put_strike = float(rec_put_tier.get("strike") or spot * 0.94)
    put_prem = float(rec_put_tier.get("premium") or spot * 0.015)
    put_be = float(rec_put_tier.get("breakeven") or (put_strike - put_prem))
    put_otm_pct = float(rec_put_tier.get("otmPct") or 5.0)
    put_pop_pct = float(rec_put_tier.get("popPct") or 78.0)
    put_ann_margin = float(rec_put_tier.get("annReturnMarginPct") or 20.0)
    put_ann_cash = float(rec_put_tier.get("annReturnCashPct") or 10.0)

    # Upside Crossover Point (踏空临界价): If the underlying finishes above Spot + PutPremium,
    # directly holding the underlying outperforms selling the Put!
    upside_crossover_px = round(spot + put_prem, dp)
    upside_crossover_pct = round((put_prem / spot) * 100.0, 2) if spot > 0 else 1.5
    downside_cushion_pct = round(((spot - put_be) / spot) * 100.0, 2) if spot > 0 else 6.0

    # Vehicle Decision Logic: When is Direct Trading superior to Short Put?
    if direction == "SHORT":
        optimal_vehicle = "DIRECT_SHORT"
        optimal_label = "📉 优先顺势做空期货 (严禁裸卖Put接刀)"
        optimal_tone = "bear"
        decision_reason = (
            f"当前处于【{trend_regime}】（MA20斜率 {ma20_slope_pct:+.1f}%），{basis_note}裸卖Put面临顺势破位穿仓风险；"
            f"期货具备双向交易优势，顺势做空目标看至 {cur}{target1:g} ~ {cur}{target2:g}（波段盈亏比 {rr_t2}:1）。"
        )
    elif direction == "NEUTRAL_BEAR":
        optimal_vehicle = "WAIT_OR_DEEP_PUT"
        optimal_label = "🛡️ 空头观望或仅限极深虚值牛市价差"
        optimal_tone = "neutral"
        decision_reason = (
            f"美股正股处于【{trend_regime}】，右侧企稳信号尚未确认，不宜直接重仓抄底正股；"
            f"建议等待站稳MA20，或仅用小仓位牛市看跌价差（卖 {cur}{put_strike:g} Put）博取超跌反弹。"
        )
    elif (
        direct_score >= put_score + 1.5
        or (iv_rank <= 38.0 and trend_regime in ("多头上升通道", "多头趋势回调甜点", "底部企稳筑底"))
        or (cost_info and cost_info.get("anchorValid") and cost_info.get("vsCashPct", 99) <= 2.5 and trend_regime == "底部企稳筑底")
    ):
        optimal_vehicle = "DIRECT_LONG"
        optimal_label = "🚀 优先直接做多正股/期货 (防踏空主升浪)"
        optimal_tone = "bull"
        decision_reason = (
            f"当前隐波分位较低（IVR {iv_rank:.0f}%）或正处【{trend_regime}】右侧启动点：{basis_note}"
            f"卖Put最大收益封顶仅 +{upside_crossover_pct:.1f}%（标的涨超 {cur}{upside_crossover_px:g} 即踏空），"
            f"直接做多波段目标 +{t2_pct:.1f}%（盈亏比 {rr_t2}:1，5年实证胜率 {emp_stats['winRatePct']:.1f}%），向上赔率远超卖Put！"
        )
    elif direct_score >= 78.0 and put_score >= 80.0:
        optimal_vehicle = "HYBRID_COMBO"
        optimal_label = "⚖️ 黄金组合：50%直接做多 + 50%卖Put收租"
        optimal_tone = "cyan"
        decision_reason = (
            f"趋势与波动率双优（直买评分 {direct_score} / 卖Put评分 {put_score}）：{basis_note}"
            f"建议【半仓直接做多】锁定上方 +{t2_pct:.1f}% 波段主升空间，同时【半仓卖出 {cur}{put_strike:g} Put】"
            f"（安全垫 -{downside_cushion_pct:.1f}%）收租降低整体持仓成本！"
        )
    else:
        optimal_vehicle = "SHORT_PUT"
        optimal_label = "🛡️ 优先卖Put收租 (高胜率安全垫占优)"
        optimal_tone = "gold"
        decision_reason = (
            f"当前处于【{trend_regime}】且隐波溢价丰厚（IVR {iv_rank:.0f}%，VRP {vrp_pts:+.1f}%）：{basis_note}"
            f"直接追多胜率（{emp_stats['winRatePct']:.1f}%）不及卖Put双轨胜率（{put_pop_pct:.1f}%），"
            f"卖 {cur}{put_strike:g} Put 可享 -{downside_cushion_pct:.1f}% 抗跌缓冲垫并躺赚时间价值。"
        )

    # -----------------------------------------------------------------------
    # 6. Action Signal Badge & 1% Account Risk Position Sizing
    # -----------------------------------------------------------------------
    if direction == "SHORT":
        if direct_score >= 76.0:
            sig_badge = "🔴 强力顺势做空 (期货)"
            sig_tone = "bear"
        else:
            sig_badge = "🟠 逢高顺势试空 (期货)"
            sig_tone = "gold"
        action_type = "SHORT_FUTURES"
        action_label = "做空期货"
        if spot < ma20 and ma20 < ma60 and ma20_slope_pct < -1.0:
            setup_archetype = f"均线空头排列 · 顺势主跌段 (MA20斜率 {ma20_slope_pct:+.1f}%)"
        elif trend_regime == "空头阴跌通道":
            setup_archetype = f"空头阴跌通道 · 反抽MA20做空 (近1月 {ret_1m:+.1f}%)"
        else:
            setup_archetype = f"空头破位下行 · 顺势跟空 (近1月 {ret_1m:+.1f}%)"
    elif direction == "NEUTRAL_BEAR":
        sig_badge = "⚪ 空头未企稳·暂缓买多"
        sig_tone = "neutral"
        action_type = "WAIT"
        action_label = "观望防飞刀"
        setup_archetype = "空头通道未企稳 · 等待右侧信号"
    else:
        if direct_score >= 83.0:
            sig_badge = f"🟢 强烈推荐做多 ({'正股/ETF' if mkt == 'us_stk' else '期货'})"
            sig_tone = "bull"
        elif direct_score >= 74.0:
            sig_badge = f"🟢 逢低分批做多 ({'正股/ETF' if mkt == 'us_stk' else '期货'})"
            sig_tone = "bull"
        else:
            sig_badge = "🟡 区间震荡·优先卖Put"
            sig_tone = "gold"
        action_type = "LONG_STOCK" if mkt == "us_stk" else "LONG_FUTURES"
        action_label = "买多正股/ETF" if mkt == "us_stk" else "做多期货"
        if trend_regime == "多头趋势回调甜点":
            setup_archetype = "多头回踩MA20 · 顺势低吸甜点"
        elif trend_regime == "多头上升通道":
            setup_archetype = f"均线多头排列 · 顺势主升浪 (MA20斜率 {ma20_slope_pct:+.1f}%)"
        elif trend_regime == "底部企稳筑底":
            setup_archetype = "成本底右侧放量 · 筑底反转做多"
        elif trend_regime == "回调测试支撑":
            setup_archetype = "回踩关键结构支撑 · 博弈波段反弹"
        else:
            setup_archetype = f"{trend_regime} · 逢低分批布局"

    # Position sizing based on 100,000 reference capital ($100k for US, ¥300k for CN futures) risking 1.5% per trade
    ref_capital = 100000.0 if mkt == "us_stk" else (150000.0 if mkt == "us_fut" else 300000.0)
    risk_budget = ref_capital * 0.015
    unit_risk_cash = stop_dist * (1.0 if mkt == "us_stk" else mult)
    if mkt == "us_stk":
        rec_units = max(10, int(round(risk_budget / max(stop_dist, 0.01) / 5.0) * 5))
        notional_val = round(rec_units * spot, 0)
        margin_or_cash = notional_val
        eff_lev = 1.0
    else:
        rec_units = max(1, int(round(risk_budget / max(unit_risk_cash, 1.0))))
        notional_val = round(rec_units * spot * mult, 0)
        margin_or_cash = round(notional_val * margin_rate, 0)
        eff_lev = round(1.0 / max(margin_rate, 0.05), 1)

    unit_name = "股" if mkt == "us_stk" else "手"
    contract_t1_profit = round(abs(target1 - spot) * (rec_units if mkt == "us_stk" else rec_units * mult), 0)
    contract_t2_profit = round(abs(target2 - spot) * (rec_units if mkt == "us_stk" else rec_units * mult), 0)
    contract_stop_loss = round(stop_dist * (rec_units if mkt == "us_stk" else rec_units * mult), 0)

    return {
        "direction": direction,
        "effectiveDirection": eff_dir,
        "actionType": action_type,
        "actionLabel": action_label,
        "directScore": direct_score,
        "signalBadge": sig_badge,
        "actionBadge": sig_badge,
        "setupArchetype": setup_archetype,
        "unitLabel": unit_name,
        "signalTone": sig_tone,
        "scoreBreakdown": {
            "trend": round(f_trend, 1),   # /30
            "val": round(f_val, 1),       # /25
            "rr": round(f_rr, 1),         # /20
            "emp": round(f_emp, 1),       # /15
            "cap": round(f_cap, 1),       # /10
            "basisAdj": round(basis_adj, 1),
        },
        "basis": basis_info,
        "tradePlan": {
            "spotEntry": round(spot, dp),
            "idealEntry": ideal_entry,
            "breakoutEntry": breakout_entry,
            "stopLoss": stop_loss,
            "stopLossPct": round(stop_pct, 2),
            "target1": target1,
            "target1Pct": round(t1_pct, 2),
            "target2": target2,
            "target2Pct": round(t2_pct, 2),
            "rrRatioT1": rr_t1,
            "rrRatioT2": rr_t2,
            "atrStopMultiple": 2.0,
        },
        "sizing": {
            "refCapital": ref_capital,
            "recUnits": rec_units,
            "unitName": unit_name,
            "notionalValue": notional_val,
            "marginOrCashReq": margin_or_cash,
            "effectiveLeverage": eff_lev,
            "estProfitT1": contract_t1_profit,
            "estProfitT2": contract_t2_profit,
            "maxStopLossAmt": contract_stop_loss,
        },
        "empirical": emp_stats,
        "vsPut": {
            "optimalVehicle": optimal_vehicle,
            "optimalLabel": optimal_label,
            "optimalTone": optimal_tone,
            "upsideCrossoverPx": upside_crossover_px,
            "upsideCrossoverPct": upside_crossover_pct,
            "downsideCushionPx": round(put_be, dp),
            "downsideCushionPct": downside_cushion_pct,
            "putMaxReturnPct": upside_crossover_pct,
            "directWaveReturnPct": round(t2_pct, 2),
            "putWinRatePct": put_pop_pct,
            "directWinRatePct": emp_stats["winRatePct"],
            "putAnnMarginPct": put_ann_margin,
            "putAnnCashPct": put_ann_cash,
            "decisionReason": decision_reason,
        },
    }
