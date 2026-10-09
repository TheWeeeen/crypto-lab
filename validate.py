#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка на устойчивость: те же способы отдельно на первой и второй половине истории.

Если способ работает по-настоящему, он должен обыгрывать удержание в обеих половинах
на нескольких монетах. Если превышение живёт только в одной половине — это подгонка/везение.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lab import data as D, engine, levels, robust, strategies as S
from full_run import COINS, FEE, INTERVAL, LIMIT, SLIP, extra_strategies

TRIALS = 100
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


def halves(bars):
    n = len(bars)
    return {"1-я половина": bars[: n // 2], "2-я половина": bars[n // 2:]}


def main() -> None:
    res: dict[str, list[dict]] = {}
    detail = {}
    for sym in COINS:
        bars = D.fetch_klines(sym, INTERVAL, LIMIT)
        if not bars:
            continue
        for hname, hb in halves(bars).items():
            base = hb[-1].c / hb[0].c - 1
            items = [(k, fn(hb), "") for k, fn in S.ALL_STRATEGIES.items()]
            items += extra_strategies(hb)
            for key, sig, note in items:
                try:
                    r = engine.run_backtest(hb, sig, symbol=sym, interval=INTERVAL,
                                            strategy=key, fee=FEE, slippage=SLIP)
                    s = r.summary()
                    p = robust.permutation_test(hb, sig, trials=TRIALS, fee=FEE, slippage=SLIP)
                    res.setdefault(key, []).append(
                        {"coin": sym, "half": hname, "excess": s["excess"],
                         "ret": s["total_return"], "base": base, "trades": s["trades"],
                         "p": p["p_value"]})
                    detail[f"{sym}|{hname}|{key}"] = {"excess": s["excess"], "p": p["p_value"]}
                except Exception as e:
                    res.setdefault(key, []).append({"coin": sym, "half": hname, "error": str(e)})
        print(f"  {sym}: готово", flush=True)

    print(f"\n{'способ':<22}{'половин':>8}{'лучше удерж.':>14}{'средн. превыш.':>16}{'p<0.05':>8}")
    rows = []
    for key, arr in res.items():
        ok = [x for x in arr if "excess" in x]
        if not ok:
            continue
        wins = sum(1 for x in ok if x["excess"] > 0)
        avg = sum(x["excess"] for x in ok) / len(ok)
        sig = sum(1 for x in ok if x["p"] < 0.05)
        rows.append((key, len(ok), wins, avg, sig))
    rows.sort(key=lambda r: (-r[2] / r[1], -r[3]))
    for key, n, wins, avg, sig in rows:
        print(f"{key:<22}{n:>8}{wins:>10}/{n:<3}{avg*100:>+15.1f}%{sig:>8}")

    path = os.path.join(OUT, "split_half.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"rows": rows, "detail": detail}, fh, ensure_ascii=False, default=str, indent=1)
    print(f"\nсохранено: {path}")


if __name__ == "__main__":
    main()
