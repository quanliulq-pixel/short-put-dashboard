# -*- coding: utf-8 -*-
"""
Weekly Dynamic Short Put Recommendation Local Server (美股 · 美期货 · 中国期货 卖Put周度动态推荐系统)
Port: 5060
"""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import subprocess
import threading
import time

from flask import Flask, Response, jsonify, render_template, request

from backtest_engine import get_historical_review
from data_engine import fetch_live_option_chain_sample
from options_math import build_payoff_curve, price_put_and_greeks, skew_adjusted_iv
from recommender import get_instrument_detail, get_weekly_recommendations
from universe import get_instrument

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

PORT = int(os.environ.get("PORT", 5058))


@app.after_request
def add_no_cache_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/")
def index():
    asset_v = str(int(time.time()))
    return render_template("index.html", asset_v=asset_v)


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "port": PORT, "ts": int(time.time())})


def _detect_wifi_lan_ips():
    """
    Enumerate real LAN/Wi-Fi IPv4 addresses while filtering out:
    - 127.x.x.x (loopback)
    - 198.18.x.x / 198.19.x.x (Clash / Surge TUN virtual adapter)
    - 169.254.x.x (APIPA)
    - 172.16.x.x - 172.31.x.x (WSL / Hyper-V / Docker virtual switches)
    """
    candidates = []
    try:
        out = subprocess.check_output(["ipconfig"], text=True, encoding="gbk", errors="ignore", timeout=3)
        for m in re.finditer(r"IPv4[^\d:\r\n]*[:. ]+(\d+\.\d+\.\d+\.\d+)", out):
            ip = m.group(1)
            if ip not in candidates:
                candidates.append(ip)
    except Exception:
        pass

    try:
        _, _, host_ips = socket.gethostbyname_ex(socket.gethostname())
        for ip in host_ips:
            if ip not in candidates:
                candidates.append(ip)
    except Exception:
        pass

    real_lan = []
    fallback_lan = []
    for ip in candidates:
        parts = [int(x) for x in ip.split(".")]
        if parts[0] == 127 or parts[0] == 169:
            continue
        if parts[0] == 198 and parts[1] in (18, 19):
            # Clash / Shadowrocket / Surge TUN adapter
            continue
        if parts[0] == 172 and 16 <= parts[1] <= 31:
            fallback_lan.append(ip)
            continue
        if parts[0] == 192 and parts[1] == 168:
            real_lan.insert(0, ip)
        elif parts[0] == 10:
            real_lan.append(ip)
        else:
            fallback_lan.append(ip)

    final_ips = real_lan or fallback_lan or ["127.0.0.1"]
    return final_ips


@app.route("/api/mobile-info")
def api_mobile_info():
    ips = _detect_wifi_lan_ips()
    urls = [f"http://{ip}:{PORT}" for ip in ips]
    return jsonify({
        "primaryIp": ips[0],
        "primaryUrl": urls[0],
        "allUrls": urls,
        "port": PORT,
    })


@app.route("/manifest.json")
def pwa_manifest():
    manifest = {
        "name": "每周动态卖Put量化推荐终端",
        "short_name": "卖Put终端",
        "description": "美股 · 美期货 · 中国期货与三大股指期权每周卖Put动态推荐",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#080c14",
        "theme_color": "#080c14",
        "orientation": "portrait-primary",
        "icons": [
            {
                "src": "/static/app-icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable",
            }
        ],
    }
    return Response(json.dumps(manifest, ensure_ascii=False), mimetype="application/manifest+json")


@app.route("/static/app-icon.svg")
def app_icon_svg():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 180">
      <defs>
        <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#0f172a"/>
          <stop offset="100%" stop-color="#1e293b"/>
        </linearGradient>
        <linearGradient id="gd" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#f59e0b"/>
          <stop offset="100%" stop-color="#10b981"/>
        </linearGradient>
      </defs>
      <rect width="180" height="180" rx="40" fill="url(#bg)"/>
      <rect x="8" y="8" width="164" height="164" rx="34" fill="none" stroke="url(#gd)" stroke-width="4" opacity="0.65"/>
      <text x="90" y="102" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-weight="900" font-size="68" fill="url(#gd)">SP</text>
      <text x="90" y="142" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,PingFang SC,sans-serif" font-weight="700" font-size="22" fill="#e6edf7">卖Put终端</text>
    </svg>"""
    return Response(svg, mimetype="image/svg+xml")


@app.route("/api/export-mobile")
def api_export_mobile():
    """
    Generate a standalone, zero-dependency, single-file interactive iPhone HTML report
    so the user can send it via WeChat / AirDrop and view/filter all 79 varieties on iPhone
    even when outside home Wi-Fi or when the PC is turned off.
    """
    dte = request.args.get("dte", default=30, type=int) or 30
    data = get_weekly_recommendations(target_dte=dte, force=False)
    payload_json = json.dumps(data, ensure_ascii=False)
    wc = data.get("weekContext") or {}
    week_label = wc.get("weekLabel") or "本周"
    filename = "ShortPut_iPhone_Weekly.html"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover"/>
<meta name="apple-mobile-web-app-capable" content="yes"/>
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"/>
<title>{week_label} 卖Put周度推荐 (iPhone离线便携版)</title>
<style>
:root {{ --bg:#080c14; --card:#131b2c; --border:#22304a; --txt:#e6edf7; --muted:#8b9bb4; --gold:#f59e0b; --bull:#10b981; --bear:#ef4444; --cyan:#38bdf8; }}
* {{ box-sizing:border-box; margin:0; padding:0; -webkit-tap-highlight-color:transparent; }}
body {{ background:var(--bg); color:var(--txt); font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif; font-size:13px; padding:env(safe-area-inset-top,12px) 12px calc(env(safe-area-inset-bottom,16px) + 16px); line-height:1.45; }}
.hdr {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:12px 14px; margin-bottom:12px; }}
.hdr h1 {{ font-size:17px; color:#fff; margin-bottom:4px; }}
.hdr .sub {{ font-size:12px; color:var(--muted); }}
.bar {{ display:flex; gap:6px; overflow-x:auto; padding-bottom:6px; margin-bottom:10px; }}
.bar button, .bar select {{ background:var(--card); color:var(--txt); border:1px solid var(--border); border-radius:8px; padding:7px 11px; font-size:12px; font-weight:600; white-space:nowrap; }}
.bar button.active {{ background:var(--gold); color:#080c14; border-color:var(--gold); font-weight:800; }}
.sec-title {{ font-size:14px; font-weight:800; color:var(--gold); margin:12px 0 8px; display:flex; justify-content:space-between; align-items:center; }}
.card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:12px; margin-bottom:10px; }}
.c-top {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; }}
.c-name {{ font-size:15px; font-weight:800; color:#fff; }}
.c-sym {{ font-size:11.5px; color:var(--muted); margin-left:6px; }}
.c-score {{ background:rgba(245,158,11,0.16); color:var(--gold); border:1px solid rgba(245,158,11,0.4); border-radius:6px; padding:2px 8px; font-weight:800; font-size:12.5px; }}
.grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:6px; background:rgba(8,12,20,0.55); border-radius:8px; padding:8px; margin:6px 0; }}
.m-lbl {{ font-size:10.5px; color:var(--muted); display:block; }}
.m-val {{ font-size:13px; font-weight:700; }}
.gold {{ color:var(--gold); }} .bull {{ color:var(--bull); }} .bear {{ color:var(--bear); }} .cyan {{ color:var(--cyan); }}
.note {{ font-size:11.5px; color:var(--muted); border-left:3px solid var(--gold); padding-left:8px; margin-top:6px; }}
.search {{ width:100%; background:var(--card); border:1px solid var(--border); color:#fff; border-radius:8px; padding:8px 12px; font-size:13px; margin-bottom:10px; outline:none; }}
</style>
</head>
<body>
<div class="hdr">
  <h1>📱 每周卖Put量化推荐 · iPhone便携版</h1>
  <div class="sub" id="meta-sub"></div>
</div>
<div class="bar" id="tier-bar">
  <button data-tier="auto" class="active">★ 智能推荐档</button>
  <button data-tier="conservative">保守高胜率 (Δ-0.15)</button>
  <button data-tier="balanced">平衡甜点 (Δ-0.25)</button>
  <button data-tier="aggressive">进取接货 (Δ-0.35)</button>
</div>
<div class="bar" id="mkt-bar">
  <button data-mkt="cn_idx" class="active">A股三大股指 (3)</button>
  <button data-mkt="top">三市场精选Top18</button>
  <button data-mkt="us_stk">美股与ETF (28)</button>
  <button data-mkt="us_fut">美国期货 (18)</button>
  <button data-mkt="cn_fut">中国期货 (33)</button>
  <button data-mkt="all">全部品种 (79)</button>
</div>
<input type="search" id="q" class="search" placeholder="搜索代码或名称 (如 IM0、沪深300、NVDA、豆粕、黄金)..."/>
<div id="list"></div>
<script>
const DATA = {payload_json};
let tierPref = "auto", mkt = "cn_idx", query = "";
const wc = DATA.weekContext || {{}};
document.getElementById("meta-sub").textContent = `${{wc.weekLabel || ""}} (${{wc.weekRange || ""}}) · 目标 ${{wc.targetDte || 30}}天 · 更新于 ${{DATA.updatedAt || ""}}`;
function getTier(r) {{
  if (tierPref !== "auto" && r.tiers && r.tiers[tierPref]) return r.tiers[tierPref];
  return r.recommendedTier || (r.tiers && r.tiers.balanced) || {{}};
}}
function render() {{
  const box = document.getElementById("list");
  let rows = DATA.all || [];
  if (query) {{
    const q = query.toLowerCase();
    rows = rows.filter(r => (`${{r.symbol}} ${{r.name}} ${{r.sector}} ${{r.archetype}}`).toLowerCase().includes(q));
  }} else if (mkt === "cn_idx") {{
    rows = DATA.cnIndexOptions || rows.filter(r => ["CN_FUT:IM0","CN_FUT:IF0","CN_FUT:IH0"].includes(r.id));
  }} else if (mkt === "top") {{
    rows = [...(DATA.cnIndexOptions||[]), ...(DATA.topPicks?.us_stk||[]), ...(DATA.topPicks?.us_fut||[]), ...(DATA.topPicks?.cn_fut||[])];
  }} else if (mkt !== "all") {{
    rows = rows.filter(r => r.market === mkt);
  }}
  box.innerHTML = rows.map((r, i) => {{
    const t = getTier(r);
    const cur = r.currency || "";
    return `<div class="card">
      <div class="c-top">
        <div><span class="c-name">${{i+1}}. ${{r.name}}</span><span class="c-sym">${{r.symbol}} · ${{r.marketLabel}}</span></div>
        <span class="c-score">${{Number(r.putScore).toFixed(1)}}分</span>
      </div>
      <div style="font-size:12px;margin-bottom:4px" class="cyan">● ${{r.archetype}} · 1D ${{r.change1dPct>0?"+":""}}${{r.change1dPct}}% / 1W ${{r.ret1wPct>0?"+":""}}${{r.ret1wPct}}%</div>
      <div class="grid">
        <div><span class="m-lbl">最新现价</span><span class="m-val">${{cur}}${{r.price}}</span></div>
        <div><span class="m-lbl">卖Put行权价(${{t.label?.slice(0,2)||"推荐"}})</span><span class="m-val gold">${{cur}}${{t.strike}}</span></div>
        <div><span class="m-lbl">安全垫 / 胜率</span><span class="m-val bull">${{t.otmPct}}% / ${{t.popPct}}%</span></div>
        <div><span class="m-lbl">单手权利金</span><span class="m-val">${{cur}}${{t.contractPremium}}</span></div>
        <div><span class="m-lbl">保证金/现金年化</span><span class="m-val gold">${{t.annReturnMarginPct}}% / ${{t.annReturnCashPct}}%</span></div>
        <div><span class="m-lbl">隐波IV (IVR)</span><span class="m-val cyan">${{r.atmIvPct}}% (${{r.ivRank}}%)</span></div>
      </div>
      <div class="note">${{r.thesisSummary || ""}}</div>
    </div>`;
  }}).join("");
}}
document.querySelectorAll("#tier-bar button").forEach(b => b.onclick = () => {{
  document.querySelectorAll("#tier-bar button").forEach(x => x.classList.remove("active"));
  b.classList.add("active"); tierPref = b.dataset.tier; render();
}});
document.querySelectorAll("#mkt-bar button").forEach(b => b.onclick = () => {{
  document.querySelectorAll("#mkt-bar button").forEach(x => x.classList.remove("active"));
  b.classList.add("active"); mkt = b.dataset.mkt; render();
}});
document.getElementById("q").oninput = e => {{ query = e.target.value.trim(); render(); }};
render();
</script>
</body>
</html>"""
    return Response(
        html,
        mimetype="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/recommendations")
def api_recommendations():
    dte = request.args.get("dte", default=30, type=int) or 30
    force = request.args.get("force") == "1"
    try:
        data = get_weekly_recommendations(target_dte=dte, force=force)
        return jsonify(data)
    except Exception as exc:
        logger.exception("api_recommendations failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/backtest")
def api_backtest():
    force = request.args.get("force") == "1"
    try:
        data = get_historical_review(hold_trading_days=20, num_cohorts=12, force=force)
        return jsonify(data)
    except Exception as exc:
        logger.exception("api_backtest failed")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/detail")
def api_detail():
    inst_id = request.args.get("id") or "CN_FUT:M0"
    dte = request.args.get("dte", default=30, type=int) or 30
    tier = request.args.get("tier")
    custom_strike = request.args.get("strike", type=float)
    force = request.args.get("force") == "1"
    try:
        data = get_instrument_detail(
            inst_id=inst_id,
            target_dte=dte,
            tier_key=tier,
            custom_strike=custom_strike,
            force=force,
        )
        return jsonify(data)
    except Exception as exc:
        logger.exception("api_detail failed for %s", inst_id)
        return jsonify({"error": str(exc)}), 400


@app.route("/api/option-chain")
def api_option_chain():
    inst_id = request.args.get("id") or "US_STK:NVDA"
    dte = request.args.get("dte", default=30, type=int) or 30
    try:
        data = fetch_live_option_chain_sample(inst_id=inst_id, target_dte=dte)
        return jsonify(data)
    except Exception as exc:
        logger.exception("api_option_chain failed for %s", inst_id)
        return jsonify({"available": False, "note": str(exc)}), 200


@app.route("/api/simulate")
def api_simulate():
    inst_id = request.args.get("id") or "CN_FUT:M0"
    spot = request.args.get("spot", type=float)
    strike = request.args.get("strike", type=float)
    dte = request.args.get("dte", default=30, type=int) or 30
    iv_pct = request.args.get("iv", type=float)
    lots = max(1, min(request.args.get("lots", default=1, type=int) or 1, 1000))

    inst = get_instrument(inst_id)
    if not inst or not spot or not strike or spot <= 0 or strike <= 0:
        return jsonify({"error": "Invalid parameters"}), 400

    is_fut = inst["market"] in ("us_fut", "cn_fut")
    r = 0.020 if inst["market"] == "cn_fut" else 0.042
    dp = int(inst.get("dp", 2))
    mult = float(inst.get("multiplier", 100))
    margin_rate = float(inst.get("margin_rate", 0.15))

    atm_iv = (iv_pct / 100.0) if (iv_pct and iv_pct > 0) else 0.25
    strike_iv = skew_adjusted_iv(atm_iv, spot, strike, float(inst.get("iv_skew", 0.12)))
    res = price_put_and_greeks(spot, strike, dte, strike_iv, r=r, is_futures=is_fut)

    prem = res["premium"]
    be = res["breakeven"]
    otm_amt = max(0.0, spot - strike)
    otm_pct = (otm_amt / spot) * 100.0

    eff_margin_rate = margin_rate * 1.25
    unit_margin = prem + max(eff_margin_rate * spot - 0.5 * otm_amt, 0.70 * eff_margin_rate * spot)
    margin_req = max(unit_margin * mult, strike * mult * 0.08) * lots
    cash_req = strike * mult * lots
    total_prem = prem * mult * lots
    total_theta = res["theta_daily"] * mult * lots

    roc_margin = (total_prem / margin_req) * 100.0 if margin_req > 0 else 0.0
    ann_margin = roc_margin * (365.0 / max(dte, 1))
    roc_cash = (prem / strike) * 100.0 if strike > 0 else 0.0
    ann_cash = roc_cash * (365.0 / max(dte, 1))

    payoff = build_payoff_curve(inst, spot, strike, dte, strike_iv, prem)
    # Scale payoff by lots
    if lots != 1:
        payoff["expPnl"] = [round(x * lots, 1) for x in payoff["expPnl"]]
        payoff["midPnl"] = [round(x * lots, 1) for x in payoff["midPnl"]]
        payoff["maxProfit"] = round(payoff["maxProfit"] * lots, 1)

    return jsonify(
        {
            "strike": round(strike, dp),
            "lots": lots,
            "dte": dte,
            "otmPct": round(otm_pct, 2),
            "ivPct": round(strike_iv * 100.0, 1),
            "premium": round(prem, max(dp, 2)),
            "totalPremium": round(total_prem, 1),
            "breakeven": round(be, dp),
            "breakevenBufferPct": round((spot - be) / spot * 100.0, 2),
            "delta": round(res["delta"], 3),
            "thetaDailyTotal": round(total_theta, 1),
            "popPct": round(res["pop_pct"], 1),
            "marginReq": round(margin_req, 0),
            "cashSecuredReq": round(cash_req, 0),
            "annReturnMarginPct": round(ann_margin, 1),
            "annReturnCashPct": round(ann_cash, 1),
            "payoff": payoff,
        }
    )


def _bg_warmup():
    try:
        logger.info("Warming up weekly Short Put recommendations across US Stocks, US Futures, CN Futures...")
        get_weekly_recommendations(target_dte=30, force=False)
        logger.info("Short Put recommendation engine ready.")
    except Exception:
        logger.exception("Warmup failed")


if __name__ == "__main__":
    import socket
    from werkzeug.serving import make_server

    # Check if already running on PORT
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            print(f"Server is already running at http://127.0.0.1:{PORT}")
            raise SystemExit(0)

    threading.Thread(target=_bg_warmup, daemon=True).start()
    print("=" * 68)
    print(f"  [Short Put Weekly Terminal] http://127.0.0.1:{PORT}")
    print(f"  [IPv6 / Localhost Support]  http://localhost:{PORT}")
    print("  每周动态卖Put推荐系统 · 美股/ETF · 美国期货 · 中国期货")
    print("=" * 68)

    # Bind IPv6 ::1 in background thread so Chrome 'localhost' (::1) connects instantly
    try:
        srv_v6 = make_server("::1", PORT, app, threaded=True)
        threading.Thread(target=srv_v6.serve_forever, daemon=True).start()
    except Exception as exc:
        logger.warning("IPv6 ::1 bind skipped: %s", exc)

    # Bind IPv4 0.0.0.0 in main thread (covers 127.0.0.1 and LAN IP)
    srv_v4 = make_server("0.0.0.0", PORT, app, threaded=True)
    srv_v4.serve_forever()
