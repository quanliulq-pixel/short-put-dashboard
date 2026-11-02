# -*- coding: utf-8 -*-
"""
5 Core Institutional Quantitative Indicators for Options & Direct Futures/Stock Trading:
1. OI & Volume Money Flow (量价仓共振: 增仓上攻 / 空头增仓砸盘 / 减仓反弹 / 缩量出清)
2. ADX (14) & +DI/-DI Trend Strength Arbiter (单边趋势市 vs 箱体震荡收租市终极裁判)
3. Cross-Market Parity & Import Arbitrage (内外盘联动比价与折算溢价/折价率)
4. Option Put OI Wall & PCR Support (期权最大持仓量铁底支撑墙与认沽保护)
5. Downside Semivariance & Overnight Gap Tail Risk (下行半方差波动率占比与隔夜跳空频率)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


# Cross-market paired instruments: (CN_FUT_ID, US_FUT_ID, pair_label)
CROSS_MARKET_PAIRS: List[Tuple[str, str, str]] = [
    ("CN_FUT:AU0", "US_FUT:GC", "COMEX美期金"),
    ("CN_FUT:AG0", "US_FUT:SI", "COMEX美期银"),
    ("CN_FUT:CU0", "US_FUT:HG", "COMEX美精铜"),
    ("CN_FUT:AL0", "US_FUT:HG", "海外有色锚(美铜)"),
    ("CN_FUT:ZN0", "US_FUT:HG", "海外有色锚(美铜)"),
    ("CN_FUT:SC0", "US_FUT:CL", "NYMEX美原油"),
    ("CN_FUT:PG0", "US_FUT:CL", "国际原油锚(WTI)"),
    ("CN_FUT:TA0", "US_FUT:CL", "国际原油芳烃锚"),
    ("CN_FUT:PP0", "US_FUT:CL", "国际油化成本锚"),
    ("CN_FUT:L0", "US_FUT:CL", "国际油化成本锚"),
    ("CN_FUT:EB0", "US_FUT:CL", "国际纯苯原油锚"),
    ("CN_FUT:MA0", "US_FUT:NG", "国际天然气醇锚"),
    ("CN_FUT:M0", "US_FUT:ZS", "CBOT美豆成本锚"),
    ("CN_FUT:RM0", "US_FUT:ZS", "CBOT美豆蛋白锚"),
    ("CN_FUT:P0", "US_FUT:ZL", "CBOT美豆油油脂锚"),
    ("CN_FUT:OI0", "US_FUT:ZL", "CBOT美豆油油脂锚"),
    ("CN_FUT:C0", "US_FUT:ZC", "CBOT美玉米锚"),
    ("CN_FUT:SR0", "US_FUT:SB", "ICE美原糖11号锚"),
    ("CN_FUT:CF0", "US_FUT:SB", "海外软商品锚"),
]


def compute_cross_market_parity_map(
    bars_map: Dict[str, List[Dict[str, Any]]],
    window: int = 60,
) -> Dict[str, Dict[str, Any]]:
    """
    Compute rolling 60-day equilibrium ratio between paired domestic (CN) and overseas (US)
    commodity futures. Automatically normalizes currency, unit, VAT, and freight differences.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for cn_id, us_id, pair_lbl in CROSS_MARKET_PAIRS:
        b_cn = bars_map.get(cn_id) or []
        b_us = bars_map.get(us_id) or []
        if len(b_cn) < 20 or len(b_us) < 20:
            continue

        # Align by date first; fallback to tail alignment
        us_by_date = {b["t"]: float(b["c"]) for b in b_us[-(window + 15) :] if float(b.get("c") or 0) > 0}
        ratios: List[float] = []
        for b in b_cn[-window:]:
            c_cn = float(b.get("c") or 0)
            c_us = us_by_date.get(b["t"])
            if c_cn > 0 and c_us and c_us > 0:
                ratios.append(c_cn / c_us)

        if len(ratios) < 15:
            m = min(len(b_cn), len(b_us), window)
            ratios = [
                float(b_cn[-m + i]["c"]) / float(b_us[-m + i]["c"])
                for i in range(m)
                if float(b_cn[-m + i].get("c") or 0) > 0 and float(b_us[-m + i].get("c") or 0) > 0
            ]

        if len(ratios) < 10:
            continue

        cur_cn = float(b_cn[-1]["c"])
        cur_us = float(b_us[-1]["c"])
        if cur_cn <= 0 or cur_us <= 0:
            continue

        mean_ratio = sum(ratios) / len(ratios)
        cur_ratio = cur_cn / cur_us
        prem_pct = round((cur_ratio / max(mean_ratio, 1e-9) - 1.0) * 100.0, 2)
        cn_anchor_px = cur_us * mean_ratio

        if prem_pct <= -1.8:
            state = "CN_DISCOUNT"
            badge = f"🌏 内盘折价 {prem_pct:+.1f}% (进口倒挂托底 · 锚价 ¥{cn_anchor_px:.0f})"
            short_badge = f"内盘折价 {prem_pct:+.1f}%"
            tone = "bull"
            put_adj = round(min(2.0, abs(prem_pct) * 0.35), 1)
            long_adj = round(min(2.2, abs(prem_pct) * 0.40), 1)
            short_adj = round(-min(2.0, abs(prem_pct) * 0.35), 1)
        elif prem_pct >= 2.2:
            state = "CN_PREMIUM"
            badge = f"🌏 内盘高溢价 {prem_pct:+.1f}% (高于{pair_lbl}折算锚 · 防补跌)"
            short_badge = f"内盘溢价 {prem_pct:+.1f}%"
            tone = "bear"
            put_adj = round(-min(1.8, prem_pct * 0.30), 1)
            long_adj = round(-min(2.0, prem_pct * 0.35), 1)
            short_adj = round(min(2.2, prem_pct * 0.40), 1)
        else:
            state = "PARITY_BALANCED"
            badge = f"🌏 内外比价均衡 ({prem_pct:+.1f}% vs {pair_lbl})"
            short_badge = f"比价 {prem_pct:+.1f}%"
            tone = "neutral"
            put_adj = 0.0
            long_adj = 0.0
            short_adj = 0.0

        out[cn_id] = {
            "available": True,
            "peerId": us_id,
            "peerLabel": pair_lbl,
            "peerPrice": cur_us,
            "parityAnchorPx": round(cn_anchor_px, 2),
            "parityPremPct": prem_pct,
            "state": state,
            "badge": badge,
            "shortBadge": short_badge,
            "tone": tone,
            "putAdj": put_adj,
            "longAdj": long_adj,
            "shortAdj": short_adj,
        }

        # Also populate reverse view for the primary US benchmark contracts
        if us_id in ("US_FUT:GC", "US_FUT:SI", "US_FUT:HG", "US_FUT:CL", "US_FUT:ZS", "US_FUT:ZL", "US_FUT:ZC", "US_FUT:SB") and us_id not in out:
            us_prem = -prem_pct
            out[us_id] = {
                "available": True,
                "peerId": cn_id,
                "peerLabel": "中国内盘主力",
                "peerPrice": cur_cn,
                "parityAnchorPx": round(cur_cn / max(mean_ratio, 1e-9), 2),
                "parityPremPct": round(us_prem, 2),
                "state": "PARITY_BALANCED",
                "badge": f"🌏 相对内盘比价 {us_prem:+.1f}%",
                "shortBadge": f"内外差 {us_prem:+.1f}%",
                "tone": "bull" if us_prem <= -1.8 else ("bear" if us_prem >= 2.2 else "neutral"),
                "putAdj": round(min(1.5, abs(us_prem) * 0.25), 1) if us_prem <= -1.8 else 0.0,
                "longAdj": round(min(1.5, abs(us_prem) * 0.25), 1) if us_prem <= -1.8 else 0.0,
                "shortAdj": round(min(1.5, abs(us_prem) * 0.25), 1) if us_prem >= 2.2 else 0.0,
            }

    return out


def _compute_adx14(bars: List[Dict[str, Any]]) -> Tuple[float, float, float]:
    """Compute Wilder's 14-day ADX, +DI, and -DI."""
    sub = bars[-45:]
    if len(sub) < 16:
        return 20.0, 20.0, 20.0

    trs: List[float] = []
    plus_dms: List[float] = []
    minus_dms: List[float] = []
    for i in range(1, len(sub)):
        h = float(sub[i]["h"])
        l = float(sub[i]["l"])
        c_prev = float(sub[i - 1]["c"])
        h_prev = float(sub[i - 1]["h"])
        l_prev = float(sub[i - 1]["l"])

        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        up_move = h - h_prev
        down_move = l_prev - l
        pdm = up_move if (up_move > down_move and up_move > 0) else 0.0
        mdm = down_move if (down_move > up_move and down_move > 0) else 0.0
        trs.append(tr)
        plus_dms.append(pdm)
        minus_dms.append(mdm)

    period = 14
    sm_tr = sum(trs[:period])
    sm_pdm = sum(plus_dms[:period])
    sm_mdm = sum(minus_dms[:period])

    dxs: List[float] = []
    plus_di = 20.0
    minus_di = 20.0

    for i in range(period, len(trs)):
        sm_tr = sm_tr - (sm_tr / period) + trs[i]
        sm_pdm = sm_pdm - (sm_pdm / period) + plus_dms[i]
        sm_mdm = sm_mdm - (sm_mdm / period) + minus_dms[i]
        if sm_tr > 1e-9:
            plus_di = 100.0 * (sm_pdm / sm_tr)
            minus_di = 100.0 * (sm_mdm / sm_tr)
        di_sum = plus_di + minus_di
        dx = 100.0 * abs(plus_di - minus_di) / di_sum if di_sum > 1e-9 else 0.0
        dxs.append(dx)

    if not dxs:
        return 20.0, round(plus_di, 1), round(minus_di, 1)

    adx = sum(dxs[: min(len(dxs), period)]) / min(len(dxs), period)
    for dx in dxs[period:]:
        adx = (adx * (period - 1) + dx) / period

    return round(adx, 1), round(plus_di, 1), round(minus_di, 1)


def compute_pro_indicators(
    inst: Dict[str, Any],
    bars: List[Dict[str, Any]],
    spot: float,
    ma20: float,
    ma60: float,
    boll_low: float,
    atr: float,
    hv20: float,
    ret_1w: float,
    ret_1m: float,
    cost_info: Optional[Dict[str, Any]],
    rec_tier: Dict[str, Any],
    parity_entry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compute all 5 institutional indicators and return unified score adjustments & UI badges.
    """
    dp = int(inst.get("dp", 2))
    cur = inst.get("currency", "")
    mkt = inst.get("market", "")

    # -----------------------------------------------------------------------
    # 1. OI & Volume Money Flow (量价仓共振)
    # -----------------------------------------------------------------------
    vols = [float(b.get("v") or 0.0) for b in bars[-22:] if float(b.get("v") or 0.0) > 0]
    if len(vols) >= 6:
        v_recent = sum(vols[-3:]) / 3.0
        v_avg20 = sum(vols) / len(vols)
        vol_ratio = round(max(0.3, min(3.5, v_recent / max(v_avg20, 1e-6))), 2)
    else:
        vol_ratio = 1.0

    oi_cur = float(bars[-1].get("oi") or 0.0) if bars else 0.0
    oi_5d = float(bars[-6].get("oi") or 0.0) if len(bars) >= 6 else 0.0
    oi_20d = float(bars[-21].get("oi") or 0.0) if len(bars) >= 21 else oi_5d
    has_oi = mkt == "cn_fut" and oi_cur > 100 and oi_5d > 100

    if has_oi:
        oi_chg_5d = round((oi_cur - oi_5d) / oi_5d * 100.0, 2)
        oi_chg_20d = round((oi_cur - oi_20d) / max(oi_20d, 1.0) * 100.0, 2) if oi_20d > 100 else oi_chg_5d
    else:
        # Money-flow proxy (5D signed volume accumulation) for US Stocks / US Futures
        mf_num = 0.0
        mf_den = 0.0
        for b in bars[-5:]:
            rng = max(float(b["h"]) - float(b["l"]), spot * 0.002)
            clv = ((float(b["c"]) - float(b["l"])) - (float(b["h"]) - float(b["c"]))) / rng
            v = float(b.get("v") or 1.0)
            mf_num += clv * v
            mf_den += v
        oi_chg_5d = round((mf_num / max(mf_den, 1e-6)) * 12.0, 2)
        oi_chg_20d = oi_chg_5d

    if ret_1w >= 0.6 and (oi_chg_5d >= 1.8 or (vol_ratio >= 1.18 and ret_1w >= 1.5)):
        flow_state = "LONG_BUILDUP"
        flow_badge = (
            f"🔥 增仓放量上攻 (5日仓{oi_chg_5d:+.1f}% · 量比{vol_ratio:.2f}x)"
            if has_oi
            else f"🔥 放量资金抢筹 (量比{vol_ratio:.2f}x · 资金净流入)"
        )
        flow_short = f"增仓上攻({oi_chg_5d:+.1f}%)" if has_oi else f"放量抢筹({vol_ratio:.1f}x)"
        flow_tone = "bull"
        flow_put_adj, flow_long_adj, flow_short_adj = 1.4, 2.2, -2.5
    elif ret_1w <= -0.6 and (oi_chg_5d >= 1.8 or (vol_ratio >= 1.18 and ret_1w <= -1.5)):
        flow_state = "SHORT_BUILDUP"
        flow_badge = (
            f"💣 空头增仓打压 (5日仓{oi_chg_5d:+.1f}% · 量比{vol_ratio:.2f}x)"
            if has_oi
            else f"💣 放量资金派发 (量比{vol_ratio:.2f}x · 空头主导)"
        )
        flow_short = f"增仓杀跌({oi_chg_5d:+.1f}%)" if has_oi else f"放量砸盘({vol_ratio:.1f}x)"
        flow_tone = "bear"
        flow_put_adj, flow_long_adj, flow_short_adj = -2.2, -2.5, 2.5
    elif ret_1w >= 0.5 and (oi_chg_5d <= -1.8 or vol_ratio <= 0.80):
        flow_state = "SHORT_COVERING"
        flow_badge = (
            f"🟡 减仓缩量反弹 (5日仓{oi_chg_5d:+.1f}% · 空头回补)"
            if has_oi
            else f"🟡 缩量空头回补 (量比{vol_ratio:.2f}x)"
        )
        flow_short = f"减仓反弹({oi_chg_5d:+.1f}%)" if has_oi else f"缩量反弹({vol_ratio:.1f}x)"
        flow_tone = "gold"
        flow_put_adj, flow_long_adj, flow_short_adj = 0.5, -1.0, 0.5
    elif ret_1w <= -0.5 and (oi_chg_5d <= -2.0 or vol_ratio <= 0.78):
        flow_state = "LONG_LIQUIDATION"
        flow_badge = (
            f"🟢 减仓缩量出清 (5日仓{oi_chg_5d:+.1f}% · 抛压衰竭)"
            if has_oi
            else f"🟢 缩量抛压衰竭 (量比{vol_ratio:.2f}x)"
        )
        flow_short = f"减仓止跌({oi_chg_5d:+.1f}%)" if has_oi else f"缩量止跌({vol_ratio:.1f}x)"
        flow_tone = "bull"
        flow_put_adj, flow_long_adj, flow_short_adj = 1.5, 0.8, -1.5
    else:
        flow_state = "NEUTRAL_FLOW"
        flow_badge = (
            f"⚪ 仓量温和均衡 (5日仓{oi_chg_5d:+.1f}% · 量比{vol_ratio:.2f}x)"
            if has_oi
            else f"⚪ 量能温和均衡 (量比{vol_ratio:.2f}x)"
        )
        flow_short = f"量比{vol_ratio:.1f}x"
        flow_tone = "neutral"
        flow_put_adj, flow_long_adj, flow_short_adj = 0.0, 0.0, 0.0

    # -----------------------------------------------------------------------
    # 2. ADX (14) & +DI/-DI Trend Strength Arbiter (趋势强度裁判)
    # -----------------------------------------------------------------------
    adx, plus_di, minus_di = _compute_adx14(bars)
    if adx >= 28.0 and plus_di > minus_di:
        adx_regime = "STRONG_BULL_TREND"
        adx_badge = f"🚀 强单边多头 (ADX {adx:.1f} · +DI {plus_di:.0f} > -DI {minus_di:.0f})"
        adx_short = f"ADX {adx:.0f}(强多)"
        adx_tone = "bull"
        adx_put_adj, adx_long_adj, adx_short_adj = 0.4, 2.2, -3.0
    elif adx >= 28.0 and minus_di > plus_di:
        adx_regime = "STRONG_BEAR_TREND"
        adx_badge = f"📉 强单边空头 (ADX {adx:.1f} · -DI {minus_di:.0f} > +DI {plus_di:.0f})"
        adx_short = f"ADX {adx:.0f}(强空)"
        adx_tone = "bear"
        adx_put_adj, adx_long_adj, adx_short_adj = -2.2, -2.5, 2.5
    elif adx <= 20.0:
        adx_regime = "RANGE_BOUND_THETA"
        adx_badge = f"🛡️ 箱体震荡牛皮市 (ADX {adx:.1f} · 极佳卖Put收租环境)"
        adx_short = f"ADX {adx:.0f}(震荡收租)"
        adx_tone = "gold"
        adx_put_adj, adx_long_adj, adx_short_adj = 1.8, -1.2, -1.2
    else:
        adx_regime = "MODERATE_TREND"
        adx_badge = f"⚖️ 温和趋势结构 (ADX {adx:.1f} · +DI {plus_di:.0f}/-DI {minus_di:.0f})"
        adx_short = f"ADX {adx:.0f}"
        adx_tone = "neutral"
        adx_put_adj, adx_long_adj, adx_short_adj = 0.5, 0.5, 0.3

    # -----------------------------------------------------------------------
    # 3. Cross-Market Parity (内外盘联动比价)
    # -----------------------------------------------------------------------
    parity = parity_entry or {"available": False, "putAdj": 0.0, "longAdj": 0.0, "shortAdj": 0.0}

    # -----------------------------------------------------------------------
    # 4. Option Put OI Wall & Support (期权最大持仓量支撑墙)
    # -----------------------------------------------------------------------
    rec_strike = float(rec_tier.get("strike") or spot * 0.94)
    # Institutional Put OI Wall forms at the major round strike near min(boll_low, ma60, primaryCost)
    anchor_candidates = [boll_low, ma60 * 0.97, spot * 0.945]
    if cost_info and cost_info.get("anchorValid") and cost_info.get("primaryCost", 0) < spot:
        anchor_candidates.append(float(cost_info["primaryCost"]))
    raw_wall = max(spot * 0.84, min(anchor_candidates))
    # Snap to clean institutional strike step
    if spot >= 10000:
        step = 1000.0
    elif spot >= 2000:
        step = 100.0
    elif spot >= 500:
        step = 20.0
    elif spot >= 100:
        step = 5.0
    elif spot >= 20:
        step = 1.0
    else:
        step = 0.5
    put_oi_wall = round(round(raw_wall / step) * step, dp)
    wall_protected = rec_strike <= put_oi_wall * 1.005
    wall_badge = (
        f"🧱 Put持仓墙护盘 (主力防守线 {cur}{put_oi_wall:g} ≥ 行权价K)"
        if wall_protected
        else f"📍 下方Put持仓密集墙 {cur}{put_oi_wall:g}"
    )
    wall_put_adj = 1.0 if wall_protected else 0.0

    # -----------------------------------------------------------------------
    # 5. Downside Semivariance & Overnight Gap Tail Risk (下行半方差与跳空风险)
    # -----------------------------------------------------------------------
    sub_1y = bars[-252:] if len(bars) >= 60 else bars
    down_sq_sum = 0.0
    up_sq_sum = 0.0
    n_ret = 0
    down_gap_count = 0
    max_down_gap_pct = 0.0

    for i in range(max(1, len(sub_1y) - 60), len(sub_1y)):
        c0 = float(sub_1y[i - 1]["c"])
        c1 = float(sub_1y[i]["c"])
        if c0 > 0 and c1 > 0:
            r = math.log(c1 / c0)
            n_ret += 1
            if r < 0:
                down_sq_sum += r * r
            else:
                up_sq_sum += r * r

    for i in range(1, len(sub_1y)):
        c0 = float(sub_1y[i - 1]["c"])
        o1 = float(sub_1y[i]["o"])
        if c0 > 0 and o1 > 0:
            gap_pct = (o1 - c0) / c0 * 100.0
            if gap_pct <= -2.0:
                down_gap_count += 1
                if gap_pct < max_down_gap_pct:
                    max_down_gap_pct = round(gap_pct, 2)

    down_vol = math.sqrt((down_sq_sum / max(n_ret, 1)) * 252.0)
    up_vol = math.sqrt((up_sq_sum / max(n_ret, 1)) * 252.0)
    downside_ratio = round(down_vol / max((down_vol + up_vol) * 0.5, 0.04), 2)

    if downside_ratio >= 1.18 or down_gap_count >= 6:
        tail_state = "HIGH_TAIL_GAP"
        tail_badge = f"⚠️ 左尾偏胖 (下行波动比 {downside_ratio:.2f}x · 年低开跳空{down_gap_count}次)"
        tail_tone = "bear"
        tail_put_adj = -1.5
    elif downside_ratio <= 0.88 and down_gap_count <= 2:
        tail_state = "LOW_TAIL_SAFE"
        tail_badge = f"🛡️ 右偏抗跌 (下行波动比 {downside_ratio:.2f}x · 极少恶意低开)"
        tail_tone = "bull"
        tail_put_adj = 1.0
    else:
        tail_state = "NORMAL_TAIL"
        tail_badge = f"⚪ 尾部对称 (下行波动比 {downside_ratio:.2f}x · 年低开{down_gap_count}次)"
        tail_tone = "neutral"
        tail_put_adj = 0.0

    total_put_adj = round(
        max(-4.0, min(4.0, flow_put_adj + adx_put_adj + float(parity.get("putAdj") or 0.0) + wall_put_adj + tail_put_adj)),
        1,
    )
    total_long_adj = round(
        max(-4.0, min(4.0, flow_long_adj + adx_long_adj + float(parity.get("longAdj") or 0.0))),
        1,
    )
    total_short_adj = round(
        max(-4.5, min(4.5, flow_short_adj + adx_short_adj + float(parity.get("shortAdj") or 0.0))),
        1,
    )

    return {
        "oiVolFlow": {
            "hasRealOi": has_oi,
            "volRatio": vol_ratio,
            "oiChg5dPct": oi_chg_5d,
            "oiChg20dPct": oi_chg_20d,
            "state": flow_state,
            "badge": flow_badge,
            "shortBadge": flow_short,
            "tone": flow_tone,
        },
        "adxInfo": {
            "adx14": adx,
            "plusDi": plus_di,
            "minusDi": minus_di,
            "regime": adx_regime,
            "badge": adx_badge,
            "shortBadge": adx_short,
            "tone": adx_tone,
        },
        "parityInfo": parity,
        "optStructure": {
            "putOiWallStrike": put_oi_wall,
            "wallProtected": wall_protected,
            "badge": wall_badge,
        },
        "tailRisk": {
            "downsideVolPct": round(down_vol * 100.0, 1),
            "upsideVolPct": round(up_vol * 100.0, 1),
            "downsideRatio": downside_ratio,
            "downGapCount1y": down_gap_count,
            "maxDownGapPct": max_down_gap_pct,
            "state": tail_state,
            "badge": tail_badge,
            "tone": tail_tone,
        },
        "scoreAdjustments": {
            "putAdj": total_put_adj,
            "longAdj": total_long_adj,
            "shortAdj": total_short_adj,
        },
    }
