# -*- coding: utf-8 -*-
"""
Multi-Market Data Engine for Short Put Recommender:
- China Futures (SHFE/DCE/CZCE/INE/GFEX) via Sina Futures API
- US Futures (CME/COMEX/NYMEX/CBOT/ICE) via Yahoo Finance v8 Chart
- US Stocks & Core ETFs via Yahoo Finance v8 Chart + Sina Real-time Quotes
- Global Volatility Regime (^VIX, ^VXN, ^OVX, ^GVZ) + Live Option Chain Enrichment
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import logging
import math
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse

from http_utils import (
    cached,
    fetch_json,
    fetch_text,
    load_pickle,
    now_bj,
    parse_jsonp,
    save_pickle,
    to_bj,
)
from universe import ALL_INSTRUMENTS, BY_ID, get_instrument

logger = logging.getLogger(__name__)

SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}
_SINA_LINE_RE = re.compile(r'var\s+hq_str_([\w$]+)="([^"]*)"')

_BARS_LOCK = threading.Lock()
_BARS_MEM: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
BARS_TTL = 1800.0  # 30 min memory cache for daily history


def _fnum(v: Any) -> Optional[float]:
    try:
        n = float(v)
        return n if (n == n and not math.isinf(n)) else None
    except (TypeError, ValueError):
        return None


def _parse_sina_batch(text: str) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for m in _SINA_LINE_RE.finditer(text):
        key, val = m.group(1), m.group(2)
        if val:
            out[key] = val.split(",")
    return out


def fetch_sina_realtime_quotes() -> Dict[str, Dict[str, Any]]:
    """
    Batch-fetch real-time quotes from Sina for all CN futures (nf_*) and US stocks (gb_*).
    """
    def _load() -> Dict[str, Dict[str, Any]]:
        codes: List[str] = ["fx_susdcny", "DINIW"]
        code_to_inst: Dict[str, Dict[str, Any]] = {}
        for inst in ALL_INSTRUMENTS:
            sc = inst.get("sina_code")
            if sc and inst["market"] in ("cn_fut", "us_stk"):
                codes.append(sc)
                code_to_inst[sc] = inst

        out: Dict[str, Dict[str, Any]] = {}
        chunk_size = 45
        for i in range(0, len(codes), chunk_size):
            batch = codes[i : i + chunk_size]
            url = f"https://hq.sinajs.cn/list={','.join(batch)}"
            try:
                txt = fetch_text(url, headers=SINA_HEADERS, encoding="gbk", timeout=6.0)
                parsed = _parse_sina_batch(txt)
            except Exception as exc:
                logger.warning("Sina batch quote error: %s", exc)
                continue

            for code, fields in parsed.items():
                if code == "fx_susdcny" and len(fields) > 8:
                    px = _fnum(fields[8])
                    prev = _fnum(fields[3])
                    if px:
                        out["MACRO:USDCNY"] = {
                            "price": px,
                            "prev": prev or px,
                            "changePct": round((px - prev) / prev * 100.0, 2) if prev else 0.0,
                        }
                    continue
                if code == "DINIW" and len(fields) > 3:
                    px = _fnum(fields[1]) or (_fnum(fields[8]) if len(fields) > 8 else None)
                    prev = _fnum(fields[3])
                    if px:
                        out["MACRO:DXY"] = {
                            "price": px,
                            "prev": prev or px,
                            "changePct": round((px - prev) / prev * 100.0, 2) if prev else 0.0,
                        }
                    continue

                inst = code_to_inst.get(code)
                if not inst:
                    continue
                mkt = inst["market"]
                if mkt == "cn_fut" and len(fields) > 10:
                    if inst.get("exchange") == "中金所":
                        # 中金所股指期货 (nf_IM0, nf_IF0, nf_IH0):
                        # 0开 1高 2低 3最新 4成交量 5成交额 6持仓量 ... 13昨收 14昨结 ... 36日期
                        px = _fnum(fields[3]) or _fnum(fields[14]) or _fnum(fields[13])
                        prev = _fnum(fields[14]) or _fnum(fields[13]) or px
                        op = _fnum(fields[0]) or px
                        hi = _fnum(fields[1]) or px
                        lo = _fnum(fields[2]) or px
                        vol = _fnum(fields[4])
                        oi = _fnum(fields[6])
                        d_str = fields[36] if len(fields) > 36 else ""
                    else:
                        # 商品期货: 0名称 1时间 2开 3高 4低 6买 7卖 8最新 9结算 10昨结 13持仓 14成交量 17日期
                        px = _fnum(fields[8]) or _fnum(fields[6]) or _fnum(fields[10])
                        prev = _fnum(fields[10]) or px
                        op = _fnum(fields[2]) or px
                        hi = _fnum(fields[3]) or px
                        lo = _fnum(fields[4]) or px
                        oi = _fnum(fields[13]) if len(fields) > 13 else None
                        vol = _fnum(fields[14]) if len(fields) > 14 else None
                        d_str = fields[17] if len(fields) > 17 else ""
                    if px and px > 0:
                        out[inst["id"]] = {
                            "price": px,
                            "prev": prev,
                            "open": op,
                            "high": hi,
                            "low": lo,
                            "volume": vol,
                            "oi": oi,
                            "date": d_str[:10] if d_str else datetime.now().strftime("%Y-%m-%d"),
                        }
                elif mkt == "us_stk" and len(fields) > 7:
                    # 0名称 1最新 2涨幅% 3时间 4涨跌额 5开 6高 7低 ... 10成交量
                    px = _fnum(fields[1])
                    chg = _fnum(fields[4])
                    prev = (px - chg) if (px is not None and chg is not None) else px
                    op = _fnum(fields[5]) or px
                    hi = _fnum(fields[6]) or px
                    lo = _fnum(fields[7]) or px
                    vol = _fnum(fields[10]) if len(fields) > 10 else None
                    if px and px > 0:
                        out[inst["id"]] = {
                            "price": px,
                            "prev": prev,
                            "open": op,
                            "high": hi,
                            "low": lo,
                            "volume": vol,
                            "oi": None,
                            "date": str(fields[3])[:10] if len(fields) > 3 else "",
                        }
        return out

    return cached("sina_rt_quotes", 12.0, _load)


def _fetch_cn_daily_bars(symbol: str) -> List[Dict[str, Any]]:
    """Fetch China futures continuous daily K-lines from Sina."""
    url = (
        f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
        f"var%20_{symbol}=/InnerFuturesNewService.getDailyKLine?symbol={symbol}"
    )
    txt = fetch_text(url, headers=SINA_HEADERS, timeout=7.0)
    raw = parse_jsonp(txt)
    out: List[Dict[str, Any]] = []
    for r in raw or []:
        c = _fnum(r.get("c"))
        if not c or c <= 0:
            continue
        o = _fnum(r.get("o")) or c
        h = _fnum(r.get("h")) or c
        l = _fnum(r.get("l")) or c
        v = _fnum(r.get("v")) or 0.0
        p = _fnum(r.get("p")) or 0.0  # open interest
        out.append(
            {
                "t": str(r.get("d", ""))[:10],
                "o": o,
                "h": max(h, c),
                "l": min(l, c) if l > 0 else c,
                "c": c,
                "v": v,
                "oi": p,
            }
        )
    return out[-1260:]  # Keep up to 5 years


def _fetch_yahoo_daily_bars(yahoo_code: str, range_str: str = "5y") -> List[Dict[str, Any]]:
    """Fetch daily OHLCV bars + latest meta quote from Yahoo Finance v8 Chart API."""
    enc = urllib.parse.quote(yahoo_code)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}?range={range_str}&interval=1d"
    j = fetch_json(url, timeout=7.5)
    res = (j.get("chart") or {}).get("result") or []
    if not res:
        return []
    r0 = res[0]
    meta = r0.get("meta") or {}
    ts_list = r0.get("timestamp") or []
    q0 = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    opens = q0.get("open") or []
    highs = q0.get("high") or []
    lows = q0.get("low") or []
    closes = q0.get("close") or []
    vols = q0.get("volume") or []

    out: List[Dict[str, Any]] = []
    for i, ts in enumerate(ts_list):
        c = _fnum(closes[i]) if i < len(closes) else None
        if not c or c <= 0:
            continue
        o = _fnum(opens[i]) if i < len(opens) else None
        h = _fnum(highs[i]) if i < len(highs) else None
        l = _fnum(lows[i]) if i < len(lows) else None
        v = _fnum(vols[i]) if i < len(vols) else 0.0
        o = o if (o and o > 0) else c
        h = max(h if (h and h > 0) else c, c)
        l = min(l if (l and l > 0) else c, c)
        t_str = to_bj(ts)[:10]
        out.append({"t": t_str, "o": o, "h": h, "l": l, "c": c, "v": v or 0.0, "oi": 0.0})

    # Patch or append live regularMarketPrice if fresher
    reg_px = _fnum(meta.get("regularMarketPrice"))
    if reg_px and reg_px > 0 and out:
        last_b = dict(out[-1])
        last_b["c"] = reg_px
        reg_hi = _fnum(meta.get("regularMarketDayHigh"))
        reg_lo = _fnum(meta.get("regularMarketDayLow"))
        if reg_hi and reg_hi > 0:
            last_b["h"] = max(last_b["h"], reg_hi, reg_px)
        if reg_lo and reg_lo > 0:
            last_b["l"] = min(last_b["l"], reg_lo, reg_px)
        out[-1] = last_b

    return out[-1260:]


def get_instrument_bars(inst_id: str, force: bool = False) -> List[Dict[str, Any]]:
    """Return daily OHLCV bars for an instrument, patched with latest real-time quote."""
    inst = BY_ID.get(inst_id)
    if not inst:
        return []

    now = time.time()
    with _BARS_LOCK:
        cached_item = _BARS_MEM.get(inst_id)
        if not force and cached_item and (now - cached_item[0] < BARS_TTL) and cached_item[1]:
            bars = [dict(b) for b in cached_item[1]]
            return _patch_realtime_bar(inst, bars)

    # Fetch fresh daily bars
    try:
        if inst["market"] == "cn_fut":
            bars = _fetch_cn_daily_bars(inst["symbol"])
        else:
            bars = _fetch_yahoo_daily_bars(inst["yahoo_code"], range_str="5y")
    except Exception as exc:
        logger.warning("Failed to fetch bars for %s: %s", inst_id, exc)
        bars = []

    if bars:
        with _BARS_LOCK:
            _BARS_MEM[inst_id] = (time.time(), bars)
        return _patch_realtime_bar(inst, [dict(b) for b in bars])

    # Fallback to stale memory if any
    with _BARS_LOCK:
        if cached_item and cached_item[1]:
            return _patch_realtime_bar(inst, [dict(b) for b in cached_item[1]])
    return []


def _patch_realtime_bar(inst: Dict[str, Any], bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not bars:
        return bars
    try:
        rt_map = fetch_sina_realtime_quotes()
        rt = rt_map.get(inst["id"])
        if rt and rt.get("price") and rt["price"] > 0:
            px = float(rt["price"])
            last = dict(bars[-1])
            # Sanity check: avoid corrupt tick > 35% away from last close
            if 0.65 <= (px / last["c"]) <= 1.45:
                last["c"] = px
                if rt.get("high") and rt["high"] > 0:
                    last["h"] = max(last["h"], float(rt["high"]), px)
                else:
                    last["h"] = max(last["h"], px)
                if rt.get("low") and rt["low"] > 0:
                    last["l"] = min(last["l"], float(rt["low"]), px)
                else:
                    last["l"] = min(last["l"], px)
                if rt.get("oi"):
                    last["oi"] = float(rt["oi"])
                bars[-1] = last
    except Exception:
        pass
    return bars


def ensure_all_bars_loaded(force: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load all instrument daily histories in parallel (with disk pickle persistence for instant startup).
    """
    if not force:
        disk_data = load_pickle("all_bars_v1.pkl", max_age_sec=3600.0 * 6)
        if disk_data and isinstance(disk_data, dict) and len(disk_data) >= len(ALL_INSTRUMENTS) * 0.8:
            now = time.time()
            with _BARS_LOCK:
                for k, v in disk_data.items():
                    if k not in _BARS_MEM and v:
                        _BARS_MEM[k] = (now, v)

    missing_ids = []
    now = time.time()
    with _BARS_LOCK:
        for inst in ALL_INSTRUMENTS:
            iid = inst["id"]
            c = _BARS_MEM.get(iid)
            if force or not c or (now - c[0] >= BARS_TTL) or not c[1]:
                missing_ids.append(iid)

    if missing_ids:
        logger.info("Fetching daily history for %d instruments in parallel...", len(missing_ids))
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=20) as pool:
            futs = {pool.submit(get_instrument_bars, iid, True): iid for iid in missing_ids}
            for fut in as_completed(futs):
                try:
                    fut.result()
                except Exception as exc:
                    logger.debug("Warmup fail %s: %s", futs[fut], exc)
        logger.info("Daily history fetch done in %.2fs", time.time() - t0)
        with _BARS_LOCK:
            snapshot = {k: v[1] for k, v in _BARS_MEM.items() if v and v[1]}
        if snapshot:
            save_pickle("all_bars_v1.pkl", snapshot)

    # Return patched bars for all instruments
    out: Dict[str, List[Dict[str, Any]]] = {}
    for inst in ALL_INSTRUMENTS:
        iid = inst["id"]
        b = get_instrument_bars(iid, force=False)
        if b:
            out[iid] = b
    return out


def get_macro_vol_regime(force: bool = False) -> Dict[str, Any]:
    """
    Fetch global volatility indices (^VIX, ^VXN, ^OVX, ^GVZ), USD/CNY, and US10Y yield.
    Used both for the top macro banner and for calibrating Implied Volatility Risk Premium (VRP).
    """
    def _load() -> Dict[str, Any]:
        vol_specs = [
            ("VIX", "^VIX", "标普500恐慌指数 VIX", "美股大盘隐波基准"),
            ("VXN", "^VXN", "纳指100波动率 VXN", "科技成长股隐波基准"),
            ("OVX", "^OVX", "原油波动率指数 OVX", "能源化工期权隐波锚"),
            ("GVZ", "^GVZ", "黄金波动率指数 GVZ", "贵金属期权隐波锚"),
            ("US10Y", "^TNX", "10Y美债收益率", "全球无风险利率定价锚"),
        ]
        results: Dict[str, Any] = {}

        def _one(key: str, code: str, name: str, sub: str) -> Tuple[str, Optional[Dict[str, Any]]]:
            try:
                bars = _fetch_yahoo_daily_bars(code, range_str="1y")
                if not bars:
                    return key, None
                cur = bars[-1]["c"]
                prev = bars[-2]["c"] if len(bars) > 1 else cur
                closes = [b["c"] for b in bars[-252:]]
                pct_1y = sum(1 for x in closes if x < cur) / max(len(closes), 1) * 100.0
                chg_pct = ((cur - prev) / prev * 100.0) if prev else 0.0
                return key, {
                    "id": key,
                    "name": name,
                    "sub": sub,
                    "value": round(cur, 2),
                    "prev": round(prev, 2),
                    "changePct": round(chg_pct, 2),
                    "pct1y": round(pct_1y, 1),
                    "high1y": round(max(closes), 2),
                    "low1y": round(min(closes), 2),
                }
            except Exception:
                return key, None

        with ThreadPoolExecutor(max_workers=5) as pool:
            for k, val in pool.map(lambda s: _one(*s), vol_specs):
                if val:
                    results[k] = val

        # Add USD/CNY from Sina quotes
        try:
            rt = fetch_sina_realtime_quotes()
            fx = rt.get("MACRO:USDCNY")
            if fx:
                results["USDCNY"] = {
                    "id": "USDCNY",
                    "name": "美元/人民币即期",
                    "sub": "内外盘商品比价汇率锚",
                    "value": round(fx["price"], 4),
                    "prev": round(fx["prev"], 4),
                    "changePct": fx["changePct"],
                    "pct1y": 50.0,
                }
        except Exception:
            pass

        # Defaults if any index was unreachable
        vix_val = (results.get("VIX") or {}).get("value") or 18.5
        vxn_val = (results.get("VXN") or {}).get("value") or 22.0
        ovx_val = (results.get("OVX") or {}).get("value") or 34.0
        gvz_val = (results.get("GVZ") or {}).get("value") or 17.5

        if vix_val >= 25:
            regime_label = "高波动恐慌溢价期 · 卖Put权利金极肥（宜选深虚值Delta -0.15）"
            regime_tone = "bull"
        elif vix_val >= 17:
            regime_label = "温和波动均衡期 · 机构标准卖Put收租甜点区（Delta -0.20~-0.25）"
            regime_tone = "gold"
        else:
            regime_label = "低波动平静期 · 权利金偏薄，精选高IV个股或破成本商品卖Put"
            regime_tone = "neutral"

        return {
            "items": results,
            "vix": vix_val,
            "vxn": vxn_val,
            "ovx": ovx_val,
            "gvz": gvz_val,
            "regimeLabel": regime_label,
            "regimeTone": regime_tone,
            "updatedAt": now_bj(),
        }

    return cached("macro_vol_regime", 120.0, _load, force=force)


def _solve_cffex_put_iv(
    spot: float,
    strike: float,
    dte: int,
    put_price: float,
    r: float = 0.02,
    is_futures: bool = True,
) -> float:
    """Bisection solver for Put implied volatility (in %) from market mid/last price (BSM or Black-76)."""
    if spot <= 0 or strike <= 0 or put_price <= 0:
        return 20.0
    T = max(int(dte), 1) / 365.0
    sqrt_T = math.sqrt(T)
    b = 0.0 if is_futures else r
    df_r = math.exp(-r * T)
    df_b = math.exp((b - r) * T)
    intrinsic = max(0.0, strike * df_r - spot * df_b)
    if put_price <= intrinsic + spot * 0.0005:
        return 8.0

    lo, hi = 0.04, 1.80
    for _ in range(28):
        mid_iv = 0.5 * (lo + hi)
        vol_sqrt_T = mid_iv * sqrt_T
        d1 = (math.log(spot / strike) + (b + 0.5 * mid_iv * mid_iv) * T) / vol_sqrt_T
        d2 = d1 - vol_sqrt_T
        nd1 = 0.5 * (1.0 + math.erf(-d1 / math.sqrt(2.0)))
        nd2 = 0.5 * (1.0 + math.erf(-d2 / math.sqrt(2.0)))
        theo = strike * df_r * nd2 - spot * df_b * nd1
        if theo > put_price:
            hi = mid_iv
        else:
            lo = mid_iv
    return round(0.5 * (lo + hi) * 100.0, 1)


def _fetch_cffex_option_chain(inst: Dict[str, Any], target_dte: int = 30) -> Dict[str, Any]:
    """Fetch real-time CFFEX index option chain (MO / IO / HO) from Sina OptionService."""
    from http_utils import _third_friday

    prod = inst["cffex_opt"]  # 'mo' | 'io' | 'ho'
    bars = get_instrument_bars(inst["id"], force=False)
    spot = float(bars[-1]["c"]) if bars else 0.0
    if spot <= 0:
        return {"available": False, "note": "无法获取股指现价"}

    today = datetime.now().date()
    # Pick the monthly contract (current, +1m, or +2m) whose 3rd-Friday DTE is closest to target_dte (and >= 5 days)
    best_ym = (today.year, today.month)
    best_diff = 9999
    best_exp_date = today
    for add_m in (0, 1, 2, 3):
        cy = today.year + (today.month + add_m - 1) // 12
        cm = (today.month + add_m - 1) % 12 + 1
        exp_d = _third_friday(cy, cm)
        dte_cand = (exp_d - today).days
        if dte_cand >= 5 and abs(dte_cand - target_dte) < best_diff:
            best_diff = abs(dte_cand - target_dte)
            best_ym = (cy, cm)
            best_exp_date = exp_d

    y, m = best_ym
    pinzhong = f"{prod}{str(y)[-2:]}{m:02d}"

    url = (
        f"https://stock.finance.sina.com.cn/futures/api/openapi.php/OptionService.getOptionData"
        f"?type=futures&product={prod}&exchange=cffex&pinzhong={pinzhong}"
    )
    j = fetch_json(url, headers=SINA_HEADERS, timeout=6.0)
    down = ((j.get("result") or {}).get("data") or {}).get("down") or []
    if not down:
        return {"available": False, "note": f"暂未获取到 {pinzhong} 实时期权链"}

    actual_dte = max(1, (best_exp_date - today).days)
    rows: List[Dict[str, Any]] = []
    for item in down:
        if len(item) < 8:
            continue
        sym_str = str(item[7])
        m_strike = re.search(r"P(\d+(?:\.\d+)?)", sym_str, re.IGNORECASE)
        if not m_strike:
            continue
        k = float(m_strike.group(1))
        if k > spot * 1.03 or k < spot * 0.78:
            continue
        bid = _fnum(item[1]) or 0.0
        last_p = _fnum(item[2]) or 0.0
        ask = _fnum(item[3]) or 0.0
        mid = round((bid + ask) / 2.0, 1) if (bid > 0 and ask > 0) else last_p
        oi = int(_fnum(item[5]) or 0)
        vol = int(_fnum(item[0]) or 0) + int(_fnum(item[4]) or 0)
        otm_pct = round((spot - k) / spot * 100.0, 2)
        ann_cash = round((mid / k) * (365.0 / actual_dte) * 100.0, 1) if k > 0 else 0.0
        solved_iv = _solve_cffex_put_iv(spot, k, actual_dte, mid if mid > 0 else last_p)
        rows.append(
            {
                "contractSymbol": sym_str.upper(),
                "strike": round(k, 1),
                "otmPct": otm_pct,
                "bid": round(bid, 1),
                "ask": round(ask, 1),
                "mid": round(mid, 1),
                "lastPrice": round(last_p, 1),
                "ivPct": solved_iv,
                "volume": vol,
                "openInterest": oi,
                "annCashReturnPct": ann_cash,
            }
        )

    rows.sort(key=lambda x: x["strike"], reverse=True)
    return {
        "available": True,
        "ticker": pinzhong.upper(),
        "isProxy": False,
        "currency": "¥",
        "spot": round(spot, 1),
        "expiry": f"{best_exp_date.strftime('%Y-%m-%d')} (中金所到期日)",
        "dte": actual_dte,
        "puts": rows[:14],
        "updatedAt": now_bj(),
    }


def fetch_live_option_chain_sample(inst_id: str, target_dte: int = 30) -> Dict[str, Any]:
    """
    On-demand live option chain verification via Sina (for CFFEX MO/IO/HO) or
    yfinance (for US Stocks/ETFs & US Futures proxies), returning real Bid/Ask/Last/OI.
    """
    inst = get_instrument(inst_id)
    if not inst:
        return {"available": False, "note": "Unknown instrument"}

    if inst.get("cffex_opt"):
        try:
            return cached(
                f"cffex_chain:{inst['id']}:{target_dte}",
                60.0,
                lambda: _fetch_cffex_option_chain(inst, target_dte=target_dte),
            )
        except Exception as exc:
            logger.debug("CFFEX chain fail %s: %s", inst_id, exc)

    ticker_sym = None
    is_proxy = False
    if inst["market"] == "us_stk":
        ticker_sym = inst["yahoo_code"]
    elif inst["market"] == "us_fut" and inst.get("proxy_etf"):
        ticker_sym = inst["proxy_etf"]
        is_proxy = True

    if not ticker_sym:
        return {
            "available": False,
            "note": f"{inst['exchange']}场内期权采用Black-76精确理论定价与波动率偏度模型",
        }

    def _load() -> Dict[str, Any]:
        import yfinance as yf

        tk = yf.Ticker(ticker_sym)
        exps = tk.options
        if not exps:
            return {"available": False, "note": "暂无公开期权链数据"}

        today = datetime.now().date()
        best_exp = exps[0]
        best_diff = 9999
        for e in exps:
            try:
                ed = datetime.strptime(e, "%Y-%m-%d").date()
                dte = (ed - today).days
                if dte >= 5 and abs(dte - target_dte) < best_diff:
                    best_diff = abs(dte - target_dte)
                    best_exp = e
            except ValueError:
                continue

        ed = datetime.strptime(best_exp, "%Y-%m-%d").date()
        actual_dte = max(1, (ed - today).days)
        chain = tk.option_chain(best_exp)
        puts = chain.puts
        if puts is None or puts.empty:
            return {"available": False, "note": "期权链Put为空"}

        # Get current underlying price of ticker_sym
        hist = tk.history(period="5d")
        spot = float(hist["Close"].iloc[-1]) if (hist is not None and not hist.empty) else None
        if not spot:
            return {"available": False, "note": "无法获取标的现价"}

        # Filter OTM puts in [0.80 * spot, 1.02 * spot]
        sub = puts[(puts["strike"] >= spot * 0.80) & (puts["strike"] <= spot * 1.02)].copy()
        if sub.empty:
            sub = puts.tail(12).copy()

        rows: List[Dict[str, Any]] = []
        for _, r in sub.iterrows():
            k = float(r.get("strike") or 0)
            last_p = _fnum(r.get("lastPrice")) or 0.0
            bid = _fnum(r.get("bid")) or 0.0
            ask = _fnum(r.get("ask")) or 0.0
            mid = round((bid + ask) / 2.0, 2) if (bid > 0 and ask > 0) else last_p
            iv = (_fnum(r.get("impliedVolatility")) or 0.0) * 100.0
            px_for_iv = mid if mid > 0 else last_p
            if (iv < 6.0 or iv > 220.0 or bid <= 0) and px_for_iv > 0:
                iv = _solve_cffex_put_iv(spot, k, actual_dte, px_for_iv, r=0.042, is_futures=False)
            oi = int(_fnum(r.get("openInterest")) or 0)
            vol = int(_fnum(r.get("volume")) or 0)
            otm_pct = round((spot - k) / spot * 100.0, 2)
            ann_cash = round((mid / k) * (365.0 / actual_dte) * 100.0, 1) if k > 0 else 0.0
            rows.append(
                {
                    "contractSymbol": str(r.get("contractSymbol") or ""),
                    "strike": round(k, 2),
                    "otmPct": otm_pct,
                    "bid": round(bid, 2),
                    "ask": round(ask, 2),
                    "mid": round(mid, 2),
                    "lastPrice": round(last_p, 2),
                    "ivPct": round(iv, 1),
                    "volume": vol,
                    "openInterest": oi,
                    "annCashReturnPct": ann_cash,
                }
            )

        rows.sort(key=lambda x: x["strike"], reverse=True)
        return {
            "available": True,
            "ticker": ticker_sym,
            "isProxy": is_proxy,
            "spot": round(spot, 2),
            "expiry": best_exp,
            "dte": actual_dte,
            "puts": rows[:14],
            "updatedAt": now_bj(),
        }

    try:
        return cached(f"optchain:{ticker_sym}:{target_dte}", 300.0, _load)
    except Exception as exc:
        logger.debug("Live option chain fail %s: %s", ticker_sym, exc)
        return {"available": False, "note": f"实时期权链请求受限: {exc}"}


_US_IV_BG_STARTED = False
_US_IV_MEM: Dict[str, float] = {}


def _extract_atm_iv_from_chain(ch: Dict[str, Any]) -> Optional[float]:
    if not ch or not ch.get("available"):
        return None
    puts = ch.get("puts") or []
    if not puts:
        return None
    # Pick up to 3 contracts closest to ATM (otmPct in [-1%, +6%])
    near = sorted(puts, key=lambda p: abs(float(p.get("otmPct") or 0.0) - 2.0))[:3]
    valid_ivs = [float(p["ivPct"]) / 100.0 for p in near if 8.0 < float(p.get("ivPct") or 0.0) < 180.0]
    if not valid_ivs:
        return None
    valid_ivs.sort()
    return valid_ivs[len(valid_ivs) // 2]


def _bg_refresh_us_option_ivs(target_dte: int = 30) -> None:
    global _US_IV_BG_STARTED
    try:
        saved = load_pickle("real_us_iv_v1.pkl", max_age_sec=14400.0) or {}
        if isinstance(saved, dict):
            _US_IV_MEM.update(saved)
        us_insts = [x for x in ALL_INSTRUMENTS if x["market"] == "us_stk"]
        for inst in us_insts:
            iid = inst["id"]
            if iid in _US_IV_MEM:
                continue
            try:
                ch = fetch_live_option_chain_sample(iid, target_dte=target_dte)
                iv_val = _extract_atm_iv_from_chain(ch)
                if iv_val and 0.08 <= iv_val <= 1.60:
                    _US_IV_MEM[iid] = round(iv_val, 4)
            except Exception:
                continue
        if _US_IV_MEM:
            save_pickle("real_us_iv_v1.pkl", dict(_US_IV_MEM))
    finally:
        _US_IV_BG_STARTED = False


def get_real_iv_map(
    target_dte: int = 30,
    macro_regime: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """
    Return verified real-market ATM Implied Volatility map: {inst_id: {"atmIv": float, "ivSource": str}}.
    Combines:
    1) CBOE Official Implied Volatility Indices (^VIX, ^VXN, ^OVX, ^GVZ)
    2) CFFEX Real-Time Index Option Chains (MO / IO / HO via Sina OptionService)
    3) US Stocks & ETFs Real Option Chains (cached on disk + background refreshed via yfinance)
    """
    global _US_IV_BG_STARTED
    out: Dict[str, Dict[str, Any]] = {}
    mr = macro_regime or {}

    vix = _fnum((mr.get("items") or {}).get("VIX", {}).get("value")) or _fnum(mr.get("vix"))
    vxn = _fnum((mr.get("items") or {}).get("VXN", {}).get("value")) or _fnum(mr.get("vxn"))
    ovx = _fnum((mr.get("items") or {}).get("OVX", {}).get("value")) or _fnum(mr.get("ovx"))
    gvz = _fnum((mr.get("items") or {}).get("GVZ", {}).get("value")) or _fnum(mr.get("gvz"))

    if vix and vix > 5:
        out["US_STK:SPY"] = {"atmIv": vix / 100.0, "ivSource": "🟢 实盘IV(CBOE VIX)"}
        out["US_FUT:ES"] = {"atmIv": vix / 100.0, "ivSource": "🟢 实盘IV(CBOE VIX)"}
    if vxn and vxn > 5:
        out["US_STK:QQQ"] = {"atmIv": vxn / 100.0, "ivSource": "🟢 实盘IV(CBOE VXN)"}
        out["US_FUT:NQ"] = {"atmIv": vxn / 100.0, "ivSource": "🟢 实盘IV(CBOE VXN)"}
    if ovx and ovx > 5:
        out["US_FUT:CL"] = {"atmIv": ovx / 100.0, "ivSource": "🟢 实盘IV(CBOE OVX)"}
        out["US_FUT:BZ"] = {"atmIv": ovx / 100.0, "ivSource": "🟢 实盘IV(CBOE OVX)"}
    if gvz and gvz > 5:
        out["US_STK:GLD"] = {"atmIv": gvz / 100.0, "ivSource": "🟢 实盘IV(CBOE GVZ)"}
        out["US_FUT:GC"] = {"atmIv": gvz / 100.0, "ivSource": "🟢 实盘IV(CBOE GVZ)"}

    # Fetch CFFEX MO / IO / HO real option chain IVs synchronously (fast <0.3s via Sina)
    for cid in ("CN_FUT:IM0", "CN_FUT:IF0", "CN_FUT:IH0"):
        try:
            ch = fetch_live_option_chain_sample(cid, target_dte=target_dte)
            iv_val = _extract_atm_iv_from_chain(ch)
            if iv_val and 0.07 <= iv_val <= 1.20:
                out[cid] = {"atmIv": iv_val, "ivSource": f"🟢 实盘IV(中金所{ch.get('ticker','')})"}
        except Exception:
            pass

    # Load any cached US stock option chain IVs and trigger non-blocking background refresh if needed
    if not _US_IV_MEM:
        saved = load_pickle("real_us_iv_v1.pkl", max_age_sec=14400.0)
        if isinstance(saved, dict) and saved:
            _US_IV_MEM.update(saved)

    for iid, iv_val in list(_US_IV_MEM.items()):
        if iid not in out and 0.08 <= iv_val <= 1.60:
            out[iid] = {"atmIv": iv_val, "ivSource": "🟢 实盘IV(美股期权链)"}

    if not _US_IV_BG_STARTED and len(_US_IV_MEM) < 20:
        _US_IV_BG_STARTED = True
        threading.Thread(target=_bg_refresh_us_option_ivs, args=(target_dte,), daemon=True).start()

    return out
