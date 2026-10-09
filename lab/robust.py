"""Проверка на случайность: сколько стратегий «работают» просто от подгонки.

Главный тест: если прогнать N случайных стратегий с той же частотой сделок,
какая доля из них покажет результат не хуже проверяемой? Это и есть p-value.
"""
from __future__ import annotations

import random
import statistics as st

from .data import Bar
from .engine import run_backtest


def random_signals(n: int, exposure: float, rnd: random.Random) -> list[float]:
    """Случайные позиции 0/1 с заданной долей времени в рынке."""
    return [1.0 if rnd.random() < exposure else 0.0 for _ in range(n)]


def permutation_test(bars: list[Bar], signals: list[float], *, trials: int = 300,
                     seed: int = 7, fee: float = 0.001, **kw) -> dict:
    """p-value: доля случайных стратегий той же экспозиции, обыгравших нашу."""
    real = run_backtest(bars, signals, fee=fee, **kw)
    exposure = max(0.01, real.exposure)
    rnd = random.Random(seed)
    better = 0
    sims = []
    for _ in range(trials):
        s = random_signals(len(bars), exposure, rnd)
        r = run_backtest(bars, s, fee=fee, **kw)
        sims.append(r.total_return)
        if r.total_return >= real.total_return:
            better += 1
    return {
        "real_return": real.total_return,
        "exposure": exposure,
        "trials": trials,
        "random_mean": st.mean(sims) if sims else 0.0,
        "random_best": max(sims) if sims else 0.0,
        "random_p95": sorted(sims)[int(0.95 * len(sims)) - 1] if sims else 0.0,
        "p_value": better / trials if trials else 1.0,
        "significant": (better / trials) < 0.05 if trials else False,
    }


def bootstrap_ci(rs: list[float], trials: int = 500, seed: int = 11,
                 lo: float = 0.05, hi: float = 0.95) -> dict:
    """Доверительный интервал среднего дохода за бар — перестановкой."""
    if not rs:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "includes_zero": True}
    rnd = random.Random(seed)
    means = []
    for _ in range(trials):
        sample = [rnd.choice(rs) for _ in rs]
        means.append(st.mean(sample))
    means.sort()
    a, b = means[int(lo * trials)], means[int(hi * trials) - 1]
    return {"mean": st.mean(rs), "lo": a, "hi": b,
            "includes_zero": a <= 0 <= b}


def multiple_testing_grid(bars: list[Bar], keys: list[str], *, fee: float = 0.001) -> dict:
    """Сколько стратегий из набора выглядят прибыльными и сколько это ожидаемо случайно."""
    from . import strategies as S
    results = []
    for k in keys:
        try:
            sig = S.build(k, bars)
            r = run_backtest(bars, sig, strategy=k, fee=fee)
            results.append({"key": k, "return": r.total_return,
                            "sharpe": r.summary()["sharpe"], "trades": len(r.trades)})
        except Exception as e:
            results.append({"key": k, "error": str(e)})
    ok = [r for r in results if "return" in r and r["return"] > 0]
    return {"tested": len(results), "profitable": len(ok),
            "expected_by_chance": round(len(results) * 0.5, 1),
            "results": sorted(results, key=lambda r: -r.get("return", -9))}
