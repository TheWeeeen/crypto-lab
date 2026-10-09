"""Сигнальные функции: бары -> целевая позиция по каждому бару.

Каждая возвращает список длиной len(bars) со значениями 0 / 1 (или -1).
Все индикаторы считаются только по прошлым данным — без заглядывания вперёд.
"""
from __future__ import annotations

import math
import statistics as st

from .data import Bar


# ---------- индикаторы ----------

def sma(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    s = 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    k = 2 / (n + 1)
    prev = None
    for i, x in enumerate(xs):
        prev = x if prev is None else x * k + prev * (1 - k)
        if i >= n - 1:
            out[i] = prev
    return out


def rsi(xs: list[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    if len(xs) <= n:
        return out
    gains, losses = [], []
    for i in range(1, len(xs)):
        d = xs[i] - xs[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = st.mean(gains[:n])
    al = st.mean(losses[:n])
    for i in range(n, len(xs)):
        if i > n:
            ag = (ag * (n - 1) + gains[i - 1]) / n
            al = (al * (n - 1) + losses[i - 1]) / n
        rs = ag / al if al else float("inf")
        out[i] = 100 - 100 / (1 + rs)
    return out


def rolling_max(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    for i in range(n - 1, len(xs)):
        out[i] = max(xs[i - n + 1:i + 1])
    return out


def rolling_min(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    for i in range(n - 1, len(xs)):
        out[i] = min(xs[i - n + 1:i + 1])
    return out


def bollinger(xs: list[float], n: int = 20, k: float = 2.0):
    mid = sma(xs, n)
    up: list[float | None] = [None] * len(xs)
    dn: list[float | None] = [None] * len(xs)
    for i in range(n - 1, len(xs)):
        sd = st.pstdev(xs[i - n + 1:i + 1])
        up[i] = mid[i] + k * sd
        dn[i] = mid[i] - k * sd
    return dn, mid, up


# ---------- стратегии ----------

def buy_hold(bars: list[Bar]) -> list[float]:
    return [1.0] * len(bars)


def ma_cross(bars: list[Bar], fast: int = 20, slow: int = 50) -> list[float]:
    px = [b.c for b in bars]
    f, s = sma(px, fast), sma(px, slow)
    return [1.0 if (f[i] is not None and s[i] is not None and f[i] > s[i]) else 0.0
            for i in range(len(px))]


def price_vs_ma(bars: list[Bar], n: int = 200) -> list[float]:
    px = [b.c for b in bars]
    m = sma(px, n)
    return [1.0 if (m[i] is not None and px[i] > m[i]) else 0.0 for i in range(len(px))]


def momentum(bars: list[Bar], lookback: int = 30, threshold: float = 0.0) -> list[float]:
    px = [b.c for b in bars]
    out = [0.0] * len(px)
    for i in range(lookback, len(px)):
        out[i] = 1.0 if px[i] / px[i - lookback] - 1 > threshold else 0.0
    return out


def mean_reversion_rsi(bars: list[Bar], n: int = 14, low: float = 30, high: float = 70) -> list[float]:
    px = [b.c for b in bars]
    r = rsi(px, n)
    out = [0.0] * len(px)
    pos = 0.0
    for i in range(len(px)):
        if r[i] is None:
            out[i] = 0.0
            continue
        if pos == 0 and r[i] < low:
            pos = 1.0
        elif pos == 1 and r[i] > high:
            pos = 0.0
        out[i] = pos
    return out


def donchian_breakout(bars: list[Bar], n: int = 20) -> list[float]:
    px = [b.c for b in bars]
    hi = rolling_max(px, n)
    out = [0.0] * len(px)
    pos = 0.0
    for i in range(len(px)):
        if hi[i - 1] if i else None:
            if px[i] > hi[i - 1]:
                pos = 1.0
        out[i] = pos
    return out


def bollinger_reversion(bars: list[Bar], n: int = 20, k: float = 2.0) -> list[float]:
    px = [b.c for b in bars]
    dn, mid, up = bollinger(px, n, k)
    out = [0.0] * len(px)
    pos = 0.0
    for i in range(len(px)):
        if dn[i] is None:
            out[i] = 0.0
            continue
        if pos == 0 and px[i] < dn[i]:
            pos = 1.0
        elif pos == 1 and px[i] > mid[i]:
            pos = 0.0
        out[i] = pos
    return out


def grid(bars: list[Bar], levels: int = 10, window: int = 60) -> list[float]:
    """Сетка: доля позиции растёт, когда цена ниже среднего за window."""
    px = [b.c for b in bars]
    m = sma(px, window)
    out = [0.0] * len(px)
    for i in range(len(px)):
        if m[i] is None:
            continue
        dev = px[i] / m[i] - 1
        # от 0 (выше среднего) до 1 (на 20% ниже среднего)
        out[i] = max(0.0, min(1.0, -dev / 0.20))
    return out


def level_breakout(bars: list[Bar], price: float, direction: str = "up") -> list[float]:
    """Рисованный горизонтальный уровень: пробой вверх -> лонг, вниз -> выход."""
    px = [b.c for b in bars]
    out = [0.0] * len(px)
    pos = 0.0
    for i in range(len(px)):
        if direction == "up":
            if px[i] > price:
                pos = 1.0
            elif px[i] < price * 0.99:
                pos = 0.0
        else:
            if px[i] < price:
                pos = 1.0
            elif px[i] > price * 1.01:
                pos = 0.0
        out[i] = pos
    return out


def range_trade(bars: list[Bar], low: float, high: float) -> list[float]:
    """Рисованный канал: покупка у нижней границы, продажа у верхней."""
    px = [b.c for b in bars]
    out = [0.0] * len(px)
    pos = 0.0
    for i in range(len(px)):
        if pos == 0 and px[i] <= low:
            pos = 1.0
        elif pos == 1 and px[i] >= high:
            pos = 0.0
        out[i] = pos
    return out


def trendline_break(bars: list[Bar], i1: int, p1: float, i2: int, p2: float,
                    side: str = "up") -> list[float]:
    """Рисованный трендлайн через две точки (индекс, цена). Пробой -> позиция."""
    if i2 == i1:
        raise ValueError("точки трендлайна должны иметь разные индексы")
    slope = (p2 - p1) / (i2 - i1)
    px = [b.c for b in bars]
    out = [0.0] * len(px)
    pos = 0.0
    for i in range(len(px)):
        if i <= max(i1, i2):
            out[i] = 0.0
            continue
        line = p1 + slope * (i - i1)
        if side == "up":
            if px[i] > line:
                pos = 1.0
            elif px[i] < line * 0.98:
                pos = 0.0
        else:
            if px[i] < line:
                pos = 1.0
            elif px[i] > line * 1.02:
                pos = 0.0
        out[i] = pos
    return out


def fib_retracement(bars: list[Bar], lookback: int = 120, entry: float = 0.618) -> list[float]:
    """Покупка на откате к уровню Фибоначчи от максимума за lookback."""
    px = [b.c for b in bars]
    out = [0.0] * len(px)
    pos = 0.0
    for i in range(lookback, len(px)):
        hi = max(px[i - lookback:i])
        lo = min(px[i - lookback:i])
        if hi == lo:
            out[i] = pos
            continue
        level = hi - (hi - lo) * entry
        if pos == 0 and px[i] <= level:
            pos = 1.0
        elif pos == 1 and px[i] >= hi * 0.98:
            pos = 0.0
        out[i] = pos
    return out


def day_of_week(bars: list[Bar], days: set[int] | None = None) -> list[float]:
    """Держим позицию только по выбранным дням недели (0=Пн)."""
    days = days or {0}
    return [1.0 if b.dt.weekday() in days else 0.0 for b in bars]


ALL_STRATEGIES = {
    "buy_hold": buy_hold,
    "ma_cross_20_50": lambda b: ma_cross(b, 20, 50),
    "ma_cross_50_200": lambda b: ma_cross(b, 50, 200),
    "price_vs_ma200": lambda b: price_vs_ma(b, 200),
    "momentum_30": lambda b: momentum(b, 30),
    "momentum_90": lambda b: momentum(b, 90),
    "rsi_reversion": mean_reversion_rsi,
    "donchian_20": donchian_breakout,
    "bollinger_reversion": bollinger_reversion,
    "grid": grid,
    "fib_618": fib_retracement,
}


def registry() -> list[dict]:
    """Список стратегий для интерфейса."""
    return [
        {"key": "buy_hold", "label": "Купил и держу", "group": "База",
         "params": []},
        {"key": "ma_cross", "label": "Пересечение скользящих", "group": "Тренд",
         "params": [{"name": "fast", "label": "Быстрая MA", "default": 20},
                    {"name": "slow", "label": "Медленная MA", "default": 50}]},
        {"key": "price_vs_ma", "label": "Цена выше MA", "group": "Тренд",
         "params": [{"name": "n", "label": "Период MA", "default": 200}]},
        {"key": "momentum", "label": "Моментум", "group": "Тренд",
         "params": [{"name": "lookback", "label": "Окно, дней", "default": 30},
                    {"name": "threshold", "label": "Порог, %", "default": 0.0}]},
        {"key": "donchian", "label": "Пробой канала Дончиана", "group": "Пробой",
         "params": [{"name": "n", "label": "Окно", "default": 20}]},
        {"key": "rsi_reversion", "label": "RSI: возврат к среднему", "group": "Возврат",
         "params": [{"name": "n", "label": "Период RSI", "default": 14},
                    {"name": "low", "label": "Покупка ниже", "default": 30},
                    {"name": "high", "label": "Продажа выше", "default": 70}]},
        {"key": "bollinger_reversion", "label": "Боллинджер: возврат", "group": "Возврат",
         "params": [{"name": "n", "label": "Период", "default": 20},
                    {"name": "k", "label": "Отклонений", "default": 2}]},
        {"key": "grid", "label": "Сетка от средней", "group": "Возврат",
         "params": [{"name": "window", "label": "Окно средней", "default": 60}]},
        {"key": "fib", "label": "Фибоначчи-откат", "group": "Рисование",
         "params": [{"name": "lookback", "label": "Окно", "default": 120},
                    {"name": "entry", "label": "Уровень", "default": 0.618}]},
        {"key": "level_breakout", "label": "Пробой уровня (нарисованный)", "group": "Рисование",
         "params": [{"name": "price", "label": "Цена уровня", "default": 0},
                    {"name": "direction", "label": "Направление", "default": "up"}]},
        {"key": "trendline", "label": "Пробой трендлайна (нарисованный)", "group": "Рисование",
         "params": [{"name": "i1", "label": "Точка 1 (индекс)", "default": 0},
                    {"name": "p1", "label": "Цена 1", "default": 0},
                    {"name": "i2", "label": "Точка 2 (индекс)", "default": 0},
                    {"name": "p2", "label": "Цена 2", "default": 0}]},
        {"key": "range_trade", "label": "Канал: от границ", "group": "Рисование",
         "params": [{"name": "low", "label": "Низ канала", "default": 0},
                    {"name": "high", "label": "Верх канала", "default": 0}]},
    ]


def build(key: str, bars: list[Bar], **params) -> list[float]:
    """Собрать сигналы по ключу стратегии и параметрам."""
    p = {k: (float(v) if isinstance(v, str) and v.replace('.', '', 1).lstrip('-').isdigit() else v)
         for k, v in params.items()}
    if key == "buy_hold":
        return buy_hold(bars)
    if key == "ma_cross":
        return ma_cross(bars, int(p.get("fast", 20)), int(p.get("slow", 50)))
    if key == "price_vs_ma":
        return price_vs_ma(bars, int(p.get("n", 200)))
    if key == "momentum":
        return momentum(bars, int(p.get("lookback", 30)), float(p.get("threshold", 0)) / 100)
    if key == "donchian":
        return donchian_breakout(bars, int(p.get("n", 20)))
    if key == "rsi_reversion":
        return mean_reversion_rsi(bars, int(p.get("n", 14)),
                                  float(p.get("low", 30)), float(p.get("high", 70)))
    if key == "bollinger_reversion":
        return bollinger_reversion(bars, int(p.get("n", 20)), float(p.get("k", 2)))
    if key == "grid":
        return grid(bars, window=int(p.get("window", 60)))
    if key == "fib":
        return fib_retracement(bars, int(p.get("lookback", 120)), float(p.get("entry", 0.618)))
    if key == "level_breakout":
        return level_breakout(bars, float(p["price"]), str(p.get("direction", "up")))
    if key == "trendline":
        return trendline_break(bars, int(p["i1"]), float(p["p1"]),
                               int(p["i2"]), float(p["p2"]),
                               str(p.get("side", "up")))
    if key == "range_trade":
        return range_trade(bars, float(p["low"]), float(p["high"]))
    raise KeyError(f"неизвестная стратегия: {key}")
