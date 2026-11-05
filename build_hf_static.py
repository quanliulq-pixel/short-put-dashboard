# -*- coding: utf-8 -*-
"""
Build a 100% Full-Featured Static Version (`huggingface_static/index.html`) for GitHub Pages & Hugging Face Static Spaces.
Includes:
- Complete Desktop + iPhone UI (identical to the Flask version)
- All 79 varieties' weekly Short Put + Direct Stock/Futures Buying/Selling recommendations
- 1-year daily K-line bars + MA20/MA60/Bollinger Bands
- Client-side Black-Scholes-Merton & Black-76 option pricing engine + Bull Put Spread + Direct Underlying PnL curves
- Full Portfolio Tracker + 45-Day Macro Event & Holiday Shield + Interactive Add/Remove/Reset via localStorage
- Full Daily Briefing & Webhook Push + 52/104-Week Historical Empirical Backtest & Stress Testing
"""
from __future__ import annotations

import json
import os
import re

from backtest_engine import get_historical_review, run_portfolio_stress_test
from data_engine import ensure_all_bars_loaded, fetch_live_option_chain_sample, get_instrument_bars
from portfolio_engine import generate_daily_briefing, get_portfolio_tracker, remove_portfolio_position
from recommender import _std, get_weekly_recommendations
from universe import ALL_INSTRUMENTS


def build_static_bundle() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(base_dir, "huggingface_static")
    os.makedirs(out_dir, exist_ok=True)

    force = os.environ.get("FORCE_REFRESH", "0") == "1"
    print(f"1. Computing weekly Short Put + Direct Stock/Futures recommendations (30 DTE base, force={force})...")
    rec_30 = get_weekly_recommendations(target_dte=30, force=force)

    print("2. Packing 1-year K-line & technical bands for all 79 varieties...")
    ensure_all_bars_loaded(force=False)
    klines_bundle = {}
    for inst in ALL_INSTRUMENTS:
        iid = inst["id"]
        bars = get_instrument_bars(iid, force=False) or []
        if not bars:
            continue
        dp = int(inst.get("dp", 2))
        kline_bars = bars[-130:]  # 130 trading days (~6 months) for crisp chart + fast static load
        closes = [b["c"] for b in kline_bars]
        all_closes = [b["c"] for b in bars]
        offset = len(all_closes) - len(kline_bars)

        ma20_arr = []
        ma60_arr = []
        boll_up_arr = []
        boll_low_arr = []
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

        klines_bundle[iid] = {
            "bars": kline_bars,
            "ma20": ma20_arr,
            "ma60": ma60_arr,
            "bollUp": boll_up_arr,
            "bollLow": boll_low_arr,
        }

    print("3. Pre-fetching live option chains for CFFEX Index Options (MO / IO / HO)...")
    chains_bundle = {}
    for iid in ["CN_FUT:IM0", "CN_FUT:IF0", "CN_FUT:IH0"]:
        try:
            ch = fetch_live_option_chain_sample(iid, target_dte=30)
            if ch and ch.get("available"):
                chains_bundle[iid] = ch
        except Exception:
            pass

    print("4. Packing Portfolio Tracker, 45-Day Macro Event Shield & Daily Briefing...")
    # Ensure default 6 institutional demo positions are seeded cleanly
    portfolio_bundle = remove_portfolio_position("", reset_default=True)
    if "tracker" in portfolio_bundle and isinstance(portfolio_bundle["tracker"], dict):
        portfolio_bundle = portfolio_bundle["tracker"]
    briefing_bundle = generate_daily_briefing(target_dte=30)

    print("5. Packing Historical Empirical Backtest (12 / 26 / 52 / 104 weeks) & Stress Testing...")
    bt_all = {}
    for c_num in (12, 26, 52, 104):
        bt_res = get_historical_review(hold_trading_days=20, num_cohorts=c_num, force=False)
        bt_all[str(c_num)] = {
            "numCohorts": bt_res.get("numCohorts", c_num),
            "holdTradingDays": bt_res.get("holdTradingDays", 20),
            "tierStats": bt_res.get("tierStats", {}),
            "marketStats": bt_res.get("marketStats", {}),
            "scoreBuckets": bt_res.get("scoreBuckets", []),
            "stopLossComparison": bt_res.get("stopLossComparison", {}),
            "cohorts": bt_res.get("cohorts", []),
            "records": bt_res.get("records", [])[:360] if c_num == 104 else [],
        }
    stress_bundle = run_portfolio_stress_test(target_dte=30, force=False)

    inst_meta = {
        inst["id"]: {
            "name": inst["name"],
            "symbol": inst["symbol"],
            "market": inst["market"],
            "currency": inst.get("currency", "$"),
            "dp": int(inst.get("dp", 2)),
            "multiplier": float(inst.get("multiplier", 100)),
            "margin_rate": float(inst.get("margin_rate", 0.15)),
            "iv_skew": float(inst.get("iv_skew", 0.12)),
            "strike_step": float(inst.get("strike_step", 1.0)),
        }
        for inst in ALL_INSTRUMENTS
    }

    print("3b. Loading Henry Hub NG nine-factor dashboard payload...")
    try:
        from ng_terminal.load_payload import load_ng_payload
        ng_payload = load_ng_payload(force=os.environ.get("FORCE_REFRESH", "0") == "1")
    except Exception as exc:
        print(f"NG payload fallback empty: {exc}")
        ng_payload = {"advice": {"bias_cn": "—", "action": "NG 暂不可用", "summary": ""}, "factors": [], "price": {}, "errors": [str(exc)]}

    with open(os.path.join(base_dir, "templates", "index.html"), "r", encoding="utf-8") as f:
        html_tpl = f.read()
    with open(os.path.join(base_dir, "static", "style.css"), "r", encoding="utf-8") as f:
        css_txt = f.read()
    with open(os.path.join(base_dir, "static", "app.js"), "r", encoding="utf-8") as f:
        js_txt = f.read()

    # Client-side API shim that intercepts fetch('/api/...') and computes everything locally in browser!
    static_shim_js = f"""
<script>
window.__STATIC_REC_30__ = {json.dumps(rec_30, ensure_ascii=False, separators=(",", ":"))};
window.__STATIC_KLINES__ = {json.dumps(klines_bundle, ensure_ascii=False, separators=(",", ":"))};
window.__STATIC_CHAINS__ = {json.dumps(chains_bundle, ensure_ascii=False, separators=(",", ":"))};
window.__STATIC_META__ = {json.dumps(inst_meta, ensure_ascii=False, separators=(",", ":"))};
window.__STATIC_PORTFOLIO_DEFAULT__ = {json.dumps(portfolio_bundle, ensure_ascii=False, separators=(",", ":"))};
window.__STATIC_BRIEFING__ = {json.dumps(briefing_bundle, ensure_ascii=False, separators=(",", ":"))};
window.__STATIC_BT_ALL__ = {json.dumps(bt_all, ensure_ascii=False, separators=(",", ":"))};
window.__STATIC_STRESS__ = {json.dumps(stress_bundle, ensure_ascii=False, separators=(",", ":"))};
window.__STATIC_NG__ = {json.dumps(ng_payload, ensure_ascii=False, separators=(",", ":"), default=str)};

(function() {{
  const PF_STORAGE_KEY = "short_put_static_pf_v4";

  function normCdf(x) {{
    const t = 1 / (1 + 0.2316419 * Math.abs(x));
    const d = 0.3989422804014327 * Math.exp(-x * x / 2);
    const p = d * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + 1.330274429 * t))));
    return x >= 0 ? 1 - p : p;
  }}
  function normPdf(x) {{
    return 0.3989422804014327 * Math.exp(-0.5 * x * x);
  }}
  function skewIv(atmIv, spot, strike, skewCoeff) {{
    if (spot <= 0 || strike <= 0) return atmIv;
    const otmRatio = Math.max(0, (spot - strike) / spot);
    const mult = 1.0 + skewCoeff * (otmRatio / 0.10) + 0.35 * skewCoeff * Math.pow(otmRatio / 0.10, 2);
    return Math.min(atmIv * mult, atmIv * 1.85);
  }}
  function pricePutAndGreeks(spot, strike, dte, iv, r, isFut) {{
    const T = Math.max(dte, 1) / 365.0;
    const sigma = Math.max(iv, 0.05);
    const sqrtT = Math.sqrt(T);
    const b = isFut ? 0.0 : r;
    const dfR = Math.exp(-r * T);
    const dfB = Math.exp((b - r) * T);
    const d1 = (Math.log(spot / strike) + (b + 0.5 * sigma * sigma) * T) / (sigma * sqrtT);
    const d2 = d1 - sigma * sqrtT;
    const nd1Neg = normCdf(-d1);
    const nd2Neg = normCdf(-d2);
    const pdfD1 = normPdf(d1);
    const putPrice = Math.max(strike * dfR * nd2Neg - spot * dfB * nd1Neg, spot * 0.0002);
    const delta = -dfB * nd1Neg;
    const gamma = (dfB * pdfD1) / (spot * sigma * sqrtT);
    const vega = spot * dfB * pdfD1 * sqrtT / 100.0;
    const term1 = -(spot * dfB * pdfD1 * sigma) / (2.0 * sqrtT);
    const term2 = r * strike * dfR * nd2Neg;
    const term3 = (b - r) * spot * dfB * nd1Neg;
    const thetaDaily = (term1 + term2 - term3) / 365.0;
    const breakeven = Math.max(0.0001, strike - putPrice);
    const d2Be = (Math.log(spot / breakeven) + (b - 0.5 * sigma * sigma) * T) / (sigma * sqrtT);
    const popPct = Math.min(99.2, Math.max(5.0, normCdf(d2Be) * 100.0));
    const probOtmPct = Math.min(99.0, Math.max(5.0, normCdf(d2) * 100.0));
    const probTouchPct = Math.min(98.0, (1.0 - probOtmPct / 100.0) * 195.0);
    return {{ premium: putPrice, breakeven, delta, gamma, theta_daily: thetaDaily, vega, pop_pct: popPct, prob_otm_pct: probOtmPct, prob_touch_pct: probTouchPct }};
  }}
  function buildPayoff(meta, spot, strike, dte, iv, premium, spreadInfo) {{
    const isFut = meta.market === "us_fut" || meta.market === "cn_fut";
    const r = meta.market === "cn_fut" ? 0.020 : 0.042;
    const dp = meta.dp;
    const mult = meta.multiplier;
    const lowP = Math.min(spot * 0.78, strike * 0.86);
    const highP = Math.max(spot * 1.15, strike * 1.18);
    const nPts = 65;
    const stepP = (highP - lowP) / (nPts - 1);
    const midDte = Math.max(1, Math.floor(dte / 2));
    const prices = [], expPnl = [], midPnl = [], spreadExpPnl = [], underlyingLongPnl = [], underlyingShortPnl = [];
    const hasSpread = spreadInfo && spreadInfo.longStrike > 0;
    const longK = hasSpread ? spreadInfo.longStrike : Math.max(meta.strike_step || 1, strike * 0.92);
    const netCred = hasSpread ? spreadInfo.netCredit : premium * 0.72;
    for (let i = 0; i < nPts; i++) {{
      const p = lowP + i * stepP;
      prices.push(Number(p.toFixed(dp)));
      const intrinsic = Math.max(0, strike - p);
      expPnl.push(Number(((premium - intrinsic) * mult).toFixed(1)));
      const midRes = pricePutAndGreeks(p, strike, midDte, iv, r, isFut);
      midPnl.push(Number(((premium - midRes.premium) * mult).toFixed(1)));
      const spIntrinsic = Math.max(0, strike - p) - Math.max(0, longK - p);
      spreadExpPnl.push(Number(((netCred - spIntrinsic) * mult).toFixed(1)));
      underlyingLongPnl.push(Number(((p - spot) * mult).toFixed(1)));
      underlyingShortPnl.push(Number(((spot - p) * mult).toFixed(1)));
    }}
    return {{
      prices, expPnl, midPnl, spreadExpPnl, underlyingLongPnl, underlyingShortPnl,
      midDte,
      spreadInfo: spreadInfo || {{ longStrike: Number(longK.toFixed(dp)), netCredit: Number(netCred.toFixed(dp)) }},
      upsideCrossoverPx: Number((spot + premium).toFixed(dp)),
      breakeven: Number((strike - premium).toFixed(dp)),
      maxProfit: Number((premium * mult).toFixed(1)),
      spot: Number(spot.toFixed(dp)),
      strike: Number(strike.toFixed(dp))
    }};
  }}
  function recalcTierForDte(row, tierObj, dte) {{
    if (dte === 30) return tierObj;
    const meta = window.__STATIC_META__[row.id] || {{ market: row.market, dp: 2, multiplier: 100, margin_rate: 0.15, iv_skew: 0.12 }};
    const isFut = meta.market === "us_fut" || meta.market === "cn_fut";
    const r = meta.market === "cn_fut" ? 0.020 : 0.042;
    const spot = row.price;
    const k = tierObj.strike;
    const strikeIv = tierObj.ivPct / 100.0;
    const res = pricePutAndGreeks(spot, k, dte, strikeIv, r, isFut);
    const prem = res.premium;
    const be = res.breakeven;
    const otmAmt = Math.max(0, spot - k);
    const mult = meta.multiplier;
    const contractPrem = prem * mult;
    const effMargin = meta.margin_rate * 1.25;
    const unitMargin = prem + Math.max(effMargin * spot - 0.5 * otmAmt, 0.70 * effMargin * spot);
    const marginReq = Math.max(unitMargin * mult, k * mult * 0.08);
    const rocMargin = marginReq > 0 ? (contractPrem / marginReq) * 100.0 : 0;
    const annMargin = rocMargin * (365.0 / Math.max(dte, 1));
    const rocCash = k > 0 ? (prem / k) * 100.0 : 0;
    const annCash = rocCash * (365.0 / Math.max(dte, 1));
    return Object.assign({{}}, tierObj, {{
      premium: Number(prem.toFixed(Math.max(meta.dp, 2))),
      contractPremium: Number(contractPrem.toFixed(contractPrem >= 100 ? 0 : 2)),
      breakeven: Number(be.toFixed(meta.dp)),
      breakevenBufferPct: Number((((spot - be) / spot) * 100.0).toFixed(2)),
      delta: Number(res.delta.toFixed(3)),
      gamma: Number(res.gamma.toFixed(5)),
      thetaDaily: Number(res.theta_daily.toFixed(Math.max(meta.dp, 3))),
      contractThetaDaily: Number((res.theta_daily * mult).toFixed(1)),
      vega: Number(res.vega.toFixed(3)),
      popPct: Number(res.pop_pct.toFixed(1)),
      probOtmPct: Number(res.prob_otm_pct.toFixed(1)),
      probTouchPct: Number(res.prob_touch_pct.toFixed(1)),
      marginReq: Math.round(marginReq),
      rocMarginPct: Number(rocMargin.toFixed(2)),
      annReturnMarginPct: Number(annMargin.toFixed(1)),
      rocCashPct: Number(rocCash.toFixed(2)),
      annReturnCashPct: Number(annCash.toFixed(1))
    }});
  }}
  function getRecsForDte(dte) {{
    const base = JSON.parse(JSON.stringify(window.__STATIC_REC_30__));
    base.weekContext.targetDte = dte;
    if (dte !== 30) {{
      const updateRow = (r) => {{
        for (const tk of ["conservative", "balanced", "aggressive"]) {{
          if (r.tiers && r.tiers[tk]) r.tiers[tk] = recalcTierForDte(r, r.tiers[tk], dte);
        }}
        r.recommendedTier = r.tiers[r.recommendedTierKey || "balanced"];
      }};
      (base.all || []).forEach(updateRow);
      (base.cnIndexOptions || []).forEach(updateRow);
      Object.values(base.topPicks || {{}}).forEach(arr => (arr || []).forEach(updateRow));
    }}
    return base;
  }}

  function recomputePortfolioSummary(pfObj) {{
    const positions = pfObj.positions || [];
    let tpCnt = 0, rollCnt = 0, wheelCnt = 0, stopCnt = 0;
    let totalThetaCny = 0, totalPnlCny = 0, totalMarginCny = 0;
    positions.forEach(p => {{
      const fx = p.currency === "$" ? 7.22 : 1.0;
      const sig = p.signalCode || p.actionCode || "HOLD_THETA";
      if (sig === "TAKE_PROFIT") tpCnt++;
      else if (sig === "ROLL_DEFENSE") rollCnt++;
      else if (sig === "WHEEL_CALL") wheelCnt++;
      else if (sig === "HARD_STOP") stopCnt++;
      totalThetaCny += (Number(p.dailyThetaTotal ?? p.liveThetaDaily ?? 0)) * fx;
      totalPnlCny += (Number(p.unrealizedPnl || 0)) * fx;
      totalMarginCny += (Number(p.marginUsed || 0)) * fx;
    }});
    pfObj.summary = {{
      totalPositions: positions.length,
      positionCount: positions.length,
      takeProfitCount: tpCnt,
      rollDefenseCount: rollCnt,
      wheelCallCount: wheelCnt,
      stopLossCount: stopCnt,
      hardStopCount: stopCnt,
      totalDailyThetaCny: Math.round(totalThetaCny),
      totalUnrealizedPnlCny: Math.round(totalPnlCny),
      totalMarginCny: Math.round(totalMarginCny)
    }};
    return pfObj;
  }}

  function getStaticPortfolio() {{
    try {{
      const raw = localStorage.getItem(PF_STORAGE_KEY);
      if (raw) {{
        const parsed = JSON.parse(raw);
        if (parsed && Array.isArray(parsed.positions)) {{
          parsed.macroShield = window.__STATIC_PORTFOLIO_DEFAULT__.macroShield;
          return recomputePortfolioSummary(parsed);
        }}
      }}
    }} catch (_) {{}}
    return JSON.parse(JSON.stringify(window.__STATIC_PORTFOLIO_DEFAULT__));
  }}

  function saveStaticPortfolio(pfObj) {{
    try {{
      localStorage.setItem(PF_STORAGE_KEY, JSON.stringify(pfObj));
    }} catch (_) {{}}
  }}

  function getStaticBacktest(cohortsNum) {{
    const key = String(cohortsNum || 52);
    const bt104 = window.__STATIC_BT_ALL__["104"] || {{}};
    const target = JSON.parse(JSON.stringify(window.__STATIC_BT_ALL__[key] || window.__STATIC_BT_ALL__["52"] || bt104));
    const allowedLabels = new Set((target.cohorts || []).map(c => c.cohortLabel));
    target.records = (bt104.records || []).filter(r => allowedLabels.has(r.cohortLabel));
    return target;
  }}

  const origFetch = window.fetch.bind(window);
  window.fetch = async function(input, init) {{
    const urlStr = typeof input === "string" ? input : (input && input.url) || "";
    if (urlStr.startsWith("/api/")) {{
      const u = new URL(urlStr, window.location.origin);
      const path = u.pathname;
      const sp = u.searchParams;
      if (path === "/api/recommendations") {{
        const dte = parseInt(sp.get("dte") || "30", 10) || 30;
        return new Response(JSON.stringify(getRecsForDte(dte)), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
      }}
      if (path === "/api/detail") {{
        const id = sp.get("id") || "CN_FUT:IM0";
        const dte = parseInt(sp.get("dte") || "30", 10) || 30;
        const tierArg = sp.get("tier");
        const recs = getRecsForDte(dte);
        const analysis = (recs.all || []).find(r => r.id === id) || recs.all[0];
        const selKey = (tierArg && ["conservative", "balanced", "aggressive"].includes(tierArg)) ? tierArg : (analysis.recommendedTierKey || "balanced");
        const selTier = analysis.tiers[selKey];
        const meta = window.__STATIC_META__[analysis.id] || {{ market: analysis.market, dp: 2, multiplier: 100, margin_rate: 0.15, iv_skew: 0.12, strike_step: 1 }};
        const payoff = buildPayoff(meta, analysis.price, selTier.strike, dte, selTier.ivPct / 100.0, selTier.premium, selTier.bullPutSpread);
        const kline = window.__STATIC_KLINES__[analysis.id] || {{ bars: [], ma20: [], ma60: [], bollUp: [], bollLow: [] }};
        return new Response(JSON.stringify({{
          analysis,
          weekContext: recs.weekContext,
          kline,
          selectedTierKey: selKey,
          payoff,
          updatedAt: recs.updatedAt
        }}), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
      }}
      if (path === "/api/simulate") {{
        const id = sp.get("id") || "CN_FUT:IM0";
        const spot = parseFloat(sp.get("spot") || "0");
        const strike = parseFloat(sp.get("strike") || "0");
        const dte = parseInt(sp.get("dte") || "30", 10) || 30;
        const ivPct = parseFloat(sp.get("iv") || "25");
        const lots = Math.max(1, parseInt(sp.get("lots") || "1", 10) || 1);
        const meta = window.__STATIC_META__[id] || {{ market: "cn_fut", dp: 2, multiplier: 100, margin_rate: 0.15, iv_skew: 0.12, strike_step: 1 }};
        const isFut = meta.market === "us_fut" || meta.market === "cn_fut";
        const r = meta.market === "cn_fut" ? 0.020 : 0.042;
        const strikeIv = skewIv(ivPct / 100.0, spot, strike, meta.iv_skew);
        const res = pricePutAndGreeks(spot, strike, dte, strikeIv, r, isFut);
        const prem = res.premium;
        const be = res.breakeven;
        const otmAmt = Math.max(0, spot - strike);
        const otmPct = (otmAmt / spot) * 100.0;
        const effMargin = meta.margin_rate * 1.25;
        const unitMargin = prem + Math.max(effMargin * spot - 0.5 * otmAmt, 0.70 * effMargin * spot);
        const marginReq = Math.max(unitMargin * meta.multiplier, strike * meta.multiplier * 0.08) * lots;
        const cashReq = strike * meta.multiplier * lots;
        const totalPrem = prem * meta.multiplier * lots;
        const totalTheta = res.theta_daily * meta.multiplier * lots;
        const rocMargin = marginReq > 0 ? (totalPrem / marginReq) * 100.0 : 0;
        const annMargin = rocMargin * (365.0 / Math.max(dte, 1));
        const rocCash = strike > 0 ? (prem / strike) * 100.0 : 0;
        const annCash = rocCash * (365.0 / Math.max(dte, 1));
        const payoff = buildPayoff(meta, spot, strike, dte, strikeIv, prem, null);
        if (lots !== 1) {{
          payoff.expPnl = payoff.expPnl.map(x => Number((x * lots).toFixed(1)));
          payoff.midPnl = payoff.midPnl.map(x => Number((x * lots).toFixed(1)));
          payoff.spreadExpPnl = payoff.spreadExpPnl.map(x => Number((x * lots).toFixed(1)));
          payoff.underlyingLongPnl = payoff.underlyingLongPnl.map(x => Number((x * lots).toFixed(1)));
          payoff.underlyingShortPnl = payoff.underlyingShortPnl.map(x => Number((x * lots).toFixed(1)));
          payoff.maxProfit = Number((payoff.maxProfit * lots).toFixed(1));
        }}
        return new Response(JSON.stringify({{
          strike: Number(strike.toFixed(meta.dp)),
          lots, dte,
          otmPct: Number(otmPct.toFixed(2)),
          ivPct: Number((strikeIv * 100.0).toFixed(1)),
          premium: Number(prem.toFixed(Math.max(meta.dp, 2))),
          totalPremium: Number(totalPrem.toFixed(1)),
          breakeven: Number(be.toFixed(meta.dp)),
          breakevenBufferPct: Number((((spot - be) / spot) * 100.0).toFixed(2)),
          delta: Number(res.delta.toFixed(3)),
          thetaDailyTotal: Number(totalTheta.toFixed(1)),
          popPct: Number(res.pop_pct.toFixed(1)),
          marginReq: Math.round(marginReq),
          cashSecuredReq: Math.round(cashReq),
          annReturnMarginPct: Number(annMargin.toFixed(1)),
          annReturnCashPct: Number(annCash.toFixed(1)),
          payoff
        }}), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
      }}
      if (path === "/api/portfolio") {{
        return new Response(JSON.stringify(getStaticPortfolio()), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
      }}
      if (path === "/api/portfolio/add") {{
        const body = init && init.body ? JSON.parse(init.body) : {{}};
        const pf = getStaticPortfolio();
        const iid = body.instId || "CN_FUT:IM0";
        const row = (window.__STATIC_REC_30__.all || []).find(r => r.id === iid) || window.__STATIC_REC_30__.all[0];
        const meta = window.__STATIC_META__[iid] || {{ name: row.name, symbol: row.symbol, market: row.market, currency: row.currency, dp: 2, multiplier: 100, margin_rate: 0.15 }};
        const strat = body.strategyType || "SHORT_PUT";
        const isDirect = ["LONG_STOCK", "LONG_FUTURES", "SHORT_FUTURES"].includes(strat);
        const spot = Number(body.entrySpot || row.price);
        const strike = Number(body.strike || row.recommendedTier.strike);
        const longStrike = Number(body.longStrike || 0);
        const lots = Math.max(1, Number(body.lots || 1));
        const dte = Number(body.dte || 30);
        const entryPrem = Number(body.entryPremium || row.recommendedTier.premium);
        const nowStr = new Date().toISOString().slice(0, 10);
        const expDate = new Date(Date.now() + dte * 86400000).toISOString().slice(0, 10);
        const newPos = {{
          posId: "POS-" + Math.random().toString(36).slice(2, 8).toUpperCase(),
          instId: iid,
          symbol: meta.symbol,
          name: meta.name,
          market: meta.market,
          currency: meta.currency || row.currency || "$",
          strategyType: strat,
          lots: lots,
          openDate: nowStr,
          expiryDate: expDate,
          remDte: dte,
          entrySpot: spot,
          spot: spot,
          strike: strike,
          longStrike: longStrike,
          otmPct: isDirect ? Number((Math.abs(spot - strike) / spot * 100).toFixed(2)) : Number(((spot - strike) / spot * 100).toFixed(2)),
          entryPremium: entryPrem,
          currentPremium: entryPrem,
          capturePct: 0.0,
          rMultiple: 0.0,
          unrealizedPnl: 0.0,
          currentDelta: isDirect ? (strat === "SHORT_FUTURES" ? -1.0 : 1.0) : (row.recommendedTier.delta || -0.22),
          dailyThetaTotal: isDirect ? 0.0 : Number(((row.recommendedTier.contractThetaDaily || 15) * lots).toFixed(1)),
          marginUsed: Math.round((row.recommendedTier.marginReq || spot * meta.multiplier * 0.15) * lots),
          signalCode: "HOLD_THETA",
          signalLabel: isDirect ? "🟢 趋势持仓跟踪中" : "🟢 持有收租 (Theta衰减中)",
          signalTone: "neutral",
          actionDetail: isDirect
            ? `已建仓${{strat === "SHORT_FUTURES" ? "做空" : "做多"}}头寸：现价 ${{meta.currency}}${{spot}}，硬止损位 ${{meta.currency}}${{strike}}，波段目标位 ${{meta.currency}}${{longStrike}}。`
            : `新开仓安全垫充足，每日稳定赚取 Theta 时间价值，静待权利金衰减至 65% 触发止盈。`,
          note: body.note || ""
        }};
        pf.positions.unshift(newPos);
        recomputePortfolioSummary(pf);
        saveStaticPortfolio(pf);
        return new Response(JSON.stringify(pf), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
      }}
      if (path === "/api/portfolio/remove") {{
        const body = init && init.body ? JSON.parse(init.body) : {{}};
        if (body.resetDefault || body.posId === "RESET_DEFAULT") {{
          localStorage.removeItem(PF_STORAGE_KEY);
          return new Response(JSON.stringify(window.__STATIC_PORTFOLIO_DEFAULT__), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
        }}
        const pf = getStaticPortfolio();
        pf.positions = (pf.positions || []).filter(p => p.posId !== body.posId);
        recomputePortfolioSummary(pf);
        saveStaticPortfolio(pf);
        return new Response(JSON.stringify(pf), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
      }}
      if (path === "/api/briefing") {{
        return new Response(JSON.stringify(window.__STATIC_BRIEFING__), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
      }}
      if (path === "/api/webhook-push") {{
        const body = init && init.body ? JSON.parse(init.body) : {{}};
        const wUrl = (body.webhookUrl || "").trim();
        const txt = body.text || window.__STATIC_BRIEFING__.text || "";
        if (!wUrl) {{
          return new Response(JSON.stringify({{ ok: false, msg: "请先输入 Webhook URL" }}), {{ status: 400, headers: {{ "Content-Type": "application/json" }} }});
        }}
        try {{
          const payload = wUrl.includes("feishu") || wUrl.includes("larksuite")
            ? {{ msg_type: "text", content: {{ text: txt }} }}
            : {{ msgtype: "text", text: {{ content: txt }} }};
          await origFetch(wUrl, {{ method: "POST", mode: "no-cors", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify(payload) }});
          return new Response(JSON.stringify({{ ok: true, msg: "已通过浏览器向 Webhook 发送推送请求！" }}), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
        }} catch (e) {{
          return new Response(JSON.stringify({{ ok: false, msg: "浏览器跨域限制，请点击右侧「复制日报文本」粘贴发送" }}), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
        }}
      }}
      if (path === "/api/backtest") {{
        const cohorts = parseInt(sp.get("cohorts") || "52", 10) || 52;
        return new Response(JSON.stringify(getStaticBacktest(cohorts)), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
      }}
      if (path === "/api/stress-test") {{
        return new Response(JSON.stringify(window.__STATIC_STRESS__), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
      }}
      if (path === "/api/option-chain") {{
        const id = sp.get("id") || "";
        const ch = window.__STATIC_CHAINS__[id] || {{ available: false, note: "云端静态版已将场内Black-76/BSM三档期权定价直接集成至上方行权价矩阵中" }};
        return new Response(JSON.stringify(ch), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
      }}
      if (path === "/api/mobile-info") {{
        const curUrl = window.location.href.split("#")[0];
        return new Response(JSON.stringify({{
          primaryIp: window.location.hostname,
          primaryUrl: curUrl,
          allUrls: [curUrl],
          port: 443
        }}), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
      }}
    }}
    return origFetch(input, init);
  }};

  document.addEventListener("DOMContentLoaded", () => {{
    const expBtn = document.getElementById("link-export-mobile");
    if (expBtn) {{
      expBtn.addEventListener("click", (e) => {{
        if (window.location.hostname.includes("github.io") || window.location.protocol === "file:") {{
          e.preventDefault();
          const blob = new Blob([document.documentElement.outerHTML], {{ type: "text/html;charset=utf-8" }});
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "ShortPut_iPhone_Weekly.html";
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
        }}
      }});
    }}
  }});
}})();
</script>
"""

    # Inline CSS and JS into html_tpl
    final_html = re.sub(
        r'<link rel="stylesheet" href="/static/style\.css[^"]*"\s*/>',
        lambda _: f"<style>\n{css_txt}\n</style>",
        html_tpl,
    )
    final_html = re.sub(
        r'<script src="/static/app\.js[^"]*"></script>',
        lambda _: f"{static_shim_js}\n<script>\n{js_txt}\n</script>",
        final_html,
    )

    out_file = os.path.join(out_dir, "index.html")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(final_html)

    print(f"Done! Built full-featured GitHub Pages / Static Space file: {out_file} ({os.path.getsize(out_file):,} bytes)")


if __name__ == "__main__":
    build_static_bundle()
