# -*- coding: utf-8 -*-
"""HTTP client, Beijing time helpers, ISO week calendar, and thread-safe TTL + disk cache."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import pickle
import threading
import time
from typing import Any, Callable, Dict, Optional

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": UA})
_ADAPTER = requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=1)
_SESSION.mount("https://", _ADAPTER)
_SESSION.mount("http://", _ADAPTER)

BJ_TZ = timezone(timedelta(hours=8))
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def to_bj(dt_or_ts: Any = None) -> str:
    """Convert timestamp (sec or ms) or datetime to Beijing time string YYYY-MM-DD HH:MM:SS."""
    if dt_or_ts is None:
        dt = datetime.now(BJ_TZ)
    elif isinstance(dt_or_ts, (int, float)):
        ts = dt_or_ts / 1000.0 if dt_or_ts > 1e11 else float(dt_or_ts)
        dt = datetime.fromtimestamp(ts, tz=BJ_TZ)
    elif isinstance(dt_or_ts, datetime):
        dt = dt_or_ts.astimezone(BJ_TZ) if dt_or_ts.tzinfo else dt_or_ts.replace(tzinfo=BJ_TZ)
    else:
        return str(dt_or_ts)[:19]
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def now_bj() -> str:
    return to_bj(None)


def _third_friday(year: int, month: int) -> date:
    """Standard US monthly options expiration (3rd Friday of the month)."""
    d = date(year, month, 1)
    # weekday(): Monday=0 ... Friday=4
    days_to_fri = (4 - d.weekday()) % 7
    first_fri = d + timedelta(days=days_to_fri)
    return first_fri + timedelta(days=14)


def get_week_context(target_dte: int = 30) -> Dict[str, Any]:
    """Return dynamic weekly cycle metadata and option expiration targets."""
    now = datetime.now(BJ_TZ)
    today = now.date()
    iso_year, iso_week, iso_weekday = today.isocalendar()
    monday = today - timedelta(days=iso_weekday - 1)
    friday = monday + timedelta(days=4)

    # Target expiry date based on DTE
    raw_exp = today + timedelta(days=max(5, int(target_dte)))
    # Align to nearest Friday for weekly/monthly options realism
    days_to_fri = (4 - raw_exp.weekday()) % 7
    exp_friday = raw_exp + timedelta(days=days_to_fri)
    actual_dte = max(5, (exp_friday - today).days)

    # Also compute next monthly OPEX (3rd Friday)
    m_exp = _third_friday(today.year, today.month)
    if (m_exp - today).days < 12:
        ny = today.year + (1 if today.month == 12 else 0)
        nm = 1 if today.month == 12 else today.month + 1
        m_exp = _third_friday(ny, nm)

    return {
        "isoYear": iso_year,
        "isoWeek": iso_week,
        "weekLabel": f"{iso_year}年第{iso_week}周",
        "weekRange": f"{monday.strftime('%m.%d')} - {friday.strftime('%m.%d')}",
        "weekStart": monday.strftime("%Y-%m-%d"),
        "weekEnd": friday.strftime("%Y-%m-%d"),
        "today": today.strftime("%Y-%m-%d"),
        "targetDte": actual_dte,
        "targetExpiry": exp_friday.strftime("%Y-%m-%d"),
        "monthlyOpex": m_exp.strftime("%Y-%m-%d"),
        "monthlyOpexDte": (m_exp - today).days,
        "updatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


def fetch_text(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    encoding: Optional[str] = None,
    timeout: float = 7.0,
) -> str:
    resp = _SESSION.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    if encoding:
        return resp.content.decode(encoding, errors="replace")
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def fetch_json(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 7.0,
) -> Any:
    resp = _SESSION.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def parse_jsonp(text: str) -> Any:
    s = text.find("([")
    e = text.rfind("])")
    if s >= 0 and e > s:
        return json.loads(text[s + 1 : e + 1])
    s = text.find("(")
    e = text.rfind(")")
    if s >= 0 and e > s:
        return json.loads(text[s + 1 : e])
    return json.loads(text)


class _CacheEntry:
    __slots__ = ("value", "ts", "lock")

    def __init__(self) -> None:
        self.value: Any = None
        self.ts: float = 0.0
        self.lock = threading.Lock()


_STORE_LOCK = threading.Lock()
_STORE: Dict[str, _CacheEntry] = {}


def cached(key: str, ttl_sec: float, fn: Callable[[], Any], force: bool = False) -> Any:
    """Thread-safe TTL cache; returns stale value if refresh raises an exception."""
    now = time.time()
    with _STORE_LOCK:
        entry = _STORE.get(key)
        if entry is None:
            entry = _CacheEntry()
            _STORE[key] = entry

    if not force and entry.value is not None and (now - entry.ts) < ttl_sec:
        return entry.value

    with entry.lock:
        now = time.time()
        if not force and entry.value is not None and (now - entry.ts) < ttl_sec:
            return entry.value
        try:
            val = fn()
            entry.value = val
            entry.ts = time.time()
            return val
        except Exception:
            if entry.value is not None:
                return entry.value
            raise


def load_pickle(name: str, max_age_sec: float = 86400.0) -> Any:
    path = DATA_DIR / name
    if not path.exists():
        return None
    try:
        if time.time() - path.stat().st_mtime > max_age_sec:
            return None
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def save_pickle(name: str, obj: Any) -> None:
    path = DATA_DIR / name
    try:
        with open(path, "wb") as f:
            pickle.dump(obj, f)
    except Exception:
        pass
