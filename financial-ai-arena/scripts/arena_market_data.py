"""可选：从 Tushare Pro HTTP 拉最近收盘（无 pandas/tushare 依赖）；失败则回退漂移价。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


def _tushare_post(token: str, api_name: str, params: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps({"api_name": api_name, "token": token, "params": params}).encode("utf-8")
    req = urllib.request.Request(
        "http://api.tushare.pro",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def fetch_latest_daily_close(ts_code: str, token: str) -> tuple[float | None, str | None]:
    """返回最近一条日线收盘价；失败返回 (None, error)."""
    now = datetime.now(timezone.utc)
    end = now.strftime("%Y%m%d")
    start = (now - timedelta(days=120)).strftime("%Y%m%d")
    try:
        raw = _tushare_post(token, "daily", {"ts_code": ts_code, "start_date": start, "end_date": end})
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return None, repr(e)
    if raw.get("code") != 0:
        return None, str(raw.get("msg") or raw)
    data = raw.get("data") or {}
    fields: list[str] = list(data.get("fields") or [])
    items: list[list[Any]] = list(data.get("items") or [])
    if not fields or not items:
        return None, "empty daily"
    try:
        i_td = fields.index("trade_date")
        i_close = fields.index("close")
    except ValueError:
        return None, "missing fields"
    items.sort(key=lambda row: str(row[i_td]), reverse=True)
    last = items[0]
    try:
        return float(last[i_close]), None
    except (TypeError, ValueError, IndexError):
        return None, "bad close"


def fetch_initial_prices_tushare(symbols: list[str]) -> tuple[dict[str, float] | None, str | None]:
    """多标的并行式顺序请求；全部成功才返回 dict。"""
    token = (os.environ.get("TUSHARE_TOKEN") or "").strip()
    if not token:
        return None, None
    out: dict[str, float] = {}
    for sym in symbols:
        px, err = fetch_latest_daily_close(sym.strip(), token)
        if px is None or px <= 0:
            return None, err or f"no price for {sym}"
        out[sym.strip()] = round(px, 4)
    return out, None


def ddg_instant_summary(query: str, *, max_len: int = 900) -> str:
    """DuckDuckGo Instant Answer API，失败返回空串。"""
    try:
        import urllib.parse

        q = urllib.parse.quote(query[:200])
        url = f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "financial-ai-arena/1"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            j = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return ""
    abstract = (j.get("AbstractText") or "").strip()
    text = (j.get("Answer") or "").strip()
    related = j.get("RelatedTopics") or []
    bits = [abstract, text]
    if isinstance(related, list):
        for rt in related[:3]:
            if isinstance(rt, dict) and rt.get("Text"):
                bits.append(str(rt["Text"]))
    s = " ".join(x for x in bits if x).strip()
    return s[:max_len] if s else ""
