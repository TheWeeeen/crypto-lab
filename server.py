#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crypto-lab HTTP-сервер: API для проверки гипотез + веб-интерфейс.

Только stdlib. Запуск:
    python3 server.py [--port 8097] [--host 127.0.0.1]

Авторизация: если задан LAB_TOKEN в окружении — требуется ?token=... или cookie lab_token.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
import urllib.parse
from dataclasses import asdict
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lab import data as D
from lab import engine, levels, metrics as M, robust, strategies as S

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
TOKEN = os.environ.get("LAB_TOKEN", "")
_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_LOCK = threading.Lock()


def cached(key: str, ttl: int, producer):
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    val = producer()
    with _CACHE_LOCK:
        _CACHE[key] = (now, val)
    return val


def _bars(symbol: str, interval: str, limit: int) -> list[D.Bar]:
    symbol = symbol.upper().replace("-", "").replace("/", "")
    if not symbol.endswith("USDT"):
        symbol += "USDT"
    limit = max(50, min(int(limit), 1000))
    return D.fetch_klines(symbol, interval, limit)


def _result_payload(r: engine.Result) -> dict:
    return {
        "summary": r.summary(),
        "equity": r.equity,
        "positions": r.positions,
        "benchmark_curve": [b.c / r.bars[0].c for b in r.bars],
        "trades": [asdict(t) for t in r.trades],
        "bars": [{"t": b.t, "o": b.o, "h": b.h, "l": b.l, "c": b.c, "v": b.v} for b in r.bars],
    }


# ---------------- API ----------------

def api_symbols(_q) -> dict:
    return {"symbols": D.symbols()}


def api_strategies(_q) -> dict:
    return {"strategies": S.registry()}


def api_bars(q) -> dict:
    bars = _bars(q.get("symbol", "BTCUSDT")[0], q.get("interval", "1d")[0],
                 q.get("limit", 1000)[0])
    return {"symbol": q.get("symbol", ["BTCUSDT"])[0].upper(),
            "interval": q.get("interval", ["1d"])[0],
            "bars": [{"t": b.t, "o": b.o, "h": b.h, "l": b.l, "c": b.c, "v": b.v}
                     for b in bars]}


def _bt_kw(q: dict) -> dict:
    def f(k, default=None):
        v = q.get(k, [None])[0]
        return float(v) if v not in (None, "") else default

    def i(k, default=None):
        v = q.get(k, [None])[0]
        return int(float(v)) if v not in (None, "") else default

    return {
        "fee": f("fee", 0.001) or 0.0,
        "slippage": f("slippage", 0.0) or 0.0,
        "stop_loss": f("stop"),
        "take_profit": f("tp"),
        "trailing_stop": f("trail"),
        "initial": f("capital", 1.0) or 1.0,
    }


def api_backtest(q) -> dict:
    symbol = q.get("symbol", ["BTCUSDT"])[0]
    interval = q.get("interval", ["1d"])[0]
    limit = q.get("limit", [1000])[0]
    bars = _bars(symbol, interval, limit)
    key = q.get("strategy", ["buy_hold"])[0]
    params = {}
    for k, v in q.items():
        if k in ("fast", "slow", "lookback", "n", "low", "high", "k", "window",
                 "price", "direction", "i1", "p1", "i2", "p2", "entry", "threshold",
                 "side"):
            params[k] = v[0]
    sig = S.build(key, bars, **params)
    r = engine.run_backtest(bars, sig, symbol=symbol, interval=interval,
                            strategy=key, params=params, **_bt_kw(q))
    return _result_payload(r)


def api_scan(q) -> dict:
    bars = _bars(q.get("symbol", ["BTCUSDT"])[0], q.get("interval", ["1d"])[0],
                 q.get("limit", [1000])[0])
    kw = _bt_kw(q)
    out = []
    for key in S.ALL_STRATEGIES:
        try:
            r = engine.run_backtest(bars, S.ALL_STRATEGIES[key](bars),
                                    strategy=key, interval=q.get("interval", ["1d"])[0], **kw)
            out.append(r.summary())
        except Exception as e:
            out.append({"strategy": key, "error": str(e)})
    out.sort(key=lambda s: -s.get("total_return", -9))
    return {"results": out}


def api_stops(q) -> dict:
    bars = _bars(q.get("symbol", ["BTCUSDT"])[0], q.get("interval", ["1d"])[0],
                 q.get("limit", [1000])[0])
    kw = {k: v for k, v in _bt_kw(q).items() if k in ("fee", "slippage", "initial")}
    base = bars[-1].c / bars[0].c - 1
    combos = [("без стопа", {}), ("стоп 3%", {"stop_loss": 0.03}),
              ("стоп 5%", {"stop_loss": 0.05}), ("стоп 10%", {"stop_loss": 0.10}),
              ("стоп 20%", {"stop_loss": 0.20}), ("трейлинг 5%", {"trailing_stop": 0.05}),
              ("трейлинг 10%", {"trailing_stop": 0.10}), ("трейлинг 20%", {"trailing_stop": 0.20}),
              ("стоп 5% + тейк 10%", {"stop_loss": 0.05, "take_profit": 0.10}),
              ("стоп 10% + тейк 20%", {"stop_loss": 0.10, "take_profit": 0.20})]
    sig = [1.0] * len(bars)
    rows = []
    for name, extra in combos:
        r = engine.run_backtest(bars, sig, strategy=name, **kw, **extra)
        rows.append({"rule": name, "return": r.total_return,
                     "vs_hold": r.total_return - base, "trades": len(r.trades),
                     "max_drawdown": M.max_drawdown(r.equity)})
    return {"benchmark": base, "results": rows}


def api_levels(q) -> dict:
    symbol = q.get("symbol", ["BTCUSDT"])[0]
    interval = q.get("interval", ["1d"])[0]
    limit = q.get("limit", [1000])[0]
    k = int(q.get("k", [5])[0])
    tol = float(q.get("tol", [0.02])[0])
    trials = int(q.get("trials", [60])[0])
    top = int(q.get("top", [12])[0])

    def build():
        bars = _bars(symbol, interval, limit)
        lv = levels.cluster_levels(bars, k=k, tol=tol)[:top]
        out = []
        for l in lv:
            st = levels.level_stats(bars, l["price"], tol=0.01)
            rnd = levels.level_hold_randomness(bars, l["price"], trials=trials)
            out.append({**l, **st, "p_value": rnd["p_value"],
                        "random_hold_rate": rnd["random_mean"]})
        return {"levels": out, "trials": trials}

    return cached(f"levels:{symbol}:{interval}:{limit}:{k}:{tol}:{trials}:{top}", 900, build)


def api_trendlines(q) -> dict:
    bars = _bars(q.get("symbol", ["BTCUSDT"])[0], q.get("interval", ["1d"])[0],
                 q.get("limit", [1000])[0])
    k = int(q.get("k", [5])[0])
    tl = levels.fit_trendlines(bars, k=k)
    for t in tl:
        t["t1"] = bars[t["i1"]].t
        t["t2"] = bars[t["i2"]].t
    return {"trendlines": tl}


def api_patterns(q) -> dict:
    bars = _bars(q.get("symbol", ["BTCUSDT"])[0], q.get("interval", ["1d"])[0],
                 q.get("limit", [1000])[0])
    horizon = int(q.get("horizon", [20])[0])
    res = levels.pattern_edge(bars, horizon=horizon)
    for p in res:
        if "i1" in p:
            p["t1"] = bars[p["i1"]].t
        if "i2" in p:
            p["t2"] = bars[p["i2"]].t
    return {"patterns": res, "horizon": horizon}


def api_robust(q) -> dict:
    bars = _bars(q.get("symbol", ["BTCUSDT"])[0], q.get("interval", ["1d"])[0],
                 q.get("limit", [1000])[0])
    key = q.get("strategy", ["ma_cross"])[0]
    trials = int(q.get("trials", [200])[0])
    params = {k: v[0] for k, v in q.items()
              if k in ("fast", "slow", "lookback", "n", "window", "entry",
                       "price", "direction", "side", "i1", "p1", "i2", "p2",
                       "low", "high", "threshold", "k")}
    sig = S.build(key, bars, **params)
    res = robust.permutation_test(bars, sig, trials=trials, fee=float(q.get("fee", [0.001])[0]))
    rs = [bars[i].c / bars[i - 1].c - 1 for i in range(1, len(bars))]
    ci = robust.bootstrap_ci(rs)
    base = bars[-1].c / bars[0].c - 1
    return {**res, "bootstrap": ci, "benchmark": base,
            "beats_benchmark": res["real_return"] > base}


def api_funding(q) -> dict:
    f = D.fetch_funding(q.get("symbol", ["BTCUSDT"])[0].upper(),
                        limit=int(q.get("limit", [500])[0]))
    if not f:
        return {"error": "нет данных"}
    rates = [x["rate"] for x in f]
    avg = sum(rates) / len(rates)
    return {"n": len(f), "avg": avg, "annual": avg * 3 * 365,
            "positive_share": sum(1 for r in rates if r > 0) / len(rates),
            "median": sorted(rates)[len(rates) // 2],
            "series": [{"t": x["t"], "rate": x["rate"]} for x in f[-200:]]}


ROUTES = {
    "/api/symbols": api_symbols,
    "/api/strategies": api_strategies,
    "/api/bars": api_bars,
    "/api/backtest": api_backtest,
    "/api/scan": api_scan,
    "/api/stops": api_stops,
    "/api/levels": api_levels,
    "/api/trendlines": api_trendlines,
    "/api/patterns": api_patterns,
    "/api/robust": api_robust,
    "/api/funding": api_funding,
}

MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
        ".json": "application/json; charset=utf-8", ".ico": "image/x-icon"}


class Handler(BaseHTTPRequestHandler):
    server_version = "crypto-lab/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # --- утилиты ---
    def _authed(self, q) -> bool:
        if not TOKEN:
            return True
        if q.get("token", [None])[0] == TOKEN:
            self._cookie = ("lab_token=%s; Path=/; SameSite=Lax; Max-Age=31536000" % TOKEN)
            return True
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return bool(cookie.get("lab_token") and cookie["lab_token"].value == TOKEN)

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        extra = dict(extra or {})
        if getattr(self, "_cookie", None) and "Set-Cookie" not in extra:
            extra["Set-Cookie"] = self._cookie
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode(),
                   "application/json; charset=utf-8")

    def _static(self, path: str):
        rel = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(WEB, rel))
        if not full.startswith(WEB):
            return self._send(403, b"forbidden", "text/plain")
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.exists(full):
            return self._send(404, b"not found", "text/plain")
        ext = os.path.splitext(full)[1]
        with open(full, "rb") as fh:
            body = fh.read()
        # cookie ставится только после ввода кода (?token=...) — см. _authed.
        self._send(200, body, MIME.get(ext, "application/octet-stream"),
                   {"Cache-Control": "no-cache, must-revalidate"})

    # --- маршрутизация ---
    def do_GET(self):
        self._cookie = None
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)
        path = parsed.path
        if path.startswith("/api/"):
            if not self._authed(q):
                return self._json({"error": "unauthorized"}, 401)
            if path in ROUTES:
                try:
                    return self._json(ROUTES[path](q))
                except Exception as e:
                    traceback.print_exc()
                    return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            if path == "/api/health":
                return self._json({"ok": True, "cache": len(_CACHE)})
            return self._json({"error": "not found"}, 404)
        # статика отдаётся всегда: сам интерфейс не секрет, секретны данные и путь.
        self._authed(q)          # чтобы ?token=... сразу поставил cookie
        return self._static(path)

    def do_POST(self):
        self._cookie = None
        parsed = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(parsed.query)
        if not self._authed(q):
            return self._json({"error": "unauthorized"}, 401)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if body:
            try:
                payload = json.loads(body.decode())
                for k, v in payload.items():
                    q[k] = [str(v)]
            except Exception:
                pass
        if parsed.path in ROUTES:
            try:
                return self._json(ROUTES[parsed.path](q))
            except Exception as e:
                traceback.print_exc()
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
        self._json({"error": "not found"}, 404)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8097)
    a = p.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"crypto-lab на http://{a.host}:{a.port}  (токен: {'да' if TOKEN else 'нет'})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
