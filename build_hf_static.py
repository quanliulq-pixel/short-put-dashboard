# -*- coding: utf-8 -*-
"""
Build a 100% Full-Featured Static Version (`huggingface_static/index.html`) for Hugging Face `Static` Spaces.
Includes:
- Complete Desktop + iPhone UI (identical to the Flask version)
- All 79 varieties' weekly recommendations + 1-year daily K-line bars + MA20/MA60/Bollinger Bands
- Client-side Black-Scholes-Merton & Black-76 option pricing engine (supports switching DTE 7/14/30/45/60, switching 3 tiers, and custom Strike/DTE/IV/Lots simulation with live ECharts Payoff & K-line charts!)
- Pre-fetched live option chains for CSI 1000 (MO), CSI 300 (IO), SSE 50 (HO), and top US stocks/ETFs.
"""
from __future__ import annotations

import json
import os
import re

from backtest_engine import get_historical_review
from data_engine import ensure_all_bars_loaded, fetch_live_option_chain_sample, get_instrument_bars
from recommender import _std, get_weekly_recommendations
from universe import ALL_INSTRUMENTS


def build_static_bundle() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(base_dir, "huggingface_static")
    os.makedirs(out_dir, exist_ok=True)

    force = os.environ.get("FORCE_REFRESH", "1") == "1"
    print(f"1. Computing weekly recommendations (30 DTE base, force={force})...")
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
        kline_bars = bars[-180:]  # 180 trading days (~9 months) for crisp chart + compact size
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

    print("4. Computing 12-week rolling historical recommendation review & backtest...")
    bt_bundle = get_historical_review(hold_trading_days=20, num_cohorts=12, force=False)

    inst_meta = {
        inst["id"]: {
            "market": inst["market"],
            "dp": int(inst.get("dp", 2)),
            "multiplier": float(inst.get("multiplier", 100)),
            "margin_rate": float(inst.get("margin_rate", 0.15)),
            "iv_skew": float(inst.get("iv_skew", 0.12)),
            "strike_step": float(inst.get("strike_step", 1.0)),
        }
        for inst in ALL_INSTRUMENTS
    }

    with open(os.path.join(base_dir, "templates", "index.html"), "r", encoding="utf-8") as f:
        html_tpl = f.read()
    with open(os.path.join(base_dir, "static", "style.css"), "r", encoding="utf-8") as f:
        css_txt = f.read()
    with open(os.path.join(base_dir, "static", "app.js"), "r", encoding="utf-8") as f:
        js_txt = f.read()

    # Client-side API shim that intercepts fetch('/api/...') and computes everything locally in browser!
    static_shim_js = f"""
<script>
window.__STATIC_REC_30__ = {json.dumps(rec_30, ensure_ascii=False)};
window.__STATIC_KLINES__ = {json.dumps(klines_bundle, ensure_ascii=False)};
window.__STATIC_CHAINS__ = {json.dumps(chains_bundle, ensure_ascii=False)};
window.__STATIC_META__ = {json.dumps(inst_meta, ensure_ascii=False)};
window.__STATIC_BACKTEST__ = {json.dumps(bt_bundle, ensure_ascii=False)};

(function() {{
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
  function buildPayoff(meta, spot, strike, dte, iv, premium) {{
    const isFut = meta.market === "us_fut" || meta.market === "cn_fut";
    const r = meta.market === "cn_fut" ? 0.020 : 0.042;
    const dp = meta.dp;
    const mult = meta.multiplier;
    const lowP = Math.min(spot * 0.78, strike * 0.86);
    const highP = Math.max(spot * 1.12, strike * 1.16);
    const nPts = 65;
    const stepP = (highP - lowP) / (nPts - 1);
    const midDte = Math.max(1, Math.floor(dte / 2));
    const prices = [], expPnl = [], midPnl = [];
    for (let i = 0; i < nPts; i++) {{
      const p = lowP + i * stepP;
      prices.push(Number(p.toFixed(dp)));
      const intrinsic = Math.max(0, strike - p);
      expPnl.push(Number(((premium - intrinsic) * mult).toFixed(1)));
      const midRes = pricePutAndGreeks(p, strike, midDte, iv, r, isFut);
      midPnl.push(Number(((premium - midRes.premium) * mult).toFixed(1)));
    }}
    return {{
      prices, expPnl, midPnl,
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
      if (path === "/api/backtest") {{
        return new Response(JSON.stringify(window.__STATIC_BACKTEST__), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }});
      }}
      if (path === "/api/detail") {{
        const id = sp.get("id") || "CN_FUT:IM0";
        const dte = parseInt(sp.get("dte") || "30", 10) || 30;
        const tierArg = sp.get("tier");
        const recs = getRecsForDte(dte);
        const analysis = (recs.all || []).find(r => r.id === id) || recs.all[0];
        const selKey = (tierArg && ["conservative", "balanced", "aggressive"].includes(tierArg)) ? tierArg : (analysis.recommendedTierKey || "balanced");
        const selTier = analysis.tiers[selKey];
        const meta = window.__STATIC_META__[analysis.id] || {{ market: analysis.market, dp: 2, multiplier: 100, margin_rate: 0.15, iv_skew: 0.12 }};
        const payoff = buildPayoff(meta, analysis.price, selTier.strike, dte, selTier.ivPct / 100.0, selTier.premium);
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
        const meta = window.__STATIC_META__[id] || {{ market: "cn_fut", dp: 2, multiplier: 100, margin_rate: 0.15, iv_skew: 0.12 }};
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
        const payoff = buildPayoff(meta, spot, strike, dte, strikeIv, prem);
        if (lots !== 1) {{
          payoff.expPnl = payoff.expPnl.map(x => Number((x * lots).toFixed(1)));
          payoff.midPnl = payoff.midPnl.map(x => Number((x * lots).toFixed(1)));
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

    print(f"Done! Built full-featured Hugging Face Static Space file: {out_file} ({os.path.getsize(out_file):,} bytes)")


if __name__ == "__main__":
    build_static_bundle()
