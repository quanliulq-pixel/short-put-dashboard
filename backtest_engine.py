# -*- coding: utf-8 -*-
"""
Historical Recommendation Tracker, Rolling Cohort Backtest & Stress Testing Engine
(卖Put历史推荐回顾、逐周实证校准与组合压力测试引擎)

Key Capabilities:
1. Multi-Cohort Backtest & Realized Outcome Evaluation (12, 26, 52, 104 weeks):
   - Unassigned (未行权·全额收租: Spot_end >= Strike)
   - Assigned with Profit (被行权·仍盈利: Breakeven <= Spot_end < Strike)
   - Mild Loss (被行权·小幅浮亏: Spot_end < Breakeven, loss <= 2x premium)
   - Heavy Loss (大幅亏损: loss > 2x premium OR breach > 3%)
2. Score Bucket Monotonicity Calibration (各分数段实证胜率与大亏率单调性检验: 90+, 80-90, 70-80, 60-70, <60)
3. Trend Regime & Circuit Breaker Efficacy Check (熔断与限分有效性实证检验)
4. Hard Stop-Loss Discipline vs Hold-to-Expiration Comparison (硬止损 -2.5R 对比)
5. Multi-Market Real Exchange Margin Calculation:
   - US Stocks & ETFs: Reg-T Margin = 100 * [Premium + max(20%*S - OTM, 10%*K)]
   - CFFEX Index Options: Multiplier * [Premium + max(12%*S - OTM, 6%*S)]
   - China Commodity Futures Options: Multiplier * [Premium + max(Rate*S - 0.5*OTM, 0.5*Rate*S)]
   - US Futures Options: Multiplier * [Premium + max(Rate*S - 0.5*OTM, 0.5*Rate*S)]
6. Institutional Portfolio Stress Testing under 4 Extreme Scenarios (Normal, -1σ, -2σ, -3σ Market Crash)
"""
from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Dict, List, Optional

from data_engine import ensure_all_bars_loaded, get_instrument_bars, get_macro_vol_regime
from http_utils import DATA_DIR, cached, now_bj
from options_math import price_put_and_greeks
from recommender import (
    _select_diversified_top,
    analyze_single_instrument,
    get_weekly_recommendations,
)
from universe import ALL_INSTRUMENTS, get_instrument

logger = logging.getLogger(__name__)

LEDGER_FILE = os.path.join(DATA_DIR, "weekly_ledger_v1.json")


def compute_exchange_margin(
    inst: Dict[str, Any], spot: float, strike: float, premium: float
) -> float:
    """
    Accurate multi-market exchange margin requirement for short puts:
    - US Stocks/ETFs (Reg-T): 100 * [Premium + max(20% * S - OTM, 10% * K)]
    - CFFEX Index Options (MO/IO/HO): Multiplier * [Premium + max(12% * S - OTM, 6% * S)]
    - China Commodity Futures Options: Multiplier * [Premium + max(Rate * S - 0.5 * OTM, 0.5 * Rate * S)]
    - US Futures Options: Multiplier * [Premium + max(Rate * S - 0.5 * OTM, 0.5 * Rate * S)]
    """
    mult = float(inst.get("multiplier", 100))
    otm = max(0.0, spot - strike)
    mkt = inst.get("market")
    sec = inst.get("sector")

    if mkt == "us_stk":
        base_margin = 100.0 * (premium + max(0.20 * spot - otm, 0.10 * strike))
        return round(max(base_margin, 100.0 * premium), 2)
    elif sec == "股指期权" or inst.get("id") in ("CN_FUT:IM0", "CN_FUT:IF0", "CN_FUT:IH0"):
        base_margin = mult * (premium + max(0.12 * spot - otm, 0.06 * spot))
        return round(max(base_margin, mult * premium), 2)
    elif mkt == "us_fut":
        rate = float(inst.get("margin_rate") or 0.12)
        base_margin = mult * (premium + max(rate * spot - 0.5 * otm, 0.5 * rate * spot))
        return round(max(base_margin, mult * premium), 2)
    else:
        rate = float(inst.get("margin_rate") or 0.10)
        base_margin = mult * (premium + max(rate * spot - 0.5 * otm, 0.5 * rate * spot))
        return round(max(base_margin, mult * premium), 2)


def _evaluate_put_outcome(
    inst: Dict[str, Any],
    entry_spot: float,
    tier_obj: Dict[str, Any],
    future_bars: List[Dict[str, Any]],
    is_expired: bool,
) -> Dict[str, Any]:
    """
    Evaluate what happened to a Short Put position given subsequent daily bars:
    1. Baseline Hold-to-Expiration outcome
    2. Hard Stop-Loss discipline outcome (stopped at -2.5R if loss reaches 2.5x premium)
    """
    dp = int(inst.get("dp", 2))
    mult = float(inst.get("multiplier", 100))
    strike = float(tier_obj["strike"])
    prem = float(tier_obj["premium"])
    be = float(tier_obj["breakeven"])
    contract_prem = float(tier_obj["contractPremium"])
    margin_req = compute_exchange_margin(inst, entry_spot, strike, prem)

    if not future_bars:
        end_price = entry_spot
        min_low = entry_spot
        min_date = "--"
    else:
        end_price = float(future_bars[-1]["c"])
        min_bar = min(future_bars, key=lambda b: float(b.get("l", b["c"])))
        min_low = float(min_bar.get("l", min_bar["c"]))
        min_date = min_bar.get("t", min_bar.get("date", "--"))

    underlying_ret_pct = ((end_price - entry_spot) / entry_spot * 100.0) if entry_spot > 0 else 0.0
    max_dd_pct = ((min_low - entry_spot) / entry_spot * 100.0) if entry_spot > 0 else 0.0

    # 1. Baseline Expiration Outcome
    intrinsic_end = max(0.0, strike - end_price)
    net_unit_pnl = prem - intrinsic_end
    net_contract_pnl = net_unit_pnl * mult

    r_multiple = (net_unit_pnl / prem) if prem > 0 else 0.0
    roc_margin_net_pct = (net_contract_pnl / margin_req * 100.0) if margin_req > 0 else 0.0

    touched_strike = min_low < strike
    is_assigned = end_price < strike
    below_be_pct = ((be - end_price) / entry_spot * 100.0) if (end_price < be and entry_spot > 0) else 0.0

    if not is_assigned:
        status_code = "SAFE"
        status_label = "未行权·全额收租" if is_expired else "安全持有·未破行权价"
        status_tone = "bull"
        is_heavy_loss = False
        is_win = True
    elif end_price >= be:
        status_code = "ASSIGNED_PROFIT"
        status_label = "被行权·权利金覆盖仍盈利"
        status_tone = "cyan"
        is_heavy_loss = False
        is_win = True
    else:
        is_win = False
        if r_multiple <= -2.0 or below_be_pct >= 3.0:
            status_code = "HEAVY_LOSS"
            status_label = "大幅亏损·击穿保护垫"
            status_tone = "bear"
            is_heavy_loss = True
        else:
            status_code = "ASSIGNED_MILD_LOSS"
            status_label = "被行权·小幅浮亏接货"
            status_tone = "gold"
            is_heavy_loss = False

    # 2. Hard Stop-Loss Simulation:
    # If intra-period price falls so low that intrinsic loss exceeds 3.5x premium (net loss <= -2.5R)
    # or drops > 3.5% below breakeven, close position immediately at -2.50R cap.
    stop_triggered = False
    stop_date = "--"
    r_stop = r_multiple
    net_contract_pnl_stop = net_contract_pnl

    for b in future_bars:
        low_b = float(b.get("l", b["c"]))
        intrinsic_b = max(0.0, strike - low_b)
        if (prem > 0 and intrinsic_b >= 3.5 * prem) or (entry_spot > 0 and (be - low_b) / entry_spot >= 0.035):
            stop_triggered = True
            stop_date = b.get("t", b.get("date", "--"))
            r_stop = -2.50
            net_contract_pnl_stop = -2.50 * prem * mult
            break

    is_win_stop = r_stop >= 0.0
    is_heavy_stop = r_stop <= -2.0

    return {
        "strike": round(strike, dp),
        "otmPct": tier_obj["otmPct"],
        "premium": round(prem, max(dp, 2)),
        "contractPremium": round(contract_prem, 0 if contract_prem >= 100 else 2),
        "breakeven": round(be, dp),
        "marginReq": round(margin_req, 0 if margin_req >= 100 else 2),
        "endPrice": round(end_price, dp),
        "minLow": round(min_low, dp),
        "minDate": min_date,
        "underlyingRetPct": round(underlying_ret_pct, 2),
        "maxDrawdownPct": round(max_dd_pct, 2),
        "touchedStrike": touched_strike,
        "isAssigned": is_assigned,
        "isHeavyLoss": is_heavy_loss,
        "isWin": is_win,
        "statusCode": status_code,
        "statusLabel": status_label,
        "statusTone": status_tone,
        "netContractPnl": round(net_contract_pnl, 0 if abs(net_contract_pnl) >= 100 else 1),
        "rMultiple": round(r_multiple, 2),
        "rocMarginNetPct": round(roc_margin_net_pct, 2),
        "belowBePct": round(below_be_pct, 2),
        # Hard stop fields
        "stopTriggered": stop_triggered,
        "stopDate": stop_date,
        "rStop": round(r_stop, 2),
        "netContractPnlStop": round(net_contract_pnl_stop, 0 if abs(net_contract_pnl_stop) >= 100 else 1),
        "isWinStop": is_win_stop,
        "isHeavyStop": is_heavy_stop,
    }


def _aggregate_stats(records: List[Dict[str, Any]], tier_key: str) -> Dict[str, Any]:
    total = len(records)
    if total == 0:
        return {
            "total": 0,
            "expiredCount": 0,
            "activeCount": 0,
            "unassignedCount": 0,
            "unassignedPct": 0.0,
            "assignedCount": 0,
            "assignedPct": 0.0,
            "assignedProfitCount": 0,
            "mildLossCount": 0,
            "heavyLossCount": 0,
            "heavyLossPct": 0.0,
            "winCount": 0,
            "winRatePct": 0.0,
            "touchedCount": 0,
            "touchedPct": 0.0,
            "avgRMultiple": 0.0,
            "avgRocMarginNetPct": 0.0,
            "stopTriggerCount": 0,
            "stopTriggerPct": 0.0,
            "winRateStopPct": 0.0,
            "avgRMultipleStop": 0.0,
            "byMarket": {},
        }

    unassigned = 0
    assigned = 0
    assigned_profit = 0
    mild_loss = 0
    heavy_loss = 0
    wins = 0
    touched = 0
    expired_cnt = 0
    active_cnt = 0
    r_sum = 0.0
    roc_sum = 0.0

    stop_triggers = 0
    stop_wins = 0
    stop_r_sum = 0.0

    by_mkt: Dict[str, Dict[str, Any]] = {
        "cn_idx": {"label": "A股三大股指(MO/IO/HO)", "total": 0, "unassigned": 0, "assigned": 0, "heavyLoss": 0, "win": 0, "avgR": 0.0},
        "us_stk": {"label": "美股与ETF", "total": 0, "unassigned": 0, "assigned": 0, "heavyLoss": 0, "win": 0, "avgR": 0.0},
        "us_fut": {"label": "美国期货", "total": 0, "unassigned": 0, "assigned": 0, "heavyLoss": 0, "win": 0, "avgR": 0.0},
        "cn_fut": {"label": "中国商品期货", "total": 0, "unassigned": 0, "assigned": 0, "heavyLoss": 0, "win": 0, "avgR": 0.0},
    }

    for rec in records:
        ev = rec["outcomes"].get(tier_key) or rec["outcomes"]["balanced"]
        if rec["isExpired"]:
            expired_cnt += 1
        else:
            active_cnt += 1

        if not ev["isAssigned"]:
            unassigned += 1
        else:
            assigned += 1
            if ev["statusCode"] == "ASSIGNED_PROFIT":
                assigned_profit += 1
            elif ev["statusCode"] == "ASSIGNED_MILD_LOSS":
                mild_loss += 1

        if ev["isHeavyLoss"]:
            heavy_loss += 1
        if ev["isWin"]:
            wins += 1
        if ev["touchedStrike"]:
            touched += 1

        r_sum += ev["rMultiple"]
        roc_sum += ev["rocMarginNetPct"]

        if ev.get("stopTriggered"):
            stop_triggers += 1
        if ev.get("isWinStop"):
            stop_wins += 1
        stop_r_sum += ev.get("rStop", ev["rMultiple"])

        m_key = "cn_idx" if rec["id"] in ("CN_FUT:IM0", "CN_FUT:IF0", "CN_FUT:IH0") else rec["market"]
        if m_key in by_mkt:
            bm = by_mkt[m_key]
            bm["total"] += 1
            if not ev["isAssigned"]:
                bm["unassigned"] += 1
            else:
                bm["assigned"] += 1
            if ev["isHeavyLoss"]:
                bm["heavyLoss"] += 1
            if ev["isWin"]:
                bm["win"] += 1
            bm["avgR"] += ev["rMultiple"]

    for m_key, bm in by_mkt.items():
        t = max(bm["total"], 1)
        bm["unassignedPct"] = round(bm["unassigned"] / t * 100.0, 1)
        bm["assignedPct"] = round(bm["assigned"] / t * 100.0, 1)
        bm["heavyLossPct"] = round(bm["heavyLoss"] / t * 100.0, 1)
        bm["winRatePct"] = round(bm["win"] / t * 100.0, 1)
        bm["avgR"] = round(bm["avgR"] / t, 2)

    return {
        "total": total,
        "expiredCount": expired_cnt,
        "activeCount": active_cnt,
        "unassignedCount": unassigned,
        "unassignedPct": round(unassigned / total * 100.0, 1),
        "assignedCount": assigned,
        "assignedPct": round(assigned / total * 100.0, 1),
        "assignedProfitCount": assigned_profit,
        "mildLossCount": mild_loss,
        "heavyLossCount": heavy_loss,
        "heavyLossPct": round(heavy_loss / total * 100.0, 1),
        "winCount": wins,
        "winRatePct": round(wins / total * 100.0, 1),
        "touchedCount": touched,
        "touchedPct": round(touched / total * 100.0, 1),
        "avgRMultiple": round(r_sum / total, 2),
        "avgRocMarginNetPct": round(roc_sum / total, 2),
        "stopTriggerCount": stop_triggers,
        "stopTriggerPct": round(stop_triggers / total * 100.0, 1),
        "winRateStopPct": round(stop_wins / total * 100.0, 1),
        "avgRMultipleStop": round(stop_r_sum / total, 2),
        "byMarket": by_mkt,
    }


def get_historical_review(
    hold_trading_days: int = 20,
    num_cohorts: int = 52,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Reconstruct and evaluate past weekly Short Put recommendation cohorts across 12, 26, 52, or 104 weeks.
    Evaluates:
    1. Overall cohort outcomes and tier comparison
    2. Score bucket calibration monotonicity (90+, 80-90, 70-80, 60-70, <60)
    3. Trend regime & circuit breaker efficacy
    4. Hard stop-loss discipline vs holding to expiration
    """
    num_cohorts = max(4, min(int(num_cohorts or 52), 104))
    hold_trading_days = max(10, min(int(hold_trading_days or 20), 45))

    def _compute() -> Dict[str, Any]:
        ensure_all_bars_loaded(force=False)
        macro_regime = get_macro_vol_regime(force=False)
        dte_calendar = int(round(hold_trading_days * 1.45))

        bars_by_id: Dict[str, List[Dict[str, Any]]] = {}
        for inst in ALL_INSTRUMENTS:
            b = get_instrument_bars(inst["id"], force=False)
            if b and len(b) >= 120:
                bars_by_id[inst["id"]] = b

        ref_bars = bars_by_id.get("CN_FUT:IM0") or bars_by_id.get("US_STK:SPY") or next(iter(bars_by_id.values()))
        total_len = len(ref_bars)

        step_days = 5
        cohort_offsets: List[int] = []
        for w in range(num_cohorts, 0, -1):
            idx_from_end = w * step_days
            if total_len - idx_from_end >= 80:
                cohort_offsets.append(idx_from_end)

        all_records: List[Dict[str, Any]] = []
        cohort_summaries: List[Dict[str, Any]] = []

        # Data structures for score bucket monotonicity & regime validation
        bucket_defs = ["90+", "80-90", "70-80", "60-70", "<60"]
        bucket_raw = {
            b: {"total": 0, "win": 0, "unassigned": 0, "heavyLoss": 0, "r_sum": 0.0}
            for b in bucket_defs
        }
        regime_raw: Dict[str, Dict[str, Any]] = {}

        for c_idx, offset_from_end in enumerate(cohort_offsets):
            scored_at_t0: List[Dict[str, Any]] = []
            is_expired = offset_from_end >= hold_trading_days

            for inst in ALL_INSTRUMENTS:
                iid = inst["id"]
                b_full = bars_by_id.get(iid)
                if not b_full or len(b_full) <= offset_from_end + 65:
                    continue
                cut_idx = len(b_full) - offset_from_end
                hist_slice = b_full[:cut_idx]
                future_slice = b_full[cut_idx : min(len(b_full), cut_idx + hold_trading_days)]
                if not hist_slice or not future_slice:
                    continue

                res = analyze_single_instrument(inst, hist_slice, macro_regime, target_dte=dte_calendar)
                if not res:
                    continue

                scored_at_t0.append({
                    "inst": inst,
                    "res": res,
                    "entryDate": hist_slice[-1].get("t", hist_slice[-1].get("date", "--")),
                    "evalDate": future_slice[-1].get("t", future_slice[-1].get("date", "--")),
                    "futureBars": future_slice,
                })

                # Record score bucket & regime outcomes across full universe (if expired)
                if is_expired and len(future_slice) >= hold_trading_days:
                    sc = res["putScore"]
                    bkey = "90+" if sc >= 90 else ("80-90" if sc >= 80 else ("70-80" if sc >= 70 else ("60-70" if sc >= 60 else "<60")))
                    bal = res["tiers"]["balanced"]
                    k_b = bal["strike"]
                    prem_b = bal["premium"]
                    be_b = bal["breakeven"]
                    s_end = future_slice[-1]["c"]

                    is_win_b = s_end >= be_b
                    is_unassigned_b = s_end >= k_b
                    r_b = (prem_b - max(0.0, k_b - s_end)) / prem_b if prem_b > 0 else 0.0
                    is_heavy_b = r_b <= -2.0 or (((be_b - s_end) / res["price"] * 100.0) >= 3.0 if s_end < be_b else False)

                    bk = bucket_raw[bkey]
                    bk["total"] += 1
                    if is_win_b: bk["win"] += 1
                    if is_unassigned_b: bk["unassigned"] += 1
                    if is_heavy_b: bk["heavyLoss"] += 1
                    bk["r_sum"] += r_b

                    reg = res.get("trendRegime", "其他")
                    if reg not in regime_raw:
                        regime_raw[reg] = {"total": 0, "win": 0, "unassigned": 0, "heavyLoss": 0, "r_sum": 0.0}
                    rg = regime_raw[reg]
                    rg["total"] += 1
                    if is_win_b: rg["win"] += 1
                    if is_unassigned_b: rg["unassigned"] += 1
                    if is_heavy_b: rg["heavyLoss"] += 1
                    rg["r_sum"] += r_b

            if not scored_at_t0:
                continue

            scored_at_t0.sort(key=lambda x: x["res"]["putScore"], reverse=True)
            entry_date_str = scored_at_t0[0]["entryDate"]
            eval_date_str = scored_at_t0[0]["evalDate"]

            # Filter candidates for weekly Top portfolio (>= 80 pts)
            scored_80 = [x for x in scored_at_t0 if float(x["res"].get("putScore", 0.0)) >= 80.0]
            idx_items = [x for x in scored_80 if x["inst"]["id"] in ("CN_FUT:IM0", "CN_FUT:IF0", "CN_FUT:IH0")]
            us_stk_items = [x for x in scored_80 if x["inst"]["market"] == "us_stk"]
            us_fut_items = [x for x in scored_80 if x["inst"]["market"] == "us_fut"]
            cn_comm_items = [
                x for x in scored_80
                if x["inst"]["market"] == "cn_fut" and x["inst"]["id"] not in ("CN_FUT:IM0", "CN_FUT:IF0", "CN_FUT:IH0")
            ]

            def _pick_top(items_list: List[Dict[str, Any]], n: int = 4) -> List[Dict[str, Any]]:
                rows_only = [x["res"] for x in items_list]
                picked_rows = _select_diversified_top(rows_only, top_n=n, max_per_sector=2)
                picked_ids = {r["id"] for r in picked_rows}
                return [x for x in items_list if x["inst"]["id"] in picked_ids]

            weekly_portfolio = (
                idx_items
                + _pick_top(us_stk_items, 4)
                + _pick_top(us_fut_items, 4)
                + _pick_top(cn_comm_items, 4)
            )

            cohort_label = f"第{c_idx + 1}期 ({entry_date_str[5:]})"
            cohort_records: List[Dict[str, Any]] = []

            for item in weekly_portfolio:
                inst = item["inst"]
                res = item["res"]
                fut_bars = item["futureBars"]

                outcomes_by_tier = {}
                for tk in ("conservative", "balanced", "aggressive"):
                    outcomes_by_tier[tk] = _evaluate_put_outcome(
                        inst=inst,
                        entry_spot=res["price"],
                        tier_obj=res["tiers"][tk],
                        future_bars=fut_bars,
                        is_expired=is_expired,
                    )

                rec_tier_key = res.get("recommendedTierKey") or "balanced"
                outcomes_by_tier["auto"] = outcomes_by_tier[rec_tier_key]

                record = {
                    "cohortIndex": c_idx + 1,
                    "cohortLabel": cohort_label,
                    "entryDate": item["entryDate"],
                    "evalDate": item["evalDate"],
                    "holdDays": len(fut_bars),
                    "isExpired": is_expired,
                    "id": inst["id"],
                    "symbol": inst["symbol"],
                    "name": inst["name"],
                    "market": inst["market"],
                    "marketLabel": "A股股指" if inst["id"] in ("CN_FUT:IM0", "CN_FUT:IF0", "CN_FUT:IH0") else res["marketLabel"],
                    "sector": res["sector"],
                    "currency": res["currency"],
                    "putScore": res["putScore"],
                    "archetype": res["archetype"],
                    "entryPrice": res["price"],
                    "atmIvPct": res["atmIvPct"],
                    "rsi14": res["rsi14"],
                    "recommendedTierKey": rec_tier_key,
                    "outcomes": outcomes_by_tier,
                }
                cohort_records.append(record)
                all_records.append(record)

            c_tiers = {}
            for tk in ("auto", "conservative", "balanced", "aggressive"):
                st = _aggregate_stats(cohort_records, tk)
                c_tiers[tk] = {
                    "total": st["total"],
                    "unassignedCount": st["unassignedCount"],
                    "assignedProfitCount": st["assignedProfitCount"],
                    "mildLossCount": st["mildLossCount"],
                    "heavyLossCount": st["heavyLossCount"],
                    "winRatePct": st["winRatePct"],
                    "unassignedPct": st["unassignedPct"],
                    "avgRMultiple": st["avgRMultiple"],
                    "avgRocMarginNetPct": st["avgRocMarginNetPct"],
                }

            cohort_summaries.append({
                "cohortIndex": c_idx + 1,
                "cohortLabel": cohort_label,
                "entryDate": entry_date_str,
                "evalDate": eval_date_str,
                "isExpired": is_expired,
                "tiers": c_tiers,
            })

        overall_by_tier = {
            tk: _aggregate_stats(all_records, tk)
            for tk in ("auto", "conservative", "balanced", "aggressive")
        }

        # Build Score Bucket Monotonicity Table
        score_buckets_out = []
        for bkey in bucket_defs:
            raw = bucket_raw[bkey]
            tot = max(raw["total"], 1)
            score_buckets_out.append({
                "bucket": bkey,
                "total": raw["total"],
                "winRatePct": round(raw["win"] / tot * 100.0, 1),
                "unassignedPct": round(raw["unassigned"] / tot * 100.0, 1),
                "heavyLossPct": round(raw["heavyLoss"] / tot * 100.0, 1),
                "avgRMultiple": round(raw["r_sum"] / tot, 2),
            })

        # Build Regime Efficacy Table
        regimes_out = []
        for reg, raw in sorted(regime_raw.items(), key=lambda x: x[1]["heavyLoss"] / max(x[1]["total"], 1)):
            tot = max(raw["total"], 1)
            regimes_out.append({
                "regime": reg,
                "total": raw["total"],
                "winRatePct": round(raw["win"] / tot * 100.0, 1),
                "unassignedPct": round(raw["unassigned"] / tot * 100.0, 1),
                "heavyLossPct": round(raw["heavyLoss"] / tot * 100.0, 1),
                "avgRMultiple": round(raw["r_sum"] / tot, 2),
            })

        # Hard Stop-Loss vs Hold-to-Expiry Comparison
        auto_stats = overall_by_tier["auto"]
        stop_loss_comp = {
            "total": auto_stats["total"],
            "holdWinRatePct": auto_stats["winRatePct"],
            "holdAvgR": auto_stats["avgRMultiple"],
            "holdHeavyLossPct": auto_stats["heavyLossPct"],
            "stopTriggerCount": auto_stats["stopTriggerCount"],
            "stopTriggerPct": auto_stats["stopTriggerPct"],
            "stopWinRatePct": auto_stats["winRateStopPct"],
            "stopAvgR": auto_stats["avgRMultipleStop"],
            "maxLossCap": -2.50,
        }

        all_records.sort(key=lambda r: (r["cohortIndex"], r["putScore"]), reverse=True)

        payload = {
            "updatedAt": now_bj(),
            "numCohorts": len(cohort_summaries),
            "holdTradingDays": hold_trading_days,
            "cohorts": cohort_summaries,
            "tierStats": overall_by_tier,
            "scoreBuckets": score_buckets_out,
            "regimes": regimes_out,
            "stopLossComparison": stop_loss_comp,
            "records": all_records,
        }

        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(LEDGER_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "updatedAt": payload["updatedAt"],
                        "tierStats": payload["tierStats"],
                        "scoreBuckets": payload["scoreBuckets"],
                        "stopLossComparison": payload["stopLossComparison"],
                        "cohorts": payload["cohorts"],
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as exc:
            logger.warning("Failed to save weekly ledger: %s", exc)

        return payload

    return cached(f"hist_review:{hold_trading_days}:{num_cohorts}", 180.0, _compute, force=force)


def run_portfolio_stress_test(
    target_dte: int = 30,
    portfolio_rows: Optional[List[Dict[str, Any]]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Run institutional extreme stress testing on recommended Short Put portfolio under 4 scenarios:
    - Scenario 0: Baseline (Current Spot, Current ATM IV)
    - Scenario 1: -1.0σ Mild Pullback (Spot -1σ, ATM IV +25%)
    - Scenario 2: -2.0σ Severe Liquidity Shock (Spot -2σ, ATM IV +50%)
    - Scenario 3: -3.0σ Extreme Black-Swan Crash (Spot -3σ, ATM IV +100%)
    """
    def _compute() -> Dict[str, Any]:
        rows = portfolio_rows
        if not rows:
            recs = get_weekly_recommendations(target_dte=target_dte, force=force)
            top_us = recs.get("topPicks", {}).get("us_stk", [])
            top_cn_fut = recs.get("topPicks", {}).get("cn_fut", [])
            top_cn_idx = recs.get("cnIndexOptions", [])
            top_us_fut = recs.get("topPicks", {}).get("us_fut", [])
            rows = top_us + top_cn_fut + top_cn_idx + top_us_fut

        scenarios = [
            {"key": "base", "label": "基准常态 (Base)", "sigmaMult": 0.0, "ivMult": 1.0, "tone": "neutral"},
            {"key": "s1", "label": "轻度回踩 (-1.0σ · 隐波+25%)", "sigmaMult": 1.0, "ivMult": 1.25, "tone": "gold"},
            {"key": "s2", "label": "重度冲击 (-2.0σ · 隐波+50%)", "sigmaMult": 2.0, "ivMult": 1.50, "tone": "gold"},
            {"key": "s3", "label": "极端黑天鹅 (-3.0σ · 隐波+100%)", "sigmaMult": 3.0, "ivMult": 2.00, "tone": "bear"},
        ]

        scenario_results: List[Dict[str, Any]] = []

        # Baseline sums
        base_contracts = []
        for r in rows:
            inst = get_instrument(r["id"]) or r
            t = r.get("recommendedTier") or r.get("tiers", {}).get("balanced") or {}
            spot = float(r["price"])
            strike = float(t.get("strike", spot * 0.95))
            prem = float(t.get("premium", spot * 0.015))
            iv = float(t.get("ivPct", 20.0)) / 100.0
            hv = float(r.get("hv20Pct", 20.0)) / 100.0
            mult = float(inst.get("multiplier", 100))
            is_fut = inst.get("market") != "us_stk"
            mkt = inst.get("market", "us_stk")
            init_margin = compute_exchange_margin(inst, spot, strike, prem)
            base_contracts.append({
                "inst": inst,
                "id": r["id"],
                "symbol": r["symbol"],
                "name": r["name"],
                "market": mkt,
                "sector": inst.get("sector", ""),
                "spot": spot,
                "strike": strike,
                "initialPrem": prem,
                "initialIv": iv,
                "hv": hv,
                "mult": mult,
                "isFut": is_fut,
                "initMargin": init_margin,
            })

        base_total_margin = sum(c["initMargin"] for c in base_contracts)

        for sc in scenarios:
            s_mult = sc["sigmaMult"]
            iv_mult = sc["ivMult"]
            tot_margin = 0.0
            tot_pnl = 0.0
            mkt_stats: Dict[str, Dict[str, float]] = {
                "us_stk": {"margin": 0.0, "pnl": 0.0},
                "us_fut": {"margin": 0.0, "pnl": 0.0},
                "cn_fut": {"margin": 0.0, "pnl": 0.0},
            }

            for c in base_contracts:
                spot = c["spot"]
                strike = c["strike"]
                prem = c["initialPrem"]
                mult = c["mult"]
                hv = c["hv"]
                iv = c["initialIv"]
                inst_obj = c["inst"]

                # 1-week price shock in sigma
                shock_pct = s_mult * hv * (5.0 / 252.0) ** 0.5
                s_shocked = spot * max(0.20, 1.0 - shock_pct)
                iv_shocked = iv * iv_mult

                reprice = price_put_and_greeks(
                    spot=s_shocked,
                    strike=strike,
                    dte=max(target_dte - 5, 1),
                    iv=iv_shocked,
                    is_futures=c["isFut"],
                )
                new_prem = float(reprice["premium"])
                pnl = (prem - new_prem) * mult
                new_margin = compute_exchange_margin(inst_obj, s_shocked, strike, new_prem)

                tot_margin += new_margin
                tot_pnl += pnl

                m_k = "cn_fut" if c["market"] == "cn_fut" or c["id"] in ("CN_FUT:IM0", "CN_FUT:IF0", "CN_FUT:IH0") else c["market"]
                if m_k in mkt_stats:
                    mkt_stats[m_k]["margin"] += new_margin
                    mkt_stats[m_k]["pnl"] += pnl

            surge_ratio = round(tot_margin / max(base_total_margin, 1.0), 2)
            scenario_results.append({
                "key": sc["key"],
                "label": sc["label"],
                "tone": sc["tone"],
                "totalMargin": round(tot_margin, 0),
                "marginSurgeRatio": surge_ratio,
                "totalPnl": round(tot_pnl, 0),
                "byMarket": mkt_stats,
            })

        return {
            "updatedAt": now_bj(),
            "targetDte": target_dte,
            "contractCount": len(base_contracts),
            "baseMargin": round(base_total_margin, 0),
            "scenarios": scenario_results,
        }

    return cached(f"stress_test:{target_dte}", 180.0, _compute, force=force)


if __name__ == "__main__":
    rev = get_historical_review(num_cohorts=52)
    print(f"Total cohorts: {rev['numCohorts']}, Total trades: {len(rev['records'])}")
    print("\n--- Score Buckets ---")
    for b in rev["scoreBuckets"]:
        print(f"  [{b['bucket']}] N={b['total']} 胜率={b['winRatePct']}% 未行权={b['unassignedPct']}% 大亏={b['heavyLossPct']}% R={b['avgRMultiple']}R")
    print("\n--- Stop-Loss Comparison ---")
    print(rev["stopLossComparison"])
    print("\n--- Stress Testing ---")
    st = run_portfolio_stress_test(30)
    for sc in st["scenarios"]:
        print(f"  [{sc['label']}] Margin: {sc['totalMargin']} (Surge: {sc['marginSurgeRatio']}x) PnL: {sc['totalPnl']}")
