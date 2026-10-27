# -*- coding: utf-8 -*-
"""
Historical Recommendation Tracker & Rolling Cohort Backtest Engine (卖Put历史推荐回顾与行权/盈亏复盘引擎)
Tracks and evaluates:
1. How many recommended Short Put varieties expired SAFE (unassigned, full premium kept)
2. How many were ASSIGNED (exercised, S_end < Strike K):
   - Assigned but still profitable (BE <= S_end < K)
   - Assigned with mild loss (S_end < BE, loss <= 2x premium and buffer breach <= 3%)
3. How many suffered HEAVY LOSS (大幅亏损: net loss > 2x premium OR price dropped > 3% below breakeven)
4. Persistent weekly ledger (`data/weekly_ledger.json`) + 12-week rolling historical cohort reconstruction.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from data_engine import ensure_all_bars_loaded, get_instrument_bars, get_macro_vol_regime
from http_utils import DATA_DIR, cached, now_bj
from recommender import _select_diversified_top, analyze_single_instrument
from universe import ALL_INSTRUMENTS, get_instrument

logger = logging.getLogger(__name__)

LEDGER_FILE = os.path.join(DATA_DIR, "weekly_ledger_v1.json")


def _evaluate_put_outcome(
    inst: Dict[str, Any],
    entry_spot: float,
    tier_obj: Dict[str, Any],
    future_bars: List[Dict[str, Any]],
    is_expired: bool,
) -> Dict[str, Any]:
    """
    Evaluate what happened to a Short Put position given the subsequent daily bars.
    """
    dp = int(inst.get("dp", 2))
    mult = float(inst.get("multiplier", 100))
    strike = float(tier_obj["strike"])
    prem = float(tier_obj["premium"])
    be = float(tier_obj["breakeven"])
    contract_prem = float(tier_obj["contractPremium"])
    margin_req = float(tier_obj.get("marginReq") or max(strike * mult * 0.15, 1.0))

    if not future_bars:
        end_price = entry_spot
        min_low = entry_spot
        min_date = "--"
    else:
        end_price = float(future_bars[-1]["c"])
        min_bar = min(future_bars, key=lambda b: float(b.get("l", b["c"])))
        min_low = float(min_bar.get("l", min_bar["c"]))
        min_date = min_bar.get("date", "--")

    underlying_ret_pct = ((end_price - entry_spot) / entry_spot * 100.0) if entry_spot > 0 else 0.0
    max_dd_pct = ((min_low - entry_spot) / entry_spot * 100.0) if entry_spot > 0 else 0.0

    # Intrinsic value at evaluation / expiration
    intrinsic_end = max(0.0, strike - end_price)
    net_unit_pnl = prem - intrinsic_end
    net_contract_pnl = net_unit_pnl * mult

    # R-multiple relative to premium collected (+1.0R = kept 100% of premium; -2.0R = lost 2x premium)
    r_multiple = (net_unit_pnl / prem) if prem > 0 else 0.0
    roc_margin_net_pct = (net_contract_pnl / margin_req * 100.0) if margin_req > 0 else 0.0

    touched_strike = min_low < strike
    is_assigned = end_price < strike
    below_be_pct = ((be - end_price) / entry_spot * 100.0) if (end_price < be and entry_spot > 0) else 0.0

    # Classify into 4 transparent outcomes
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
        # Net loss (end_price < breakeven)
        is_win = False
        # Heavy loss criterion: lost > 2.0x premium collected OR fell > 3.0% below breakeven
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

    return {
        "strike": round(strike, dp),
        "otmPct": tier_obj["otmPct"],
        "premium": round(prem, max(dp, 2)),
        "contractPremium": round(contract_prem, 0 if contract_prem >= 100 else 2),
        "breakeven": round(be, dp),
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
            "avgRMultiple": 0.0,
            "avgRocMarginNetPct": 0.0,
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
        "byMarket": by_mkt,
    }


def get_historical_review(hold_trading_days: int = 20, num_cohorts: int = 12, force: bool = False) -> Dict[str, Any]:
    """
    Reconstruct and evaluate the past `num_cohorts` weekly Short Put recommendation cohorts
    (each spaced by 5 trading days = 1 week, evaluated over `hold_trading_days` = ~28-30 calendar days).
    Also persists the ledger to `data/weekly_ledger_v1.json`.
    """
    def _compute() -> Dict[str, Any]:
        ensure_all_bars_loaded(force=False)
        macro_regime = get_macro_vol_regime(force=False)
        dte_calendar = int(round(hold_trading_days * 1.45))  # 20 trading days ~ 29 calendar days

        # Pre-load bars for all instruments
        bars_by_id: Dict[str, List[Dict[str, Any]]] = {}
        for inst in ALL_INSTRUMENTS:
            b = get_instrument_bars(inst["id"], force=False)
            if b and len(b) >= 120:
                bars_by_id[inst["id"]] = b

        # Use SPY / IM0 dates as reference timeline for weekly cohorts
        ref_bars = bars_by_id.get("CN_FUT:IM0") or bars_by_id.get("US_STK:SPY") or next(iter(bars_by_id.values()))
        total_len = len(ref_bars)

        # Build cohort offsets: from oldest (e.g. 12 weeks ago) to most recent (1 week ago)
        # step = 5 trading days per week
        step_days = 5
        cohort_offsets: List[int] = []
        for w in range(num_cohorts, 0, -1):
            idx_from_end = w * step_days
            if total_len - idx_from_end >= 80:
                cohort_offsets.append(idx_from_end)

        all_records: List[Dict[str, Any]] = []
        cohort_summaries: List[Dict[str, Any]] = []

        for c_idx, offset_from_end in enumerate(cohort_offsets):
            # Evaluate each instrument as of `len(bars) - offset_from_end`
            scored_at_t0: List[Dict[str, Any]] = []
            entry_date_str = "--"
            eval_date_str = "--"
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
                    "entryDate": hist_slice[-1].get("date", "--"),
                    "evalDate": future_slice[-1].get("date", "--"),
                    "futureBars": future_slice,
                })

            if not scored_at_t0:
                continue

            scored_at_t0.sort(key=lambda x: x["res"]["putScore"], reverse=True)
            entry_date_str = scored_at_t0[0]["entryDate"]
            eval_date_str = scored_at_t0[0]["evalDate"]

            # Select that week's recommended portfolio:
            # 1) All 3 A-share index options (IM0, IF0, IH0)
            # 2) Top 4 US Stocks, Top 4 US Futures, Top 4 CN Commodity Futures
            idx_items = [x for x in scored_at_t0 if x["inst"]["id"] in ("CN_FUT:IM0", "CN_FUT:IF0", "CN_FUT:IH0")]
            us_stk_items = [x for x in scored_at_t0 if x["inst"]["market"] == "us_stk"]
            us_fut_items = [x for x in scored_at_t0 if x["inst"]["market"] == "us_fut"]
            cn_comm_items = [
                x for x in scored_at_t0
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

            # Summarize this cohort for each tier
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

        # Overall statistics across all cohorts for each tier preference
        overall_by_tier = {
            tk: _aggregate_stats(all_records, tk)
            for tk in ("auto", "conservative", "balanced", "aggressive")
        }

        # Sort records newest cohort first, and within cohort highlight heavy losses / highest score
        all_records.sort(key=lambda r: (r["cohortIndex"], r["putScore"]), reverse=True)

        payload = {
            "updatedAt": now_bj(),
            "numCohorts": len(cohort_summaries),
            "holdTradingDays": hold_trading_days,
            "cohorts": cohort_summaries,
            "tierStats": overall_by_tier,
            "records": all_records,
        }

        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(LEDGER_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "updatedAt": payload["updatedAt"],
                        "tierStats": payload["tierStats"],
                        "cohorts": payload["cohorts"],
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as exc:
            logger.warning("Failed to save weekly ledger: %s", exc)

        return payload

    return cached(f"hist_review:{hold_trading_days}:{num_cohorts}", 120.0, _compute, force=force)


if __name__ == "__main__":
    rev = get_historical_review()
    print(f"Total cohorts: {rev['numCohorts']}, Total recommended trades tracked: {len(rev['records'])}")
    for tk, st in rev["tierStats"].items():
        print(
            f"  [{tk:12s}] Total={st['total']} | 未行权={st['unassignedCount']} ({st['unassignedPct']}%) | "
            f"被行权={st['assignedCount']} ({st['assignedPct']}%, 含浅行权仍盈利={st['assignedProfitCount']}, 小幅浮亏={st['mildLossCount']}) | "
            f"大幅亏损={st['heavyLossCount']} ({st['heavyLossPct']}%) | 总盈利胜率={st['winRatePct']}% | 平均R倍数={st['avgRMultiple']}R"
        )

