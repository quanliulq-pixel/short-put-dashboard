# -*- coding: utf-8 -*-
"""
Full-Lifecycle Short Put Portfolio Tracker, Rollover/Exit Signal Radar,
Macro Event Shield & Automated Webhook Alert Engine.
(实盘/模拟持仓账本 · 止盈/移仓/止损动态雷达 · 宏观事件与长假提保护盾 · 钉钉/飞书/企微日报推送)
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
import uuid

from backtest_engine import compute_exchange_margin
from data_engine import get_instrument_bars
from http_utils import BJ_TZ, DATA_DIR, _SESSION, _third_friday, now_bj
from options_math import (
    build_bull_put_spread,
    build_wheel_covered_call,
    dynamic_strike_step,
    price_put_and_greeks,
    round_to_step,
    skew_adjusted_iv,
    solve_roll_down_and_out,
)
from recommender import get_weekly_recommendations
from universe import get_instrument

logger = logging.getLogger(__name__)

POSITIONS_FILE = os.path.join(DATA_DIR, "positions_ledger_v1.json")
WEBHOOK_CFG_FILE = os.path.join(DATA_DIR, "webhook_config_v1.json")


# ---------------------------------------------------------------------------
# 1. Macro Event & Exchange Holiday Margin Shield (宏观事件与长假提保日历护盾)
# ---------------------------------------------------------------------------
def _first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    days_to_fri = (4 - d.weekday()) % 7
    return d + timedelta(days=days_to_fri)


def get_macro_event_shield(target_dte: int = 30) -> Dict[str, Any]:
    """
    Build a dynamic 45-day forward radar of high-impact macro catalysts & exchange margin windows:
    - Federal Reserve FOMC Rate Decisions
    - US CPI Inflation Releases
    - US Non-Farm Payrolls (NFP - 1st Friday)
    - Monthly Options Expiration (OPEX / CFFEX MO/IO/HO 3rd Friday)
    - China Statutory Holidays (Pre-holiday exchange margin hikes &夜盘停盘跳空风险)
    """
    today = datetime.now(BJ_TZ).date()
    events: List[Dict[str, Any]] = []

    # Check current month and next 2 months
    for add_m in (0, 1, 2):
        y = today.year + (today.month + add_m - 1) // 12
        m = (today.month + add_m - 1) % 12 + 1
        last_d = calendar.monthrange(y, m)[1]

        # 1) US Non-Farm Payrolls (1st Friday of every month)
        nfp_d = _first_friday(y, m)
        events.append({
            "date": nfp_d,
            "title": f"{m}月美国非农就业报告 (NFP)",
            "category": "宏观数据",
            "markets": "美股 / 美债 / 黄金 / 外盘期货",
            "riskLevel": "MEDIUM",
            "advice": "非农夜20:30(冬令21:30)美债TLT、黄金GC及纳指QQQ短线跳空加剧，周度末日Put宜提前减仓。",
        })

        # 2) US CPI Inflation Release (~12th-14th of every month, adjust weekend to Wed/Thu)
        cpi_d = date(y, m, min(13, last_d))
        if cpi_d.weekday() == 5:
            cpi_d -= timedelta(days=1)
        elif cpi_d.weekday() == 6:
            cpi_d += timedelta(days=2)
        events.append({
            "date": cpi_d,
            "title": f"{m}月美国CPI通胀数据发布",
            "category": "宏观数据",
            "markets": "美股 / 美期货 / 贵金属",
            "riskLevel": "HIGH",
            "advice": "CPI数据直接触发美联储降息预期重定价，建议优先采用牛市看跌价差(Bull Put Spread)锁死左尾风险。",
        })

        # 3) Monthly OPEX & CFFEX Index Option Expiration (3rd Friday)
        opex_d = _third_friday(y, m)
        events.append({
            "date": opex_d,
            "title": f"{m}月中金所股指期权(MO/IO/HO)及美股月度期权交割日",
            "category": "期权交割",
            "markets": "A股三大股指 / 美股与ETF",
            "riskLevel": "MEDIUM",
            "advice": "交割周Gamma风险陡增，临近行权价的浅虚值Put建议提前移仓(Roll Out)至下月合约。",
        })

        # 4) FOMC Rate Decision Windows (Jan, Mar, May, Jun, Jul, Sep, Nov, Dec ~18th-20th or 1st-7th)
        fomc_day_map = {1: 29, 3: 19, 5: 7, 6: 18, 7: 30, 9: 17, 11: 7, 12: 17}
        if m in fomc_day_map:
            fd = date(y, m, min(fomc_day_map[m], last_d))
            events.append({
                "date": fd,
                "title": f"美联储 FOMC 议息决议与鲍威尔发布会 ({m}月例会)",
                "category": "央行议息",
                "markets": "全球全市场 (美股 / 美期 / 商品)",
                "riskLevel": "HIGH",
                "advice": "议息夜隐波(VIX)常现先涨后崩(IV Crush)，适合在决议前高IV时卖出深虚值Put或构建牛市价差。",
            })

        # 5) China Statutory Holidays & Exchange Pre-Holiday Margin Hike Windows
        cn_holidays = [
            (1, 1, "元旦假期 · 国内休市与节前风控"),
            (2, 10, "春节长假 · 交易所提保+外盘连续多日跳空预警"),
            (4, 4, "清明假期 · 国内夜盘停盘与外盘跳空预警"),
            (5, 1, "五一劳动节长假 · 期货交易所提保(+2%~5%)预警"),
            (6, 10, "端午假期 · 国内夜盘停盘风控"),
            (10, 1, "国庆黄金周长假 · 交易所大幅提保+外盘7天累计跳空预警"),
        ]
        for hm, hd, htitle in cn_holidays:
            if hm == m:
                events.append({
                    "date": date(y, hm, hd),
                    "title": htitle,
                    "category": "长假提保",
                    "markets": "中国商品期货 / 中金所股指期权",
                    "riskLevel": "HIGH" if hm in (2, 5, 10) else "MEDIUM",
                    "advice": "国内长假前3个交易日交易所上调保证金比例，且假期外盘波动可能引发节后大幅跳空，节前务必降杠杆或平掉浅虚值裸Put。",
                })

    upcoming: List[Dict[str, Any]] = []
    in_dte_high_count = 0
    for ev in events:
        diff = (ev["date"] - today).days
        if -1 <= diff <= 45:
            in_window = 0 <= diff <= target_dte
            if in_window and ev["riskLevel"] == "HIGH":
                in_dte_high_count += 1
            upcoming.append({
                "date": ev["date"].strftime("%Y-%m-%d"),
                "monthDay": ev["date"].strftime("%m-%d"),
                "daysAway": diff,
                "daysText": "今日触发" if diff == 0 else ("昨日刚过" if diff == -1 else f"{diff}天后"),
                "title": ev["title"],
                "category": ev["category"],
                "markets": ev["markets"],
                "riskLevel": ev["riskLevel"],
                "inDteWindow": in_window,
                "advice": ev["advice"],
            })

    upcoming.sort(key=lambda x: x["daysAway"])
    return {
        "today": today.strftime("%Y-%m-%d"),
        "targetDte": target_dte,
        "highRiskInWindowCount": in_dte_high_count,
        "events": upcoming[:8],
    }


# ---------------------------------------------------------------------------
# 2. Portfolio Position Ledger & Dynamic Rollover / Stop-Loss / Wheel Radar
# ---------------------------------------------------------------------------
def _seed_default_positions() -> List[Dict[str, Any]]:
    """
    Create 5 realistic institutional positions anchored dynamically to live market prices
    so the user immediately sees all 4 action signal archetypes in action:
    1) TAKE_PROFIT (70%+ time decay captured -> lock in profit)
    2) ROLL_DEFENSE (Spot pulled back near strike -> Roll Down & Out for Net Credit)
    3) WHEEL_CALL (Assigned Put -> Sell Covered Call to lower cost basis)
    4) HOLD_THETA (Healthy OTM Short Put & Bull Put Spread collecting daily Theta)
    """
    today = datetime.now(BJ_TZ).date()
    seeds = [
        {
            "instId": "CN_FUT:IM0",
            "strategyType": "SHORT_PUT",
            "scenario": "TAKE_PROFIT",
            "lots": 1,
            "openDaysAgo": 16,
            "origDte": 30,
            "note": "中金所MO中证1000深虚值收租仓（已赚超70%时间价值）",
        },
        {
            "instId": "US_STK:NVDA",
            "strategyType": "BULL_PUT_SPREAD",
            "scenario": "HOLD_THETA",
            "lots": 2,
            "openDaysAgo": 9,
            "origDte": 30,
            "note": "英伟达AI龙头牛市看跌价差（买保护腿省65%保证金）",
        },
        {
            "instId": "CN_FUT:M0",
            "strategyType": "SHORT_PUT",
            "scenario": "ROLL_DEFENSE",
            "lots": 5,
            "openDaysAgo": 12,
            "origDte": 30,
            "note": "大商所豆粕浅虚值测试行权价（触发向下展期Roll雷达）",
        },
        {
            "instId": "US_STK:AAPL",
            "strategyType": "WHEEL_COVERED_CALL",
            "scenario": "WHEEL_CALL",
            "lots": 1,
            "openDaysAgo": 22,
            "origDte": 30,
            "note": "苹果CSP到期接货100股后转入车轮策略（待卖备兑Call降成本）",
        },
        {
            "instId": "CN_FUT:AU0",
            "strategyType": "SHORT_PUT",
            "scenario": "HOLD_THETA",
            "lots": 1,
            "openDaysAgo": 7,
            "origDte": 30,
            "note": "上期所沪金回调均线支撑卖Put稳健收租",
        },
    ]

    recs = get_weekly_recommendations(target_dte=30, force=False)
    rec_by_id = {r["id"]: r for r in (recs.get("all") or [])}

    out: List[Dict[str, Any]] = []
    for s in seeds:
        inst = get_instrument(s["instId"])
        if not inst:
            continue
        rec_row = rec_by_id.get(inst["id"])
        if rec_row:
            spot = float(rec_row["price"])
            atm_iv = float(rec_row["atmIvPct"]) / 100.0
        else:
            bars = get_instrument_bars(inst["id"], force=False)
            spot = float(bars[-1]["c"]) if bars else 100.0
            atm_iv = 0.24 if inst["market"] != "cn_fut" else 0.21

        dp = int(inst.get("dp", 2))
        step = dynamic_strike_step(spot, float(inst.get("strike_step", 1.0)), dp=dp)
        is_fut = inst["market"] in ("us_fut", "cn_fut")
        r = 0.020 if inst["market"] == "cn_fut" else 0.042
        skew_coeff = float(inst.get("iv_skew", 0.12))

        rem_dte = max(5, s["origDte"] - s["openDaysAgo"])
        open_dt = (today - timedelta(days=s["openDaysAgo"])).strftime("%Y-%m-%d")
        exp_dt = (today + timedelta(days=rem_dte)).strftime("%Y-%m-%d")

        if s["scenario"] == "TAKE_PROFIT":
            # Strike 8.5% below current spot; opened when spot was 4% lower -> ~72% profit captured
            strike = round_to_step(spot * 0.915, step, dp=dp)
            entry_spot = round(spot * 0.96, dp)
            strike_iv = skew_adjusted_iv(atm_iv, spot, strike, skew_coeff=skew_coeff)
            cur_res = price_put_and_greeks(spot, strike, rem_dte, strike_iv, r=r, is_futures=is_fut)
            entry_prem = round(cur_res["premium"] * 3.6, max(dp, 2))
            long_k = None
        elif s["scenario"] == "ROLL_DEFENSE":
            # Strike very close to current spot (spot is only 0.4% above strike) -> Delta ~ -0.44, needs Roll Down & Out
            strike = round_to_step(spot * 0.996, step, dp=dp)
            entry_spot = round(spot * 1.035, dp)
            strike_iv = skew_adjusted_iv(atm_iv, spot, strike, skew_coeff=skew_coeff)
            cur_res = price_put_and_greeks(spot, strike, rem_dte, strike_iv, r=r, is_futures=is_fut)
            entry_prem = round(cur_res["premium"] * 0.68, max(dp, 2))
            long_k = None
        elif s["scenario"] == "WHEEL_CALL":
            # Assigned at strike ~ 2.2% above current spot, with generous initial put credit
            strike = round_to_step(spot * 1.022, step, dp=dp)
            entry_spot = round(spot * 1.05, dp)
            entry_prem = round(spot * 0.028, max(dp, 2))
            long_k = None
        else:
            # Healthy OTM Theta position (strike ~ 5.5% OTM) with ~35% profit already captured
            strike = round_to_step(spot * 0.945, step, dp=dp)
            entry_spot = round(spot * 0.985, dp)
            strike_iv = skew_adjusted_iv(atm_iv, spot, strike, skew_coeff=skew_coeff)
            cur_res = price_put_and_greeks(spot, strike, rem_dte, strike_iv, r=r, is_futures=is_fut)
            cur_p = cur_res["premium"]
            long_k = round_to_step(strike - max(step * 2, spot * 0.045), step, dp=dp) if s["strategyType"] == "BULL_PUT_SPREAD" else None
            if long_k and long_k < strike:
                long_iv = skew_adjusted_iv(atm_iv, spot, long_k, skew_coeff=skew_coeff)
                long_res = price_put_and_greeks(spot, long_k, rem_dte, long_iv, r=r, is_futures=is_fut)
                cur_p = max(0.05, cur_p - long_res["premium"])
            entry_prem = round(cur_p * 1.55, max(dp, 2))

        out.append({
            "posId": f"POS-{uuid.uuid4().hex[:8].upper()}",
            "instId": inst["id"],
            "symbol": inst["symbol"],
            "name": inst["name"],
            "market": inst["market"],
            "strategyType": s["strategyType"],
            "strike": round(strike, dp),
            "longStrike": round(long_k, dp) if long_k else None,
            "entrySpot": entry_spot,
            "entryPremium": entry_prem,
            "lots": int(s["lots"]),
            "openDate": open_dt,
            "expiryDate": exp_dt,
            "origDte": int(s["origDte"]),
            "entryIvPct": round(atm_iv * 100.0, 1),
            "note": s["note"],
        })

    return out


def _load_raw_positions() -> List[Dict[str, Any]]:
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception as exc:
            logger.warning("Failed to read positions file: %s", exc)
    seeded = _seed_default_positions()
    _save_raw_positions(seeded)
    return seeded


def _save_raw_positions(positions: List[Dict[str, Any]]) -> None:
    try:
        with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(positions, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("Failed to save positions file: %s", exc)


def add_portfolio_position(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Add a new position to the persistent portfolio ledger."""
    inst_id = str(payload.get("instId") or "CN_FUT:IM0")
    inst = get_instrument(inst_id)
    if not inst:
        raise ValueError(f"Unknown instrument: {inst_id}")

    bars = get_instrument_bars(inst["id"], force=False)
    spot = float(payload.get("entrySpot") or (bars[-1]["c"] if bars else 100.0))
    dp = int(inst.get("dp", 2))
    strike = float(payload.get("strike") or round(spot * 0.94, dp))
    long_strike_raw = payload.get("longStrike")
    long_strike = float(long_strike_raw) if (long_strike_raw not in (None, "", 0, "0")) else None
    strategy_type = str(payload.get("strategyType") or ("BULL_PUT_SPREAD" if long_strike else "SHORT_PUT"))
    dte = max(3, int(payload.get("dte") or 30))
    lots = max(1, int(payload.get("lots") or 1))
    iv_pct = float(payload.get("ivPct") or 24.0)
    entry_prem = float(payload.get("entryPremium") or 0.0)

    if entry_prem <= 0:
        is_fut = inst["market"] in ("us_fut", "cn_fut")
        r = 0.020 if inst["market"] == "cn_fut" else 0.042
        res = price_put_and_greeks(spot, strike, dte, iv_pct / 100.0, r=r, is_futures=is_fut)
        entry_prem = round(res["premium"], max(dp, 2))

    today = datetime.now(BJ_TZ).date()
    exp_dt = (today + timedelta(days=dte)).strftime("%Y-%m-%d")

    new_pos = {
        "posId": f"POS-{uuid.uuid4().hex[:8].upper()}",
        "instId": inst["id"],
        "symbol": inst["symbol"],
        "name": inst["name"],
        "market": inst["market"],
        "strategyType": strategy_type,
        "strike": round(strike, dp),
        "longStrike": round(long_strike, dp) if long_strike else None,
        "entrySpot": round(spot, dp),
        "entryPremium": round(entry_prem, max(dp, 2)),
        "lots": lots,
        "openDate": today.strftime("%Y-%m-%d"),
        "expiryDate": str(payload.get("expiryDate") or exp_dt),
        "origDte": dte,
        "entryIvPct": round(iv_pct, 1),
        "note": str(payload.get("note") or "实盘/模拟手动录入持仓"),
    }

    positions = _load_raw_positions()
    positions.insert(0, new_pos)
    _save_raw_positions(positions)
    return get_portfolio_tracker()


def remove_portfolio_position(pos_id: str, reset_default: bool = False) -> Dict[str, Any]:
    """Delete a position by posId, or reset to default institutional demo portfolio."""
    if reset_default:
        seeded = _seed_default_positions()
        _save_raw_positions(seeded)
        return get_portfolio_tracker()

    positions = _load_raw_positions()
    positions = [p for p in positions if p.get("posId") != pos_id]
    _save_raw_positions(positions)
    return get_portfolio_tracker()


def get_portfolio_tracker(target_dte: int = 30) -> Dict[str, Any]:
    """
    Mark all open portfolio positions to live market prices, evaluate Greek exposures,
    and generate actionable Take-Profit / Roll-Down-&-Out / Wheel-Call / -2.5R Stop-Loss signals.
    """
    raw_list = _load_raw_positions()
    recs = get_weekly_recommendations(target_dte=target_dte, force=False)
    rec_by_id = {r["id"]: r for r in (recs.get("all") or [])}
    today = datetime.now(BJ_TZ).date()

    evaluated: List[Dict[str, Any]] = []
    take_profit_count = 0
    roll_defense_count = 0
    stop_loss_count = 0
    wheel_call_count = 0

    total_theta_cny = 0.0
    total_pnl_cny = 0.0
    total_margin_cny = 0.0
    fx_rate = float(((recs.get("macroRegime") or {}).get("items") or {}).get("USDCNY", {}).get("value") or 7.20)

    for p in raw_list:
        inst = get_instrument(p["instId"])
        if not inst:
            continue
        rec_row = rec_by_id.get(inst["id"])
        dp = int(inst.get("dp", 2))
        mult = float(inst.get("multiplier", 100))
        cur = inst["currency"]
        is_fut = inst["market"] in ("us_fut", "cn_fut")
        r = 0.020 if inst["market"] == "cn_fut" else 0.042
        skew_coeff = float(inst.get("iv_skew", 0.12))
        step = dynamic_strike_step(float(p["strike"]), float(inst.get("strike_step", 1.0)), dp=dp)

        spot = float(rec_row["price"]) if rec_row else float(p["entrySpot"])
        atm_iv = (float(rec_row["atmIvPct"]) / 100.0) if rec_row else (float(p.get("entryIvPct") or 24.0) / 100.0)

        try:
            exp_d = datetime.strptime(str(p.get("expiryDate"))[:10], "%Y-%m-%d").date()
            rem_dte = max(1, (exp_d - today).days)
        except Exception:
            rem_dte = 15

        strike = float(p["strike"])
        long_strike = float(p["longStrike"]) if p.get("longStrike") else None
        lots = max(1, int(p.get("lots") or 1))
        entry_prem = float(p["entryPremium"])
        strat = str(p.get("strategyType") or "SHORT_PUT")

        strike_iv = skew_adjusted_iv(atm_iv, spot, strike, skew_coeff=skew_coeff)
        cur_res = price_put_and_greeks(spot, strike, rem_dte, strike_iv, r=r, is_futures=is_fut)
        cur_prem = cur_res["premium"]
        cur_delta = cur_res["delta"]
        cur_theta = cur_res["theta_daily"]

        if strat == "BULL_PUT_SPREAD" and long_strike and long_strike < strike:
            long_iv = skew_adjusted_iv(atm_iv, spot, long_strike, skew_coeff=skew_coeff)
            long_res = price_put_and_greeks(spot, long_strike, rem_dte, long_iv, r=r, is_futures=is_fut)
            cur_prem = max(0.01, cur_prem - long_res["premium"])
            cur_delta = cur_delta - long_res["delta"]
            cur_theta = max(0.0, cur_theta - long_res["theta_daily"])
            width = max(step, strike - long_strike)
            margin_req = max(width - entry_prem, entry_prem * 0.5) * mult * lots
        else:
            margin_req = compute_exchange_margin(inst, spot, strike, cur_prem) * lots

        unit_pnl = entry_prem - cur_prem
        total_pnl = unit_pnl * mult * lots
        max_profit = entry_prem * mult * lots
        capture_pct = (unit_pnl / entry_prem * 100.0) if entry_prem > 0 else 0.0
        r_mult = (unit_pnl / entry_prem) if entry_prem > 0 else 0.0
        otm_pct = ((spot - strike) / spot * 100.0) if spot > 0 else 0.0
        daily_theta_total = cur_theta * mult * lots

        # Roll Down & Out plan + Wheel Covered Call plan
        roll_plan = solve_roll_down_and_out(
            inst=inst,
            spot=spot,
            current_strike=strike,
            current_put_price=cur_prem,
            atm_iv=atm_iv,
            rem_dte=rem_dte,
            add_days=30,
        )
        wheel_plan = build_wheel_covered_call(
            inst=inst,
            spot=spot,
            assigned_strike=strike,
            put_premium=entry_prem,
            atm_iv=atm_iv,
            dte=30,
            step=step,
        )

        # Action Signal Decision Tree
        if strat == "WHEEL_COVERED_CALL":
            signal_code = "WHEEL_CALL"
            signal_label = "🟣 车轮备兑Call收租"
            signal_tone = "cyan"
            wheel_call_count += 1
            action_detail = (
                f"已按 {cur}{strike:g} 接货（净成本 {cur}{wheel_plan['initialCostBasis']:g}），"
                f"建议卖出30天 {cur}{wheel_plan['callStrike']:g} 备兑Call（Δ={wheel_plan['callDelta']:.2f}），"
                f"再收权利金 +{cur}{wheel_plan['contractCallPremium'] * lots:g}（年化 +{wheel_plan['callAnnReturnPct']:.1f}%），"
                f"持仓成本降至 {cur}{wheel_plan['newCostBasis']:g}。"
            )
        elif r_mult <= -2.50:
            signal_code = "HARD_STOP"
            signal_label = "🔴 触及-2.5R硬止损线"
            signal_tone = "bear"
            stop_loss_count += 1
            action_detail = (
                f"当前浮亏达 {r_mult:.2f}R（已击穿 -2.50R 机构硬止损纪律线），"
                f"建议立即平仓截断尾部穿仓风险，或降仓展期至下月 {cur}{roll_plan['newStrike']:g}。"
            )
        elif otm_pct <= 1.2 or abs(cur_delta) >= 0.36 or r_mult <= -0.85:
            signal_code = "ROLL_DEFENSE"
            signal_label = "🟡 防御移仓 (Roll Down & Out)"
            signal_tone = "gold"
            roll_defense_count += 1
            roll_credit_str = (
                f"净收权利金 +{cur}{abs(roll_plan['contractNetRollCredit']) * lots:g}"
                if roll_plan["isNetCredit"]
                else f"微付净成本 -{cur}{abs(roll_plan['contractNetRollCredit']) * lots:g}"
            )
            action_detail = (
                f"现价逼近行权价（安全垫仅剩 {otm_pct:.1f}%，Delta {cur_delta:.2f}）。"
                f"建议平当前仓并向下展期至 {roll_plan['newDte']}天 {cur}{roll_plan['newStrike']:g} Put（下移 {roll_plan['strikeDropPct']:.1f}%），"
                f"可实现【{roll_credit_str}】，新安全垫扩至 {roll_plan['newOtmPct']:.1f}%！"
            )
        elif capture_pct >= 65.0 or (capture_pct >= 50.0 and rem_dte >= 14):
            signal_code = "TAKE_PROFIT"
            signal_label = "🟢 止盈落袋 (已赚65%+)"
            signal_tone = "bull"
            take_profit_count += 1
            action_detail = (
                f"权利金已衰减 {capture_pct:.1f}%（浮盈 +{cur}{total_pnl:.0f}），剩余 {rem_dte}天仅剩残余价值 {cur}{cur_prem:g}。"
                f"建议立即买平止盈，释放 {cur}{margin_req:.0f} 保证金换仓至新甜点标的！"
            )
        else:
            signal_code = "HOLD_THETA"
            signal_label = "🔵 安心持有收Theta"
            signal_tone = "neutral"
            action_detail = (
                f"虚值安全垫 {otm_pct:.1f}% 稳固（Delta {cur_delta:.2f}），"
                f"每日躺赚时间价值 +{cur}{daily_theta_total:.1f}/天；达到 65%~70% 衰减时自动提示止盈。"
            )

        cny_mult = fx_rate if cur == "$" else (fx_rate * 0.01 if cur == "¢" else 1.0)
        total_theta_cny += daily_theta_total * cny_mult
        total_pnl_cny += total_pnl * cny_mult
        total_margin_cny += margin_req * cny_mult

        evaluated.append({
            **p,
            "currency": cur,
            "multiplier": mult,
            "spot": round(spot, dp),
            "remDte": rem_dte,
            "currentPremium": round(cur_prem, max(dp, 2)),
            "unrealizedPnl": round(total_pnl, 1),
            "maxProfit": round(max_profit, 1),
            "capturePct": round(capture_pct, 1),
            "rMultiple": round(r_mult, 2),
            "otmPct": round(otm_pct, 2),
            "currentDelta": round(cur_delta, 2),
            "dailyThetaTotal": round(daily_theta_total, 1),
            "marginReq": round(margin_req, 0),
            "signalCode": signal_code,
            "signalLabel": signal_label,
            "signalTone": signal_tone,
            "actionDetail": action_detail,
            "rollPlan": roll_plan,
            "wheelPlan": wheel_plan,
        })

    return {
        "positions": evaluated,
        "summary": {
            "totalPositions": len(evaluated),
            "takeProfitCount": take_profit_count,
            "rollDefenseCount": roll_defense_count,
            "stopLossCount": stop_loss_count,
            "wheelCallCount": wheel_call_count,
            "totalDailyThetaCny": round(total_theta_cny, 0),
            "totalUnrealizedPnlCny": round(total_pnl_cny, 0),
            "totalMarginCny": round(total_margin_cny, 0),
        },
        "macroShield": get_macro_event_shield(target_dte=target_dte),
        "updatedAt": now_bj(),
    }


# ---------------------------------------------------------------------------
# 3. Daily/Weekly Quantitative Briefing & Webhook Push (钉钉/飞书/企微推送)
# ---------------------------------------------------------------------------
def generate_daily_briefing(target_dte: int = 30) -> Dict[str, Any]:
    """
    Generate a structured Markdown / WeChat / Feishu / DingTalk ready daily report
    combining Macro Vol Regime, Macro Event Shield, Top 85+ Sweet-Spot Picks, and Position Alerts.
    """
    recs = get_weekly_recommendations(target_dte=target_dte, force=False)
    tracker = get_portfolio_tracker(target_dte=target_dte)
    wc = recs.get("weekContext") or {}
    mr = recs.get("macroRegime") or {}
    shield = tracker.get("macroShield") or {}

    # Top sweet-spot picks across markets
    all_rows = recs.get("all") or []
    sweet_spots = [
        r for r in all_rows
        if r.get("putScore", 0) >= 82.0 and r.get("trendRegime") not in ("破位急跌飞刀", "空头阴跌通道")
    ][:6]

    lines: List[str] = [
        f"📊 【卖Put量化实战日报 · {wc.get('weekLabel', '')}】 ({now_bj()[:16]})",
        f"🌐 波动率环境：VIX {mr.get('vix', '--')} | VXN {mr.get('vxn', '--')} | OVX {mr.get('ovx', '--')} | {mr.get('regimeLabel', '')}",
        "",
        "🏆 【一、今日高分卖Put甜点精选 (裸卖Put & 牛市价差配对)】",
    ]
    for i, r in enumerate(sweet_spots, 1):
        t = r.get("recommendedTier") or {}
        sp = t.get("bullPutSpread") or {}
        cur = r.get("currency", "")
        lines.append(
            f"{i}. {r['name']}({r['symbol']}) [{r['putScore']:.1f}分·{r.get('trendRegime','')}]："
            f"现价 {cur}{r['price']:g} → 卖 {cur}{t.get('strike',0):g} Put (安全垫 {t.get('otmPct',0):.1f}% / 胜率 {t.get('popPct',0):.1f}%)；"
            f"或配对买 {cur}{sp.get('longStrike',0):g} 保护腿构建价差 (省保证金 {sp.get('marginSavedPct',0):.0f}% / 价差年化 {sp.get('annReturnSpreadPct',0):.1f}%)"
        )

    lines.append("")
    lines.append("📡 【二、持仓动态雷达 (止盈 / 移仓 / 备兑Call / 硬止损)】")
    pos_list = tracker.get("positions") or []
    action_pos = [p for p in pos_list if p.get("signalCode") != "HOLD_THETA"] or pos_list[:3]
    for p in action_pos:
        cur = p.get("currency", "")
        lines.append(
            f"• {p['signalLabel']} | {p['name']}({p['symbol']}) K={cur}{p['strike']:g}："
            f"浮盈亏 {cur}{p['unrealizedPnl']:+.0f} ({p['capturePct']:+.1f}%) → {p['actionDetail']}"
        )

    lines.append("")
    lines.append("🛡️ 【三、近期宏观事件与长假提保日历护盾】")
    for ev in (shield.get("events") or [])[:4]:
        flag = "🔴" if ev["riskLevel"] == "HIGH" else "🟡"
        lines.append(f"{flag} {ev['monthDay']} ({ev['daysText']}) {ev['title']} [{ev['markets']}]")

    text_report = "\n".join(lines)
    return {
        "title": f"卖Put量化实战日报 ({wc.get('weekLabel', '')})",
        "text": text_report,
        "sweetSpotCount": len(sweet_spots),
        "actionSignalCount": len([p for p in pos_list if p.get("signalCode") != "HOLD_THETA"]),
        "updatedAt": now_bj(),
    }


def send_webhook_alert(webhook_url: str, target_dte: int = 30) -> Dict[str, Any]:
    """
    Send the Daily Briefing & Position Action Alerts to a user-provided Webhook URL.
    Auto-detects Feishu (Lark), DingTalk, Enterprise WeChat (WeCom), Bark, or generic JSON webhook.
    """
    briefing = generate_daily_briefing(target_dte=target_dte)
    url = (webhook_url or "").strip()
    if not url:
        return {"ok": False, "msg": "请先输入钉钉 / 飞书 / 企业微信 Webhook 地址", "briefing": briefing}

    text = briefing["text"]
    if "feishu.cn" in url or "larksuite.com" in url:
        payload = {"msg_type": "text", "content": {"text": text}}
    elif "dingtalk.com" in url:
        payload = {"msgtype": "text", "text": {"content": text}}
    elif "weixin.qq.com" in url:
        payload = {"msgtype": "text", "text": {"content": text}}
    else:
        payload = {"title": briefing["title"], "text": text, "content": text}

    try:
        resp = _SESSION.post(url, json=payload, timeout=7.0)
        return {
            "ok": resp.status_code < 400,
            "statusCode": resp.status_code,
            "msg": f"推送成功 (HTTP {resp.status_code})" if resp.status_code < 400 else f"推送返回 HTTP {resp.status_code}",
            "briefing": briefing,
        }
    except Exception as exc:
        return {"ok": False, "msg": f"Webhook 请求异常: {exc}", "briefing": briefing}
