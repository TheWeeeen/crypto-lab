"""Загрузка рыночных данных Binance с локальным кэшем. Только stdlib."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

SPOT = "https://api.binance.com"
FUT = "https://fapi.binance.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache")
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) crypto-lab/1.0"}

# секунд в интервале — для TTL кэша и аннуализации
INTERVALS = {
    "15m": 900, "30m": 1800, "1h": 3600, "2h": 7200,
    "4h": 14400, "6h": 21600, "12h": 43200, "1d": 86400, "1w": 604800,
}
PER_YEAR = {k: (365 * 86400) / v for k, v in INTERVALS.items()}

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                   "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "TONUSDT"]


@dataclass
class Bar:
    t: int          # открытие бара, ms epoch
    o: float
    h: float
    l: float
    c: float
    v: float

    @property
    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.t / 1000, timezone.utc)

    @property
    def date(self) -> str:
        return self.dt.strftime("%Y-%m-%d")


def _get(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _cache_path(symbol: str, interval: str, limit: int) -> str:
    return os.path.join(CACHE, f"{symbol}_{interval}_{limit}.json")


def _ttl(interval: str) -> int:
    """Свежие бары — короткий TTL, дневные — час."""
    return 300 if INTERVALS.get(interval, 86400) < 86400 else 3600


def fetch_klines(symbol: str, interval: str = "1d", limit: int = 1000,
                 use_cache: bool = True) -> list[Bar]:
    """Дневные/часовые свечи с Binance spot. limit<=1000 за один запрос."""
    if interval not in INTERVALS:
        raise ValueError(f"интервал {interval!r} не поддержан: {sorted(INTERVALS)}")
    os.makedirs(CACHE, exist_ok=True)
    path = _cache_path(symbol, interval, limit)
    if use_cache and os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < _ttl(interval):
            try:
                return [Bar(*row) for row in json.load(open(path))]
            except Exception:
                pass
    url = f"{SPOT}/api/v3/klines?symbol={symbol}&interval={interval}&limit={min(limit, 1000)}"
    raw = _get(url)
    bars = [Bar(int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5]))
            for x in raw]
    if bars:
        json.dump([[b.t, b.o, b.h, b.l, b.c, b.v] for b in bars], open(path, "w"))
    return bars


def fetch_klines_range(symbol: str, interval: str, start_ms: int, end_ms: int) -> list[Bar]:
    """Свечи за произвольный период (склейка по 1000)."""
    out: list[Bar] = []
    cur = start_ms
    while cur < end_ms:
        url = (f"{SPOT}/api/v3/klines?symbol={symbol}&interval={interval}"
               f"&startTime={cur}&endTime={end_ms}&limit=1000")
        raw = _get(url)
        if not raw:
            break
        for x in raw:
            out.append(Bar(int(x[0]), float(x[1]), float(x[2]), float(x[3]),
                           float(x[4]), float(x[5])))
        cur = int(raw[-1][0]) + INTERVALS[interval] * 1000
        if len(raw) < 1000:
            break
    return out


def fetch_funding(symbol: str, limit: int = 1000) -> list[dict]:
    """История выплат фандинга по перпетуалу."""
    raw = _get(f"{FUT}/fapi/v1/fundingRate?symbol={symbol}&limit={min(limit, 1000)}")
    return [{"t": int(x["fundingTime"]), "rate": float(x["fundingRate"]),
             "symbol": x["symbol"]} for x in raw]


def symbols() -> list[str]:
    """Пары USDT, отсортированные по обороту за сутки."""
    try:
        info = _get(f"{SPOT}/api/v3/exchangeInfo")
        tradable = {s["symbol"] for s in info["symbols"]
                    if s["quoteAsset"] == "USDT" and s["status"] == "TRADING"
                    and (s.get("isSpotTradingAllowed") or s.get("spotTradingAllowed"))}
        tick = _get(f"{SPOT}/api/v3/ticker/24hr")
        rows = [(t["symbol"], float(t["quoteVolume"])) for t in tick
                if t["symbol"] in tradable]
        rows.sort(key=lambda r: -r[1])
        out = [s for s, _ in rows[:250]]
        return out or list(DEFAULT_SYMBOLS)
    except Exception:
        return list(DEFAULT_SYMBOLS)


def load(symbol: str, interval: str = "1d", limit: int = 1000) -> list[Bar]:
    """Псевдоним для читаемости в CLI и API."""
    return fetch_klines(symbol, interval, limit)


def closes(bars: list[Bar]) -> list[float]:
    return [b.c for b in bars]


def price_now(symbol: str) -> float:
    return float(_get(f"{SPOT}/api/v3/ticker/price?symbol={symbol}")["price"])
