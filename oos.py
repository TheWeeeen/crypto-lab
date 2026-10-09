#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Честный тест «рисования»: линию рисуем на прошлом, торгуем на будущем.

Первая половина истории (500 дней) — «то, что видит трейдер, когда рисует».
Вторая половина (500 дней) — «то, что случилось после».
Если уровень/трендлайн, нарисованный на прошлом, обыгрывает удержание на будущем —
это реальный приём. Если нет — рисование работает только задним числом.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lab import data as D, engine, levels, robust, strategies as S
from full_run import COINS, FEE, INTERVAL, LIMIT, SLIP

TRIALS = 150
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


def rolling_support(bars, n: int = 100):
    """Без подглядывания: держим, пока цена выше минимума предыдущих n дней."""
    out = []
    for i, b in enumerate(bars):
        if i < n:
            out.append(0.0)
            continue
        lo = min(x.l for x in bars[i - n:i])
        out.append(1.0 if b.c > lo * 1.001 else 0.0)
    return out


def rolling_trend(bars, n: int = 100):
    """Без подглядывания: держим, пока цена выше средней за предыдущие n дней."""
    out = []
    for i, b in enumerate(bars):
        if i < n:
            out.append(0.0)
            continue
        ma = sum(x.c for x in bars[i - n:i]) / n
        out.append(1.0 if b.c > ma else 0.0)
    return out


def main() -> None:
    report = {}
    print(f"{'монета':<9}{'приём':<26}{'итог':>9}{'держать':>10}{'разница':>10}{'сделок':>8}{'p':>7}")
    for sym in COINS:
        bars = D.fetch_klines(sym, INTERVAL, LIMIT)
        if not bars or len(bars) < 400:
            continue
        cut = len(bars) // 2
        A, B = bars[:cut], bars[cut:]
        base = B[-1].c / B[0].c - 1
        coin = {"train": f"{A[0].date} → {A[-1].date}", "test": f"{B[0].date} → {B[-1].date}",
                "hold_test": base, "rules": []}

        rules = []
        # 1) уровни, найденные на первой половине, торгуем на второй
        for n, l in enumerate(levels.cluster_levels(A, k=5, tol=0.02)[:3], 1):
            rules.append((f"уровень{n} {l['price']:.0f} отскок",
                          S.level_breakout(B, l["price"], "down"), l["price"]))
            rules.append((f"уровень{n} {l['price']:.0f} пробой",
                          S.level_breakout(B, l["price"], "up"), l["price"]))
        # 2) трендлайн с первой половины, торгуем на второй
        for n, t in enumerate(levels.fit_trendlines(A, k=5)[:2], 1):
            rules.append((f"трендлайн{n} пробой",
                          S.trendline_break(B, t["i1"] - cut, t["p1"],
                                            t["i2"] - cut, t["p2"], "up"), None))
        # 3) правила без подглядывания вообще
        rules.append(("поддержка 100д (скольз.)", rolling_support(B, 100), None))
        rules.append(("средняя 100д (скольз.)", rolling_trend(B, 100), None))
        rules.append(("средняя 200д (скольз.)", rolling_trend(B, 200), None))
        rules.append(("Дончиан 20", S.donchian_breakout(B, 20), None))
        rules.append(("моментум 30", S.momentum(B, 30), None))

        for name, sig, lvl in rules:
            try:
                r = engine.run_backtest(B, sig, symbol=sym, interval=INTERVAL,
                                        strategy=name, fee=FEE, slippage=SLIP)
                s = r.summary()
                p = robust.permutation_test(B, sig, trials=TRIALS, fee=FEE, slippage=SLIP)
                coin["rules"].append({"rule": name, "level": lvl, "return": s["total_return"],
                                      "excess": s["excess"], "trades": s["trades"],
                                      "p_value": p["p_value"],
                                      "significant": p["significant"]})
                print(f"{sym:<9}{name:<26}{s['total_return']*100:>+8.1f}%{base*100:>+9.1f}%"
                      f"{s['excess']*100:>+9.1f}%{s['trades']:>8}{p['p_value']:>7.2f}"
                      f"{'  *' if p['significant'] else ''}")
            except Exception as e:
                print(f"{sym:<9}{name:<26} ошибка: {e}")
        report[sym] = coin

    path = os.path.join(OUT, "oos_drawing.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, default=str, indent=1)
    print(f"\nсохранено: {path}")


if __name__ == "__main__":
    main()
