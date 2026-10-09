"""Метрики доходности и риска. Чистый Python, без numpy."""
from __future__ import annotations

import math
import statistics as st

from .data import PER_YEAR


def returns(prices: list[float]) -> list[float]:
    return [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices)) if prices[i - 1]]


def mean(xs: list[float]) -> float:
    return st.mean(xs) if xs else 0.0


def stdev(xs: list[float]) -> float:
    return st.pstdev(xs) if len(xs) > 1 else 0.0


def ann_return(rs: list[float], interval: str = "1d") -> float:
    """Геометрический годовой доход из списка доходностей за бар."""
    if not rs:
        return 0.0
    total = 1.0
    for r in rs:
        total *= (1 + r)
    years = len(rs) / PER_YEAR.get(interval, 365)
    if years <= 0 or total <= 0:
        return 0.0
    return total ** (1 / years) - 1


def ann_vol(rs: list[float], interval: str = "1d") -> float:
    return stdev(rs) * math.sqrt(PER_YEAR.get(interval, 365))


def sharpe(rs: list[float], rf: float = 0.0, interval: str = "1d") -> float:
    sd = stdev(rs)
    if not sd:
        return 0.0
    return (mean(rs) - rf / PER_YEAR.get(interval, 365)) / sd * math.sqrt(PER_YEAR.get(interval, 365))


def sortino(rs: list[float], interval: str = "1d") -> float:
    down = [r for r in rs if r < 0]
    dd = stdev(down)
    if not dd:
        return 0.0
    return mean(rs) / dd * math.sqrt(PER_YEAR.get(interval, 365))


def max_drawdown(equity: list[float]) -> float:
    peak = equity[0] if equity else 1.0
    worst = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak:
            worst = min(worst, v / peak - 1)
    return worst


def drawdown_series(equity: list[float]) -> list[float]:
    peak = equity[0] if equity else 1.0
    out = []
    for v in equity:
        peak = max(peak, v)
        out.append(v / peak - 1 if peak else 0.0)
    return out


def calmar(equity: list[float], rs: list[float], interval: str = "1d") -> float:
    mdd = abs(max_drawdown(equity))
    return ann_return(rs, interval) / mdd if mdd else 0.0


def autocorr(xs: list[float], lag: int = 1) -> float:
    if len(xs) <= lag:
        return 0.0
    a, b = xs[:-lag], xs[lag:]
    ma, mb = mean(a), mean(b)
    num = sum((p - ma) * (q - mb) for p, q in zip(a, b))
    den = math.sqrt(sum((p - ma) ** 2 for p in a) * sum((q - mb) ** 2 for q in b))
    return num / den if den else 0.0


def corr(x: list[float], y: list[float]) -> float:
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    x, y = x[-n:], y[-n:]
    mx, my = mean(x), mean(y)
    num = sum((p - mx) * (q - my) for p, q in zip(x, y))
    den = math.sqrt(sum((p - mx) ** 2 for p in x) * sum((q - my) ** 2 for q in y))
    return num / den if den else 0.0


def t_stat(xs: list[float]) -> float:
    """t-статистика среднего против нуля: |t|>2 — примерно значимо."""
    sd = stdev(xs)
    if not sd or not xs:
        return 0.0
    return mean(xs) / (sd / math.sqrt(len(xs)))


def percentiles(xs: list[float], ps=(5, 25, 50, 75, 95)) -> dict[int, float]:
    if not xs:
        return {}
    s = sorted(xs)
    out = {}
    for p in ps:
        idx = min(len(s) - 1, max(0, int(round(p / 100 * (len(s) - 1)))))
        out[p] = s[idx]
    return out


def fmt_pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:+.{digits}f}%"


def fmt_money(x: float, cur: str = "₽") -> str:
    return f"{x:,.0f} {cur}".replace(",", " ")
