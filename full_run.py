#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Полный прогон способов заработка на крипте за последние 1000 дней.

Что считает:
  1) все стратегии из реестра — доход, сравнение с «держать», Sharpe, просадка + тест на случайность (p-value);
  2) стопы/тейки/трейлинг против простого удержания;
  3) «рисование»: автоуровни с p-value, трендлайны, фигуры и их предсказательная сила;
  4) фандинг (ставки финансирования перпетуалов).
Результат: reports/full_<дата>.json + печать сводки.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lab import data as D
from lab import engine, levels, robust, strategies as S

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
INTERVAL = "1d"
LIMIT = 1000
FEE = 0.001          # taker 0,1%
SLIP = 0.0005        # проскальзывание 0,05%
TRIALS = 200         # прогонов для теста на случайность
LEVEL_TRIALS = 100

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "reports")
os.makedirs(OUT, exist_ok=True)
STAMP = time.strftime("%Y%m%d")
JSON_PATH = os.path.join(OUT, f"full_{STAMP}.json")

KEEP = ("total_return", "benchmark_return", "excess", "cagr", "vol", "sharpe",
        "sortino", "max_drawdown", "trades", "win_rate", "avg_trade",
        "fees_paid", "exposure", "final_equity", "bars", "from", "to")


def log(*a) -> None:
    print(*a, flush=True)


def save(obj) -> None:
    with open(JSON_PATH, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, default=str, indent=1)


def stop_rules():
    rules = [("без стопа", None, None, None)]
    for sl in (0.03, 0.05, 0.10, 0.20):
        rules.append((f"стоп {sl:.0%}", sl, None, None))
    for tr in (0.05, 0.10, 0.20):
        rules.append((f"трейлинг {tr:.0%}", None, None, tr))
    for sl, tp in ((0.05, 0.10), (0.10, 0.20), (0.10, 0.30)):
        rules.append((f"стоп {sl:.0%} + тейк {tp:.0%}", sl, tp, None))
    return rules


def extra_strategies(bars):
    """Способы, которые строятся по данным без подглядывания в будущее."""
    out = []
    # 1) автоуровни: пробой вверх найденного уровня (уровень считается по всей истории,
    #    но это не подгонка под результат — кластеры экстремумов)
    try:
        lv = levels.cluster_levels(bars, k=5, tol=0.02)
        for n, l in enumerate(lv[:3], 1):
            out.append((f"автоуровень{n}_пробой",
                        S.level_breakout(bars, l["price"], "up"),
                        f"уровень {l['price']:.0f} ({l['touches']} касаний)"))
            out.append((f"автоуровень{n}_отскок",
                        S.level_breakout(bars, l["price"], "down"),
                        f"уровень {l['price']:.0f}"))
    except Exception as e:
        log(f"    автоуровни: ошибка {e}")
    # 2) автотрендлайны
    try:
        for n, t in enumerate(levels.fit_trendlines(bars, k=5)[:2], 1):
            out.append((f"автотрендлайн{n}_пробой",
                        S.trendline_break(bars, t["i1"], t["p1"], t["i2"], t["p2"], "up"),
                        f"{t['kind']} {t['p1']:.0f}→{t['p2']:.0f}"))
    except Exception as e:
        log(f"    автотрендлайны: ошибка {e}")
    # 3) канал: границы по первым 200 барам (без подглядывания), дальше не меняются
    try:
        head = bars[:200]
        lo = sorted(b.l for b in head)[int(len(head) * 0.1)]
        hi = sorted(b.h for b in head)[int(len(head) * 0.9)]
        out.append(("канал_10_90", S.range_trade(bars, lo, hi),
                    f"границы {lo:.0f}–{hi:.0f} по первым 200 дням"))
    except Exception as e:
        log(f"    канал: ошибка {e}")
    # 4) дни недели
    for d, name in enumerate(["пн", "вт", "ср", "чт", "пт", "сб", "вс"]):
        out.append((f"только_{name}", S.day_of_week(bars, {d}), f"позиция по {name}"))
    return out


def main() -> None:
    t0 = time.time()
    rep = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "interval": INTERVAL, "limit": LIMIT,
        "fee": FEE, "slippage": SLIP, "trials": TRIALS,
        "coins": {},
    }
    for sym in COINS:
        log(f"\n=== {sym} ===")
        bars = D.fetch_klines(sym, INTERVAL, LIMIT)
        if not bars:
            log("  нет данных — пропуск")
            continue
        base = bars[-1].c / bars[0].c - 1
        coin = {"bars": len(bars), "from": bars[0].date, "to": bars[-1].date,
                "price_from": bars[0].c, "price_to": bars[-1].c,
                "benchmark": base, "strategies": [], "stops": [],
                "levels": [], "trendlines": [], "patterns": [], "funding": None}
        log(f"  {bars[0].date} → {bars[-1].date} · держать {base*100:+.1f}%")

        # 1) стратегии + тест на случайность
        def test(key: str, sig, note: str = "") -> None:
            try:
                r = engine.run_backtest(bars, sig, symbol=sym, interval=INTERVAL,
                                        strategy=key, fee=FEE, slippage=SLIP)
                s = r.summary()
                p = robust.permutation_test(bars, sig, trials=TRIALS, fee=FEE, slippage=SLIP)
                coin["strategies"].append(
                    {"key": key, "note": note, **{k: s[k] for k in KEEP if k in s},
                     "p_value": p["p_value"], "significant": p["significant"],
                     "random_mean": p["random_mean"], "random_p95": p["random_p95"]})
                log(f"    {key:<20} {s['total_return']*100:+8.1f}%  "
                    f"vs держать {s['excess']*100:+7.1f}%  сделок {s['trades']:>4}  "
                    f"p={p['p_value']:.3f}{'  ЗНАЧИМО' if p['significant'] else ''}")
            except Exception as e:
                coin["strategies"].append({"key": key, "note": note,
                                           "error": f"{type(e).__name__}: {e}"})
                log(f"    {key:<20} ошибка: {e}")

        for key, fn in S.ALL_STRATEGIES.items():
            test(key, fn(bars))
        for key, sig, note in extra_strategies(bars):
            test(key, sig, note)

        # 2) стопы и тейки
        sig_all = [1.0] * len(bars)
        for name, sl, tp, tr in stop_rules():
            r = engine.run_backtest(bars, sig_all, symbol=sym, interval=INTERVAL,
                                    strategy=name, fee=FEE, slippage=SLIP,
                                    stop_loss=sl, take_profit=tp, trailing_stop=tr)
            s = r.summary()
            coin["stops"].append({"rule": name, "return": s["total_return"],
                                  "trades": s["trades"], "max_drawdown": s["max_drawdown"],
                                  "excess": s["excess"]})
        log("    стопы: " + ", ".join(
            f"{x['rule']} {x['return']*100:+.0f}%" for x in coin["stops"]))

        # 3) уровни с p-value
        try:
            lv = levels.cluster_levels(bars, k=5, tol=0.02)
            for l in lv[:6]:
                st = levels.level_stats(bars, l["price"], tol=0.01)
                rnd = levels.level_hold_randomness(bars, l["price"], trials=LEVEL_TRIALS)
                coin["levels"].append({"price": l["price"], "touches": l["touches"],
                                       "hold_rate": st["hold_rate"],
                                       "broke_up": st["broke_up"], "broke_down": st["broke_down"],
                                       "p_value": rnd["p_value"]})
            log(f"    уровней: {len(coin['levels'])}, "
                f"p-value от {min(x['p_value'] for x in coin['levels']):.2f} "
                f"до {max(x['p_value'] for x in coin['levels']):.2f}"
                if coin["levels"] else "    уровней нет")
        except Exception as e:
            log(f"    уровни: ошибка {e}")

        # 4) трендлайны
        try:
            tl = levels.fit_trendlines(bars, k=5)
            coin["trendlines"] = [{"kind": t["kind"], "touches": t["touches"],
                                   "breaks": t["breaks"], "score": t["score"],
                                   "from": bars[t["i1"]].date, "to": bars[t["i2"]].date,
                                   "p1": t["p1"], "p2": t["p2"]} for t in tl[:5]]
            log(f"    трендлайнов: {len(tl)}")
        except Exception as e:
            log(f"    трендлайны: ошибка {e}")

        # 5) фигуры
        try:
            pat = levels.pattern_edge(bars, horizon=20)
            coin["patterns"] = pat
            total = next((p for p in pat if p.get("name") == "ИТОГО"), None)
            if total:
                log(f"    фигур: {total['n']}, ход {total['fwd']*100:+.1f}% "
                    f"против базы {total['base']*100:+.1f}% "
                    f"(превышение {total['edge_vs_base']*100:+.1f} п.п.)")
        except Exception as e:
            log(f"    фигуры: ошибка {e}")

        # 6) фандинг
        try:
            f = D.fetch_funding(sym, limit=500)
            if f:
                rates = [x["rate"] for x in f]
                avg = sum(rates) / len(rates)
                coin["funding"] = {"n": len(f), "avg": avg, "annual": avg * 3 * 365,
                                   "positive_share": sum(1 for r in rates if r > 0) / len(rates)}
                log(f"    фандинг: {avg*3*365*100:+.2f}% годовых, "
                    f"положительных {coin['funding']['positive_share']*100:.0f}%")
        except Exception as e:
            log(f"    фандинг: ошибка {e}")

        rep["coins"][sym] = coin
        save(rep)
        log(f"  сохранено: {JSON_PATH}  ({time.time()-t0:.0f} с)")

    # сводка
    log("\n\n=== СВОДКА: что переигрывает простое удержание (по всем монетам) ===")
    tally: dict[str, list[float]] = {}
    for sym, coin in rep["coins"].items():
        for row in coin["strategies"]:
            if "total_return" in row:
                tally.setdefault(row["key"], []).append(row["excess"])
    for key, ex in sorted(tally.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        avg = sum(ex) / len(ex)
        wins = sum(1 for x in ex if x > 0)
        log(f"  {key:<18} средн. превышение {avg*100:+7.1f}%  "
            f"лучше удержания на {wins} из {len(ex)} монет")
    log(f"\nвсего {time.time()-t0:.0f} с")
    save(rep)


if __name__ == "__main__":
    main()
