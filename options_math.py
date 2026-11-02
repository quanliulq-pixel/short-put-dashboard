# -*- coding: utf-8 -*-
"""
Quantitative Option Pricing, Greeks, Strike Solver & Payoff Engine for Short Put Strategies.
Supports:
- Black-Scholes-Merton (Stocks/ETFs)
- Black-76 (Commodity/Financial Futures, incl. CFFEX MO/IO/HO priced off the index futures)
- Empirical left-tail haircut (heuristic fat-tail discount on strike & probability; NOT a full Cornish-Fisher expansion)
- Risk-Adjusted Carry Metrics (ATR Safety Cushion Multiple, Return-to-Vol Ratio, Theta/Vega)
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Dict, List, Optional

_STD_NORM = NormalDist(0.0, 1.0)
SQRT_2PI = math.sqrt(2.0 * math.pi)

# CFFEX index options (MO/IO/HO): the engine prices off the IM0/IF0/IH0 futures price with Black-76.
# A futures price already embeds the index discount (贴水), so an extra drift here would double-count it.
# Keep b = 0 for all futures (standard Black-76). Left as an explicit, empty override table.
_CFFEX_BASIS_DRIFT: Dict[str, float] = {}

# Asset-specific left-tail excess kurtosis factor (0.0 = Gaussian, higher = fatter left tail)
_FAT_TAIL_FACTOR: Dict[str, float] = {
    "IM0": 0.28,
    "TSLA": 0.30,
    "IBIT": 0.32,
    "NG=F": 0.32,
    "LC0": 0.28,
    "SA0": 0.25,
    "SI0": 0.24,
    "FG0": 0.22,
    "SI=F": 0.24,
    "AG0": 0.24,
    "PLTR": 0.26,
    "PDD": 0.24,
    "BABA": 0.22,
}


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI


def _norm_ppf(p: float) -> float:
    p = max(1e-6, min(1.0 - 1e-6, p))
    return float(_STD_NORM.inv_cdf(p))


def dynamic_strike_step(spot: float, default_step: float, dp: int = 2) -> float:
    """Ensure strike step is well-proportioned to current spot price."""
    if spot <= 0:
        return default_step
    ratio = default_step / spot
    if 0.002 <= ratio <= 0.035:
        return default_step
    # Calibrate step to ~1% of spot
    raw = spot * 0.01
    mag = 10 ** math.floor(math.log10(max(raw, 1e-4)))
    for m in (1.0, 2.0, 2.5, 5.0, 10.0):
        cand = mag * m
        if cand >= raw * 0.75:
            return round(cand, dp + 1)
    return default_step


def round_to_step(val: float, step: float, dp: int = 2) -> float:
    if step <= 0:
        return round(val, dp)
    rounded = round(val / step) * step
    return round(rounded, max(dp, 3 if step < 0.1 else 2))


def skew_adjusted_iv(
    atm_iv: float,
    spot: float,
    strike: float,
    skew_coeff: float = 0.12,
    fat_tail: float = 0.12,
) -> float:
    """
    Model the empirical OTM Put volatility smile/skew + left-tail kurtosis curvature:
    Lower strikes carry higher implied volatility due to crash-protection demand.
    """
    if spot <= 0 or strike <= 0:
        return atm_iv
    moneyness = math.log(spot / strike)  # > 0 for OTM put (strike < spot)
    if moneyness >= 0:
        # OTM put linear skew + quadratic fat-tail smile curvature
        curve_coeff = 0.025 + 0.06 * fat_tail
        adj = 1.0 + skew_coeff * (moneyness / 0.10) + curve_coeff * ((moneyness / 0.10) ** 2)
    else:
        # Slightly ITM put
        adj = 1.0 + 0.03 * (abs(moneyness) / 0.10)
    adj = max(0.90, min(adj, 1.65))
    return max(0.06, min(atm_iv * adj, 2.50))


def price_put_and_greeks(
    spot: float,
    strike: float,
    dte: int,
    iv: float,
    r: float = 0.04,
    is_futures: bool = False,
    basis_drift: float = 0.0,
    fat_tail: float = 0.12,
) -> Dict[str, float]:
    """
    Calculate Put option price, Delta, Gamma, Theta (per calendar day), Vega (per 1% IV),
    and fat-tail adjusted probabilities using BSM (equity) or Black-76 (futures).
    """
    T = max(int(dte), 1) / 365.0
    sigma = max(float(iv), 0.04)
    sqrt_T = math.sqrt(T)
    vol_sqrt_T = sigma * sqrt_T

    # Drift of underlying under risk-neutral measure:
    # 0 for standard futures (Black-76), basis_drift for CFFEX index options, r for spot (BSM)
    b = basis_drift if is_futures else r

    d1 = (math.log(spot / strike) + (b + 0.5 * sigma * sigma) * T) / vol_sqrt_T
    d2 = d1 - vol_sqrt_T

    df_r = math.exp(-r * T)
    df_b = math.exp((b - r) * T)

    put_price = strike * df_r * _norm_cdf(-d2) - spot * df_b * _norm_cdf(-d1)
    put_price = max(put_price, spot * 0.0002)

    # Put Delta: in [-1, 0]
    delta = -df_b * _norm_cdf(-d1)
    gamma = (df_b * _norm_pdf(d1)) / (spot * vol_sqrt_T)
    # Vega per 1% (0.01) vol change
    vega = spot * df_b * _norm_pdf(d1) * sqrt_T * 0.01

    # Put Theta (per year -> divide by 365 for daily time decay earned by short put)
    term1 = -(spot * df_b * _norm_pdf(d1) * sigma) / (2.0 * sqrt_T)
    if is_futures:
        theta_annual = term1 + r * strike * df_r * _norm_cdf(-d2) - r * spot * df_b * _norm_cdf(-d1)
    else:
        theta_annual = term1 + r * strike * df_r * _norm_cdf(-d2)
    theta_daily = theta_annual / 365.0

    # Breakeven & Fat-Tail Adjusted Probability of Profit (PoP = Prob(S_T > Breakeven))
    breakeven = max(strike - put_price, strike * 0.5)
    d2_be = (math.log(spot / breakeven) + (b - 0.5 * sigma * sigma) * T) / vol_sqrt_T

    # Empirical left-tail haircut (heuristic): real returns have heavier left tails than Gaussian
    tail_haircut = 1.0 + 0.18 * fat_tail
    d2_be_adj = d2_be / tail_haircut if d2_be > 0 else d2_be * tail_haircut
    d2_otm_adj = d2 / tail_haircut if d2 > 0 else d2 * tail_haircut

    pop_pct = _norm_cdf(d2_be_adj) * 100.0
    prob_otm_pct = _norm_cdf(d2_otm_adj) * 100.0
    prob_touch_pct = min(99.0, max(1.0, (1.0 - _norm_cdf(d2_otm_adj)) * 195.0))

    return {
        "premium": put_price,
        "breakeven": breakeven,
        "delta": delta,
        "gamma": gamma,
        "theta_daily": abs(theta_daily),  # Daily theta collected by seller
        "vega": vega,
        "pop_pct": pop_pct,
        "prob_otm_pct": prob_otm_pct,
        "prob_touch_pct": prob_touch_pct,
    }


def price_call_and_greeks(
    spot: float,
    strike: float,
    dte: int,
    iv: float,
    r: float = 0.04,
    is_futures: bool = False,
    basis_drift: float = 0.0,
) -> Dict[str, float]:
    """
    Calculate Call option price, Delta, Gamma, Theta (per calendar day), Vega (per 1% IV),
    and probability of expiring OTM for Covered Call (Wheel Strategy Phase 2).
    """
    T = max(int(dte), 1) / 365.0
    sigma = max(float(iv), 0.04)
    sqrt_T = math.sqrt(T)
    vol_sqrt_T = sigma * sqrt_T
    b = basis_drift if is_futures else r

    d1 = (math.log(spot / strike) + (b + 0.5 * sigma * sigma) * T) / vol_sqrt_T
    d2 = d1 - vol_sqrt_T

    df_r = math.exp(-r * T)
    df_b = math.exp((b - r) * T)

    call_price = spot * df_b * _norm_cdf(d1) - strike * df_r * _norm_cdf(d2)
    call_price = max(call_price, spot * 0.0002)

    delta = df_b * _norm_cdf(d1)
    gamma = (df_b * _norm_pdf(d1)) / (spot * vol_sqrt_T)
    vega = spot * df_b * _norm_pdf(d1) * sqrt_T * 0.01

    term1 = -(spot * df_b * _norm_pdf(d1) * sigma) / (2.0 * sqrt_T)
    if is_futures:
        theta_annual = term1 - r * strike * df_r * _norm_cdf(d2) + r * spot * df_b * _norm_cdf(d1)
    else:
        theta_annual = term1 - r * strike * df_r * _norm_cdf(d2)
    theta_daily = abs(theta_annual / 365.0)

    prob_otm_pct = _norm_cdf(-d2) * 100.0
    return {
        "premium": call_price,
        "delta": delta,
        "gamma": gamma,
        "theta_daily": theta_daily,
        "vega": vega,
        "prob_otm_pct": prob_otm_pct,
        "prob_called_pct": 100.0 - prob_otm_pct,
    }


def build_bull_put_spread(
    inst: Dict[str, Any],
    spot: float,
    short_strike: float,
    short_prem: float,
    short_delta: float,
    atm_iv: float,
    dte: int,
    naked_margin_req: float,
    step: float,
) -> Dict[str, Any]:
    """
    Pair a Short Put (K_short) with a protective Long Put (K_long < K_short, target Delta ~ -0.06 to -0.08)
    to form a defined-risk Bull Put Credit Spread.
    """
    market = inst["market"]
    sym = inst["symbol"]
    is_futures = market in ("us_fut", "cn_fut")
    r = 0.020 if market == "cn_fut" else 0.042
    basis_drift = _CFFEX_BASIS_DRIFT.get(sym, 0.0)
    fat_tail = _FAT_TAIL_FACTOR.get(sym, 0.16 if market == "cn_fut" else 0.12)
    dp = int(inst.get("dp", 2))
    mult = float(inst.get("multiplier", 100))
    skew_coeff = float(inst.get("iv_skew", 0.12))

    # Solve protective long leg around Delta = min(0.07, abs(short_delta) * 0.32)
    target_long_delta = max(0.04, min(0.09, abs(short_delta) * 0.32))
    raw_long_k = solve_strike_for_delta(
        spot,
        target_long_delta,
        dte,
        atm_iv,
        r=r,
        is_futures=is_futures,
        basis_drift=basis_drift,
        fat_tail=fat_tail,
    )
    long_k = round_to_step(raw_long_k, step, dp=dp)
    # Ensure width is at least 2 strike steps and ~3.5% to 8% of spot
    min_width = max(step * 2.0, spot * 0.035)
    if short_strike - long_k < min_width:
        long_k = round_to_step(short_strike - min_width, step, dp=dp)
    long_k = max(step, long_k)

    long_iv = skew_adjusted_iv(atm_iv, spot, long_k, skew_coeff=skew_coeff, fat_tail=fat_tail)
    long_res = price_put_and_greeks(
        spot,
        long_k,
        dte,
        long_iv,
        r=r,
        is_futures=is_futures,
        basis_drift=basis_drift,
        fat_tail=fat_tail,
    )
    long_prem = min(long_res["premium"], short_prem * 0.65)
    net_credit = max(short_prem - long_prem, short_prem * 0.25)
    width = max(short_strike - long_k, step)
    max_loss_unit = max(width - net_credit, net_credit * 0.5)

    contract_credit = net_credit * mult
    contract_max_loss = max_loss_unit * mult
    spread_margin = contract_max_loss  # Exchange/Reg-T defined-risk credit spread margin = max loss
    margin_saved_pct = (
        max(0.0, (1.0 - spread_margin / naked_margin_req) * 100.0) if naked_margin_req > 0 else 0.0
    )
    roc_spread = (contract_credit / spread_margin * 100.0) if spread_margin > 0 else 0.0
    ann_roc_spread = roc_spread * (365.0 / max(int(dte), 1))
    credit_retention_pct = (net_credit / short_prem * 100.0) if short_prem > 0 else 100.0
    spread_be = short_strike - net_credit

    return {
        "shortStrike": round(short_strike, dp),
        "longStrike": round(long_k, dp),
        "spreadWidth": round(width, dp),
        "shortPremium": round(short_prem, max(dp, 2)),
        "longPremium": round(long_prem, max(dp, 2)),
        "netCredit": round(net_credit, max(dp, 2)),
        "contractNetCredit": round(contract_credit, 0 if contract_credit >= 100 else 2),
        "maxLoss": round(contract_max_loss, 0 if contract_max_loss >= 100 else 2),
        "spreadMarginReq": round(spread_margin, 0),
        "marginSavedPct": round(margin_saved_pct, 1),
        "creditRetentionPct": round(credit_retention_pct, 1),
        "breakeven": round(spread_be, dp),
        "rocSpreadPct": round(roc_spread, 2),
        "annReturnSpreadPct": round(ann_roc_spread, 1),
        "netDelta": round(short_delta - long_res["delta"], 3),
        "longDelta": round(long_res["delta"], 3),
        "longIvPct": round(long_iv * 100.0, 1),
    }


def build_wheel_covered_call(
    inst: Dict[str, Any],
    spot: float,
    assigned_strike: float,
    put_premium: float,
    atm_iv: float,
    dte: int,
    step: float,
) -> Dict[str, Any]:
    """
    Calculate Phase 2 of 'The Wheel Strategy' (车轮策略接货后备兑看涨期权 Covered Call):
    Assuming assignment at `assigned_strike` (effective cost basis = assigned_strike - put_premium),
    recommend selling an OTM Call at >= assigned_strike (~0.25-0.30 Call Delta) for 30 DTE.
    """
    market = inst["market"]
    sym = inst["symbol"]
    is_futures = market in ("us_fut", "cn_fut")
    r = 0.020 if market == "cn_fut" else 0.042
    basis_drift = _CFFEX_BASIS_DRIFT.get(sym, 0.0)
    dp = int(inst.get("dp", 2))
    mult = float(inst.get("multiplier", 100))

    cost_basis = max(assigned_strike - put_premium, assigned_strike * 0.7)
    # If assigned, spot is around assigned_strike; target call strike is at least assigned_strike (no locked-in loss)
    ref_spot = min(spot, assigned_strike)
    call_dte = max(int(dte), 30)
    raw_call_k = max(assigned_strike, round_to_step(ref_spot * (1.0 + 0.35 * atm_iv * math.sqrt(call_dte / 365.0)), step, dp=dp))
    if raw_call_k <= ref_spot:
        raw_call_k = round_to_step(ref_spot + step, step, dp=dp)

    call_iv = max(0.06, atm_iv * 0.96)  # OTM call typically trades slightly below ATM vol on equities
    call_res = price_call_and_greeks(
        ref_spot,
        raw_call_k,
        call_dte,
        call_iv,
        r=r,
        is_futures=is_futures,
        basis_drift=basis_drift,
    )
    call_prem = call_res["premium"]
    contract_call_prem = call_prem * mult
    new_cost_basis = max(cost_basis - call_prem, cost_basis * 0.5)
    call_ann_yield = (call_prem / assigned_strike) * (365.0 / call_dte) * 100.0 if assigned_strike > 0 else 0.0
    total_wheel_prem = put_premium + call_prem
    wheel_ann_yield = (total_wheel_prem / assigned_strike) * (365.0 / (call_dte * 2.0)) * 100.0 if assigned_strike > 0 else 0.0
    upside_if_called_pct = ((raw_call_k - cost_basis + call_prem) / cost_basis * 100.0) if cost_basis > 0 else 0.0

    return {
        "assignedStrike": round(assigned_strike, dp),
        "initialCostBasis": round(cost_basis, dp),
        "callStrike": round(raw_call_k, dp),
        "callDte": call_dte,
        "callDelta": round(call_res["delta"], 2),
        "callPremium": round(call_prem, max(dp, 2)),
        "contractCallPremium": round(contract_call_prem, 0 if contract_call_prem >= 100 else 2),
        "newCostBasis": round(new_cost_basis, dp),
        "costReductionPct": round(((assigned_strike - new_cost_basis) / assigned_strike) * 100.0, 2) if assigned_strike > 0 else 0.0,
        "callAnnReturnPct": round(call_ann_yield, 1),
        "wheelCycleAnnPct": round(wheel_ann_yield, 1),
        "upsideIfCalledPct": round(upside_if_called_pct, 2),
        "probCalledPct": round(call_res["prob_called_pct"], 1),
    }


def compute_vol_skew_and_term(
    inst: Dict[str, Any],
    spot: float,
    atm_iv: float,
    hv20: float,
    hv60: float,
    hv_med_1y: float,
    dte: int = 30,
    earnings_in_window: bool = False,
) -> Dict[str, Any]:
    """
    Compute 25-Delta Put Skew (Put Smirk), 25-Delta Risk Reversal, and 7D / 30D / 60D IV Term Structure.
    """
    market = inst["market"]
    sym = inst["symbol"]
    is_futures = market in ("us_fut", "cn_fut")
    r = 0.020 if market == "cn_fut" else 0.042
    basis_drift = _CFFEX_BASIS_DRIFT.get(sym, 0.0)
    fat_tail = _FAT_TAIL_FACTOR.get(sym, 0.16 if market == "cn_fut" else 0.12)
    skew_coeff = float(inst.get("iv_skew", 0.12))

    k_25p = solve_strike_for_delta(spot, 0.25, dte, atm_iv, r=r, is_futures=is_futures, basis_drift=basis_drift, fat_tail=fat_tail)
    iv_25p = skew_adjusted_iv(atm_iv, spot, k_25p, skew_coeff=skew_coeff, fat_tail=fat_tail)
    # 25-Delta OTM Call IV (equities/indices exhibit downside put skew; gold/commodities can have mild call skew)
    is_upside_skew_asset = inst.get("sector") in ("贵金属", "有色金属", "新能源") or sym in ("GLD", "GC=F", "SI=F", "AU0", "AG0", "IBIT")
    iv_25c = atm_iv * (1.015 if is_upside_skew_asset else max(0.88, 1.0 - skew_coeff * 0.42))

    atm_iv_pct = round(atm_iv * 100.0, 1)
    put_25d_pct = round(iv_25p * 100.0, 1)
    call_25d_pct = round(iv_25c * 100.0, 1)
    skew_25d_pts = round(put_25d_pct - atm_iv_pct, 1)
    rr_25d_pts = round(put_25d_pct - call_25d_pct, 1)

    if skew_25d_pts >= 3.2:
        skew_label = "陡峭恐慌偏度 (尾部Put溢价极肥·宜卖虚值Put或牛市价差)"
        skew_tone = "bull"
    elif skew_25d_pts >= 1.5:
        skew_label = "标准左偏微笑 (机构常态虚值保护溢价)"
        skew_tone = "gold"
    else:
        skew_label = "偏度温和/平坦 (虚值与平值隐波接近)"
        skew_tone = "neutral"

    # Term structure across 7D, 30D, 60D, 90D
    anchor_long = max(0.08, 0.55 * atm_iv + 0.45 * max(hv60, hv_med_1y) * 1.12)
    if earnings_in_window or hv20 > atm_iv * 1.08:
        iv_7d = atm_iv * (1.12 if earnings_in_window else 1.05)
        iv_14d = atm_iv * (1.06 if earnings_in_window else 1.02)
    else:
        iv_7d = max(0.06, 0.65 * atm_iv + 0.35 * hv20)
        iv_14d = max(0.06, 0.82 * atm_iv + 0.18 * hv20)
    iv_30d = atm_iv
    iv_60d = 0.65 * atm_iv + 0.35 * anchor_long
    iv_90d = 0.45 * atm_iv + 0.55 * anchor_long

    iv_7d_pct = round(iv_7d * 100.0, 1)
    iv_14d_pct = round(iv_14d * 100.0, 1)
    iv_30d_pct = round(iv_30d * 100.0, 1)
    iv_60d_pct = round(iv_60d * 100.0, 1)
    iv_90d_pct = round(iv_90d * 100.0, 1)
    term_slope_pts = round(iv_60d_pct - iv_7d_pct, 1)

    if term_slope_pts <= -1.5:
        term_label = "⚠️ 近高远低倒挂 (Backwardation · 短期事件/跳空风险高)"
        term_tone = "bear"
    elif term_slope_pts >= 1.0:
        term_label = "🟢 远月正常升水 (Contango · 30~45天Theta衰减甜点)"
        term_tone = "bull"
    else:
        term_label = "🟡 期限结构平坦 (近远月隐波持平)"
        term_tone = "gold"

    return {
        "atmIvPct": atm_iv_pct,
        "put25dIvPct": put_25d_pct,
        "call25dIvPct": call_25d_pct,
        "skew25dPts": skew_25d_pts,
        "riskReversal25dPts": rr_25d_pts,
        "skewLabel": skew_label,
        "skewTone": skew_tone,
        "iv7dPct": iv_7d_pct,
        "iv14dPct": iv_14d_pct,
        "iv30dPct": iv_30d_pct,
        "iv60dPct": iv_60d_pct,
        "iv90dPct": iv_90d_pct,
        "termSlopePts": term_slope_pts,
        "termLabel": term_label,
        "termTone": term_tone,
    }


def solve_roll_down_and_out(
    inst: Dict[str, Any],
    spot: float,
    current_strike: float,
    current_put_price: float,
    atm_iv: float,
    rem_dte: int,
    add_days: int = 30,
) -> Dict[str, Any]:
    """
    Defensive Roll Down & Out calculator:
    Given a tested Short Put at `current_strike` (buy-to-close cost = `current_put_price`),
    search for a lower strike `new_strike < current_strike` at `new_dte = max(rem_dte, 5) + add_days`
    that achieves a Net Credit (or minimal debit) while lowering the strike & breakeven.
    """
    market = inst["market"]
    sym = inst["symbol"]
    is_futures = market in ("us_fut", "cn_fut")
    r = 0.020 if market == "cn_fut" else 0.042
    basis_drift = _CFFEX_BASIS_DRIFT.get(sym, 0.0)
    fat_tail = _FAT_TAIL_FACTOR.get(sym, 0.16 if market == "cn_fut" else 0.12)
    dp = int(inst.get("dp", 2))
    mult = float(inst.get("multiplier", 100))
    skew_coeff = float(inst.get("iv_skew", 0.12))
    step = dynamic_strike_step(spot, float(inst.get("strike_step", 1.0)), dp=dp)

    new_dte = max(int(rem_dte), 3) + int(add_days)
    best_plan: Optional[Dict[str, Any]] = None

    # Candidate strikes from 1 step to 6 steps below current_strike
    for n_steps in range(1, 7):
        cand_k = round_to_step(current_strike - n_steps * step, step, dp=dp)
        if cand_k <= spot * 0.65:
            break
        cand_iv = skew_adjusted_iv(atm_iv, spot, cand_k, skew_coeff=skew_coeff, fat_tail=fat_tail)
        res = price_put_and_greeks(
            spot,
            cand_k,
            new_dte,
            cand_iv,
            r=r,
            is_futures=is_futures,
            basis_drift=basis_drift,
            fat_tail=fat_tail,
        )
        new_prem = res["premium"]
        net_roll_credit = new_prem - current_put_price
        plan = {
            "newStrike": round(cand_k, dp),
            "strikeDropPct": round(((current_strike - cand_k) / current_strike) * 100.0, 2) if current_strike > 0 else 0.0,
            "newDte": new_dte,
            "closeCost": round(current_put_price, max(dp, 2)),
            "newPremium": round(new_prem, max(dp, 2)),
            "netRollCredit": round(net_roll_credit, max(dp, 2)),
            "contractNetRollCredit": round(net_roll_credit * mult, 1),
            "isNetCredit": net_roll_credit >= 0.0,
            "newDelta": round(res["delta"], 3),
            "newBreakeven": round(cand_k - max(0.0, new_prem - current_put_price), dp),
            "newOtmPct": round(((spot - cand_k) / spot) * 100.0, 2) if spot > 0 else 0.0,
        }
        if net_roll_credit >= 0.0:
            best_plan = plan
        elif best_plan is None:
            best_plan = plan

    return best_plan or {
        "newStrike": round(current_strike - step, dp),
        "strikeDropPct": 1.5,
        "newDte": new_dte,
        "closeCost": round(current_put_price, max(dp, 2)),
        "newPremium": round(current_put_price, max(dp, 2)),
        "netRollCredit": 0.0,
        "contractNetRollCredit": 0.0,
        "isNetCredit": True,
        "newDelta": -0.25,
        "newBreakeven": round(current_strike - step, dp),
        "newOtmPct": 3.0,
    }


def solve_strike_for_delta(
    spot: float,
    target_abs_delta: float,
    dte: int,
    atm_iv: float,
    r: float = 0.04,
    is_futures: bool = False,
    basis_drift: float = 0.0,
    fat_tail: float = 0.12,
) -> float:
    """
    Analytical inverse-Delta strike solver for OTM Put with a heuristic fat-tail buffer.
    Assets with high left-tail kurtosis automatically require deeper OTM strikes for the same target risk.
    """
    T = max(int(dte), 1) / 365.0
    # Effective vol for strike solving incorporates fat-tail cushion for deep OTM tiers
    tail_mult = 1.0 + fat_tail * max(0.0, (0.38 - target_abs_delta)) * 0.65
    sigma = max(float(atm_iv) * tail_mult, 0.05)
    sqrt_T = math.sqrt(T)
    b = basis_drift if is_futures else r
    df_b = math.exp((b - r) * T)

    # |Delta_P| = df_b * N(-d1) => -d1 = N^{-1}(|Delta_P| / df_b)
    p = min(0.49, max(0.03, target_abs_delta / max(df_b, 0.8)))
    d1 = -_norm_ppf(p)
    # d1 = [ln(S/K) + (b + 0.5*sigma^2)*T] / (sigma*sqrt_T)
    ln_s_over_k = d1 * sigma * sqrt_T - (b + 0.5 * sigma * sigma) * T
    raw_k = spot * math.exp(-ln_s_over_k)
    return min(raw_k, spot * 0.99)


def compute_empirical_put_stats(
    closes: Optional[List[float]],
    spot: float,
    strike: float,
    breakeven: float,
    dte: int,
    fallback_pop: float = 80.0,
    fallback_otm: float = 75.0,
) -> Dict[str, float]:
    """
    Compute 5-year historical rolling window empirical probability of profit (S_T >= breakeven)
    and probability of expiring unassigned (S_T >= strike) over N_td trading days.
    """
    n_td = max(4, round(int(dte) * 252.0 / 365.0))
    if not closes or len(closes) < n_td + 30 or spot <= 0:
        return {
            "empiricalPopPct": round(fallback_pop, 1),
            "empiricalOtmPct": round(fallback_otm, 1),
        }

    req_be_ratio = breakeven / spot
    req_k_ratio = strike / spot
    total_w = 0
    win_be = 0
    win_otm = 0

    # Step by 2 trading days across up to 5 years (~1260 bars) for fast, unbiased rolling distribution
    limit = len(closes) - n_td
    for i in range(0, limit, 2):
        c0 = closes[i]
        c1 = closes[i + n_td]
        if c0 <= 0 or c1 <= 0:
            continue
        ratio = c1 / c0
        # Filter extreme continuous futures roll splice (>45% jump)
        if ratio > 1.65 or ratio < 0.45:
            continue
        total_w += 1
        if ratio >= req_be_ratio:
            win_be += 1
        if ratio >= req_k_ratio:
            win_otm += 1

    if total_w < 20:
        return {
            "empiricalPopPct": round(fallback_pop, 1),
            "empiricalOtmPct": round(fallback_otm, 1),
        }

    return {
        "empiricalPopPct": round((win_be / total_w) * 100.0, 1),
        "empiricalOtmPct": round((win_otm / total_w) * 100.0, 1),
    }


def build_put_tiers(
    inst: Dict[str, Any],
    spot: float,
    atm_iv: float,
    dte: int = 30,
    supports: Optional[Dict[str, Optional[float]]] = None,
    atr_pct: float = 1.8,
    hv20: float = 0.22,
    closes: Optional[List[float]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Generate 3 actionable Short Put strike tiers:
    - conservative: Delta ~ -0.15 (深虚值高胜率安全垫档)
    - balanced:     Delta ~ -0.25 (标准甜点收租档 - 默认推荐)
    - aggressive:   Delta ~ -0.35 (浅虚值高权利金接货档)
    """
    market = inst["market"]
    sym = inst["symbol"]
    is_futures = market in ("us_fut", "cn_fut")
    r = 0.020 if market == "cn_fut" else 0.042
    basis_drift = _CFFEX_BASIS_DRIFT.get(sym, 0.0)
    fat_tail = _FAT_TAIL_FACTOR.get(sym, 0.16 if market == "cn_fut" else 0.12)

    dp = int(inst.get("dp", 2))
    mult = float(inst.get("multiplier", 100))
    margin_rate = float(inst.get("margin_rate", 0.15))
    skew_coeff = float(inst.get("iv_skew", 0.12))
    step = dynamic_strike_step(spot, float(inst.get("strike_step", 1.0)), dp=dp)

    # Solve from closest-to-ATM (aggressive) down to deepest-OTM (conservative)
    # so K_aggressive > K_balanced > K_conservative is strictly guaranteed.
    solve_order = [
        ("aggressive", "进取接货档", 0.35, "以接货建仓之心卖Put · 权利金极厚"),
        ("balanced", "平衡甜点档", 0.24, "机构主力档 · 胜率与Theta性价比最优"),
        ("conservative", "保守高胜率档", 0.14, "深虚值收租 · 极高胜率防穿仓"),
    ]

    solved_map: Dict[str, Any] = {}
    prev_k: Optional[float] = None

    for key, label, target_d, desc in solve_order:
        raw_k = solve_strike_for_delta(
            spot,
            target_d,
            dte,
            atm_iv,
            r=r,
            is_futures=is_futures,
            basis_drift=basis_drift,
            fat_tail=fat_tail,
        )
        k = round_to_step(raw_k, step, dp=dp)
        if k >= spot:
            k = round_to_step(spot - step, step, dp=dp)
        if prev_k is not None and k >= prev_k:
            k = round_to_step(prev_k - step, step, dp=dp)
        prev_k = k
        solved_map[key] = (key, label, target_d, desc, k)

    out: Dict[str, Dict[str, Any]] = {}
    eff_atr_pct = max(float(atr_pct or 1.5), 0.35)
    eff_hv_pct = max(float(hv20 or 0.20) * 100.0, 6.0)

    for key in ("conservative", "balanced", "aggressive"):
        _, label, target_d, desc, k = solved_map[key]

        strike_iv = skew_adjusted_iv(atm_iv, spot, k, skew_coeff=skew_coeff, fat_tail=fat_tail)
        res = price_put_and_greeks(
            spot,
            k,
            dte,
            strike_iv,
            r=r,
            is_futures=is_futures,
            basis_drift=basis_drift,
            fat_tail=fat_tail,
        )

        prem = res["premium"]
        be = res["breakeven"]
        otm_amt = max(0.0, spot - k)
        otm_pct = (otm_amt / spot) * 100.0 if spot > 0 else 0.0
        be_buffer_pct = ((spot - be) / spot) * 100.0 if spot > 0 else 0.0

        # Risk-adjusted metrics:
        # 1) How many daily ATRs must spot fall to breach breakeven?
        atr_buffer_mult = be_buffer_pct / eff_atr_pct
        # 2) Theta / Vega efficiency
        theta_vega_ratio = res["theta_daily"] / max(res["vega"], 0.001)

        contract_notional = spot * mult
        strike_notional = k * mult
        contract_prem = prem * mult
        contract_theta = res["theta_daily"] * mult

        # Practical broker naked put margin formula (approx 1.25x exchange base + 70% OTM floor):
        eff_margin_rate = margin_rate * 1.25
        unit_margin = prem + max(eff_margin_rate * spot - 0.5 * otm_amt, 0.70 * eff_margin_rate * spot)
        margin_req = max(unit_margin * mult, strike_notional * 0.08)

        roc_margin = (contract_prem / margin_req) * 100.0 if margin_req > 0 else 0.0
        ann_margin = roc_margin * (365.0 / max(int(dte), 1))
        roc_cash = (prem / k) * 100.0 if k > 0 else 0.0
        ann_cash = roc_cash * (365.0 / max(int(dte), 1))

        # 3) Return-to-Volatility Ratio (unlevered annualized cash yield / HV20%)
        ret_to_vol_ratio = ann_cash / eff_hv_pct

        # Check relationship with cost floor / technical support
        cost_obj = inst.get("cost") or {}
        cash_cost = cost_obj.get("cash_cost")
        primary_cost = cost_obj.get("primary_cost")
        anchor_tags: List[str] = []
        if cash_cost and k <= cash_cost * 1.01:
            anchor_tags.append(f"低于现金成本({cash_cost:g})")
        elif primary_cost and k <= primary_cost * 1.02:
            anchor_tags.append(f"贴近/低于完全成本({primary_cost:g})")
        if supports:
            boll_low = supports.get("bollLow")
            s2 = supports.get("s2")
            if boll_low and k <= boll_low * 1.005:
                anchor_tags.append("破布林下轨保护")
            elif s2 and k <= s2 * 1.005:
                anchor_tags.append("S2强支撑下方")
        if atr_buffer_mult >= 5.5:
            anchor_tags.append(f"{atr_buffer_mult:.1f}倍ATR安全垫")

        bsm_pop = round(res["pop_pct"], 1)
        bsm_otm = round(res["prob_otm_pct"], 1)
        emp = compute_empirical_put_stats(
            closes=closes,
            spot=spot,
            strike=k,
            breakeven=be,
            dte=dte,
            fallback_pop=bsm_pop,
            fallback_otm=bsm_otm,
        )
        emp_pop = emp["empiricalPopPct"]
        emp_otm = emp["empiricalOtmPct"]
        # Dual-track conservative envelope: min(BSM, 5Y Empirical) prevents both Gaussian thin-tail optimism
        # and 5-year bull-market survivorship bias!
        effective_pop = round(min(bsm_pop, emp_pop), 1)

        spread_obj = build_bull_put_spread(
            inst=inst,
            spot=spot,
            short_strike=k,
            short_prem=prem,
            short_delta=res["delta"],
            atm_iv=atm_iv,
            dte=dte,
            naked_margin_req=margin_req,
            step=step,
        )
        wheel_obj = build_wheel_covered_call(
            inst=inst,
            spot=spot,
            assigned_strike=k,
            put_premium=prem,
            atm_iv=atm_iv,
            dte=dte,
            step=step,
        )

        out[key] = {
            "tier": key,
            "label": label,
            "desc": desc,
            "strike": round(k, dp),
            "otmPct": round(otm_pct, 2),
            "ivPct": round(strike_iv * 100.0, 1),
            "premium": round(prem, max(dp, 2)),
            "contractPremium": round(contract_prem, 0 if contract_prem >= 100 else 2),
            "breakeven": round(be, dp),
            "breakevenBufferPct": round(be_buffer_pct, 2),
            "atrBufferMultiple": round(atr_buffer_mult, 1),
            "returnToVolRatio": round(ret_to_vol_ratio, 2),
            "thetaVegaRatio": round(theta_vega_ratio, 2),
            "delta": round(res["delta"], 3),
            "gamma": round(res["gamma"], 5),
            "thetaDaily": round(res["theta_daily"], max(dp, 3)),
            "contractThetaDaily": round(contract_theta, 1),
            "vega": round(res["vega"], 3),
            "popPct": effective_pop,
            "bsmPopPct": bsm_pop,
            "empiricalPopPct": emp_pop,
            "probOtmPct": round(min(bsm_otm, emp_otm), 1),
            "probTouchPct": round(res["prob_touch_pct"], 1),
            "marginReq": round(margin_req, 0),
            "cashSecuredReq": round(strike_notional, 0),
            "contractNotional": round(contract_notional, 0),
            "rocMarginPct": round(roc_margin, 2),
            "annReturnMarginPct": round(ann_margin, 1),
            "rocCashPct": round(roc_cash, 2),
            "annReturnCashPct": round(ann_cash, 1),
            "anchorTags": anchor_tags,
            "bullPutSpread": spread_obj,
            "wheelCoveredCall": wheel_obj,
        }

    return out


def build_payoff_curve(
    inst: Dict[str, Any],
    spot: float,
    strike: float,
    dte: int,
    iv: float,
    premium: float,
) -> Dict[str, Any]:
    """
    Build expiration PnL, T/2 mid-term theoretical PnL, and paired Bull Put Credit Spread PnL curve
    for 1 contract.
    """
    market = inst["market"]
    sym = inst["symbol"]
    is_futures = market in ("us_fut", "cn_fut")
    r = 0.020 if market == "cn_fut" else 0.042
    basis_drift = _CFFEX_BASIS_DRIFT.get(sym, 0.0)
    fat_tail = _FAT_TAIL_FACTOR.get(sym, 0.16 if market == "cn_fut" else 0.12)
    dp = int(inst.get("dp", 2))
    mult = float(inst.get("multiplier", 100))
    step = dynamic_strike_step(spot, float(inst.get("strike_step", 1.0)), dp=dp)
    margin_rate = float(inst.get("margin_rate", 0.15))
    otm_amt = max(0.0, spot - strike)
    eff_margin_rate = margin_rate * 1.25
    unit_margin = premium + max(eff_margin_rate * spot - 0.5 * otm_amt, 0.70 * eff_margin_rate * spot)
    naked_margin = max(unit_margin * mult, strike * mult * 0.08)

    spread_info = build_bull_put_spread(
        inst=inst,
        spot=spot,
        short_strike=strike,
        short_prem=premium,
        short_delta=-0.24,
        atm_iv=iv,
        dte=dte,
        naked_margin_req=naked_margin,
        step=step,
    )
    long_k = float(spread_info["longStrike"])
    net_credit = float(spread_info["netCredit"])

    low_p = min(spot * 0.78, strike * 0.86, long_k * 0.94)
    high_p = max(spot * 1.12, strike * 1.16)
    n_pts = 65
    step_p = (high_p - low_p) / (n_pts - 1)
    mid_dte = max(1, int(dte // 2))

    prices: List[float] = []
    exp_pnl: List[float] = []
    mid_pnl: List[float] = []
    spread_exp_pnl: List[float] = []

    for i in range(n_pts):
        p = low_p + i * step_p
        prices.append(round(p, dp))
        # At expiration: Short Put PnL = (Premium - max(Strike - S_T, 0)) * multiplier
        intrinsic = max(0.0, strike - p)
        e_val = (premium - intrinsic) * mult
        exp_pnl.append(round(e_val, 1))

        # Bull Put Spread at expiration: (net_credit - max(K_short - S_T, 0) + max(K_long - S_T, 0)) * multiplier
        long_intrinsic = max(0.0, long_k - p)
        sp_val = (net_credit - intrinsic + long_intrinsic) * mult
        spread_exp_pnl.append(round(sp_val, 1))

        # At T/2: Short Put PnL = (Premium - Put_BSM(p, K, dte/2, iv)) * multiplier
        mid_res = price_put_and_greeks(
            p,
            strike,
            mid_dte,
            iv,
            r=r,
            is_futures=is_futures,
            basis_drift=basis_drift,
            fat_tail=fat_tail,
        )
        m_val = (premium - mid_res["premium"]) * mult
        mid_pnl.append(round(m_val, 1))

    return {
        "prices": prices,
        "expPnl": exp_pnl,
        "midPnl": mid_pnl,
        "spreadExpPnl": spread_exp_pnl,
        "spreadInfo": spread_info,
        "maxProfit": round(premium * mult, 1),
        "breakeven": round(strike - premium, dp),
        "midDte": mid_dte,
    }
