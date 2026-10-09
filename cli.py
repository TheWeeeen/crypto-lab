#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crypto-lab CLI — консольная версия для агента и терминала.

Примеры:
  python3 cli.py scan  --symbol BTCUSDT
  python3 cli.py bt    --symbol ETHUSDT --strategy ma_cross --fast 20 --slow 50 --stop 0.05
  python3 cli.py stops --symbol BTCUSDT
  python3 cli.py levels --symbol BTCUSDT
  python3 cli.py trendlines --symbol BTCUSDT
  python3 cli.py patterns --symbol BTCUSDT
  python3 cli.py robust --symbol BTCUSDT --strategy ma_cross
  python3 cli.py funding --symbol BTCUSDT
  python3 cli.py json --symbol BTCUSDT --strategy buy_hold
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lab import data as D
from lab import engine, levels, metrics as M, robust, strategies as S


def _pct(x: float, d: int = 1) -> str:
    return f"{x * 100:+.{d}f}%"


def _row(label: str, value: str, width: int = 26) -> str:
    return f"  {label:<{width}} {value}"


def load(args) -> list[D.Bar]:
    bars = D.fetch_klines(args.symbol.upper(), args.interval, args.limit)
    if not bars:
        print("нет данных", file=sys.stderr)
        sys.exit(1)
    return bars


def _header(bars: list[D.Bar], symbol: str, interval: str) -> None:
    print(f"=== {symbol.upper()} {interval} · {len(bars)} баров · "
          f"{bars[0].date} → {bars[-1].date}")
    print(_row("цена", f"{bars[0].c:,.0f} → {bars[-1].c:,.0f} $".replace(",", " ")))
    print(_row("купил и держу", _pct(bars[-1].c / bars[0].c - 1)))


def cmd_scan(args) -> None:
    bars = load(args)
    _header(bars, args.symbol, args.interval)
    print()
    rows = []
    for key in S.ALL_STRATEGIES:
        try:
            sig = S.ALL_STRATEGIES[key](bars)
            r = engine.run_backtest(bars, sig, symbol=args.symbol, interval=args.interval,
                                    strategy=key, fee=args.fee)
            s = r.summary()
            rows.append((key, s))
        except Exception as e:
            rows.append((key, {"error": str(e)}))
    rows.sort(key=lambda kv: -kv[1].get("total_return", -9))
    print(f"{'стратегия':<22}{'итог':>10}{'vs держать':>12}{'Sharpe':>9}{'просадка':>10}{'сделок':>8}")
    for key, s in rows:
        if "error" in s:
            print(f"{key:<22}{'ошибка':>10}")
            continue
        print(f"{key:<22}{_pct(s['total_return']):>10}{_pct(s['excess']):>12}"
              f"{s['sharpe']:>9.2f}{_pct(s['max_drawdown']):>10}{s['trades']:>8}")
    if args.json:
        print(json.dumps({k: v for k, v in rows}, ensure_ascii=False))


def cmd_bt(args) -> None:
    bars = load(args)
    params = {k: v for k, v in vars(args).items()
              if k in ("fast", "slow", "lookback", "n", "low", "high", "k",
                       "window", "price", "direction", "i1", "p1", "i2", "p2",
                       "entry", "threshold") and v is not None}
    sig = S.build(args.strategy, bars, **params)
    r = engine.run_backtest(bars, sig, symbol=args.symbol, interval=args.interval,
                            strategy=args.strategy, params=params, fee=args.fee,
                            stop_loss=args.stop, take_profit=args.tp,
                            trailing_stop=args.trail, initial=args.capital)
    s = r.summary()
    _header(bars, args.symbol, args.interval)
    print()
    print(f"  стратегия: {args.strategy}  {params if params else ''}"
          + (f"  стоп {args.stop:.0%}" if args.stop else "")
          + (f"  трейлинг {args.trail:.0%}" if args.trail else "")
          + (f"  тейк {args.tp:.0%}" if args.tp else ""))
    print(_row("итог стратегии", f"{s['total_return']*100:+.1f}%  "
                                 f"({s['final_equity']*args.capital:,.0f} ₽)".replace(",", " ")))
    print(_row("купил и держу", _pct(s["benchmark_return"])))
    print(_row("разница", _pct(s["excess"])))
    print(_row("годовых (CAGR)", _pct(s["cagr"])))
    print(_row("волатильность", _pct(s["vol"])))
    print(_row("Sharpe / Sortino", f"{s['sharpe']:.2f} / {s['sortino']:.2f}"))
    print(_row("макс. просадка", _pct(s["max_drawdown"])))
    print(_row("сделок / выигрышных", f"{s['trades']} / {s['win_rate']*100:.0f}%"))
    print(_row("средняя сделка", _pct(s["avg_trade"])))
    print(_row("уплачено комиссий", _pct(-s["fees_paid"])))
    print(_row("время в рынке", _pct(s["exposure"])))
    if args.json:
        print(json.dumps({**s, "equity": r.equity[-5:],
                          "trades_sample": [t.__dict__ for t in r.trades[:10]]},
                         ensure_ascii=False, default=str))


def cmd_stops(args) -> None:
    bars = load(args)
    _header(bars, args.symbol, args.interval)
    print("\n  Проверка стоп-лоссов (вход в начале периода, доля капитала):")
    print(f"  {'правило':<30}{'итог':>10}{'vs держать':>12}")
    base = bars[-1].c / bars[0].c - 1
    combos = [("без стопа", None, None, None)]
    for sl in (0.03, 0.05, 0.10, 0.20):
        combos.append((f"стоп {sl:.0%}", sl, None, None))
    for sl in (0.05, 0.10, 0.20):
        combos.append((f"трейлинг {sl:.0%}", None, None, sl))
    for sl, tp in ((0.05, 0.10), (0.10, 0.20), (0.10, 0.30)):
        combos.append((f"стоп {sl:.0%} + тейк {tp:.0%}", sl, tp, None))
    sig = [1.0] * len(bars)
    out = []
    for name, sl, tp, tr in combos:
        r = engine.run_backtest(bars, sig, symbol=args.symbol, interval=args.interval,
                                strategy=name, fee=args.fee, stop_loss=sl,
                                take_profit=tp, trailing_stop=tr)
        s = r.summary()
        out.append({"rule": name, "return": s["total_return"], "trades": s["trades"]})
        print(f"  {name:<30}{_pct(s['total_return']):>10}{_pct(s['total_return']-base):>12}")
    if args.json:
        print(json.dumps(out, ensure_ascii=False))


def cmd_levels(args) -> None:
    bars = load(args)
    _header(bars, args.symbol, args.interval)
    lv = levels.cluster_levels(bars, k=args.k, tol=args.tol)
    print(f"\n  Найдено уровней: {len(lv)} (кластеры локальных экстремумов, "
          f"допуск {args.tol:.1%})")
    print(f"  {'цена':>10}{'касаний':>9}{'держит':>9}{'вверх':>8}{'вниз':>8}{'p-value':>10}")
    out = []
    for l in lv[:args.top]:
        st_ = levels.level_stats(bars, l["price"], tol=0.01)
        rnd = levels.level_hold_randomness(bars, l["price"], trials=args.trials)
        out.append({**l, **st_, "p_value": rnd["p_value"]})
        print(f"  {l['price']:>10,.0f}{l['touches']:>9}{st_['hold_rate']*100:>8.0f}%"
              f"{st_['broke_up']:>8}{st_['broke_down']:>8}{rnd['p_value']:>10.2f}"
              .replace(",", " "))
    print("\n  p-value > 0.05 — уровень не отличается от случайного блуждания.")
    if args.json:
        print(json.dumps(out, ensure_ascii=False))


def cmd_trendlines(args) -> None:
    bars = load(args)
    _header(bars, args.symbol, args.interval)
    tl = levels.fit_trendlines(bars, k=args.k)
    print(f"\n  Линий: {len(tl)}")
    for t in tl:
        print(f"  {t['kind']:<11} от {bars[t['i1']].date} ({t['p1']:,.0f}) → "
              f"{bars[t['i2']].date} ({t['p2']:,.0f})  касаний {t['touches']}, "
              f"пробоев {t['breaks']}, счёт {t['score']}".replace(",", " "))
    if args.json:
        print(json.dumps(tl, ensure_ascii=False))


def cmd_patterns(args) -> None:
    bars = load(args)
    _header(bars, args.symbol, args.interval)
    res = levels.pattern_edge(bars, horizon=args.horizon)
    print(f"\n  Фигуры и ход цены через {args.horizon} дней:")
    for p in res:
        if p.get("name") == "ИТОГО":
            print(f"  ИТОГО: {p['n']} фигур, средний ход {_pct(p['fwd'])}, "
                  f"превышение над базой {_pct(p['edge_vs_base'])} (база {_pct(p['base'])})")
        else:
            print(f"  {p['name']:<22} {bars[p.get('i1', 0)].date} → "
                  f"ход {_pct(p.get('fwd', 0))}  превышение {_pct(p.get('edge_vs_base', 0))}")
    if args.json:
        print(json.dumps(res, ensure_ascii=False, default=str))


def cmd_robust(args) -> None:
    bars = load(args)
    sig = S.build(args.strategy, bars)
    _header(bars, args.symbol, args.interval)
    print(f"\n  Стратегия {args.strategy}: тест на случайность ({args.trials} прогонов)")
    res = robust.permutation_test(bars, sig, trials=args.trials, fee=args.fee)
    print(_row("доход стратегии", _pct(res["real_return"])))
    print(_row("средний случайный", _pct(res["random_mean"])))
    print(_row("лучший случайный", _pct(res["random_best"])))
    print(_row("95-й перцентиль случайных", _pct(res["random_p95"])))
    print(_row("p-value", f"{res['p_value']:.3f}"))
    print(_row("значимо (p<0.05)", "да" if res["significant"] else "НЕТ"))
    ci = robust.bootstrap_ci([b.c for b in bars] and
                             [bars[i].c / bars[i-1].c - 1 for i in range(1, len(bars))])
    print(_row("средний доход за бар", f"{ci['mean']*100:+.3f}%  "
                                       f"ДИ [{ci['lo']*100:+.3f}%, {ci['hi']*100:+.3f}%]"))
    print(_row("интервал включает ноль", "да — эджа нет" if ci["includes_zero"] else "нет"))
    if args.json:
        print(json.dumps({**res, "bootstrap": ci}, ensure_ascii=False))


def cmd_funding(args) -> None:
    f = D.fetch_funding(args.symbol.upper(), limit=args.limit)
    if not f:
        print("нет данных по фандингу")
        return
    rates = [x["rate"] for x in f]
    avg = sum(rates) / len(rates)
    ann = avg * 3 * 365  # 3 выплаты в сутки
    print(f"=== {args.symbol.upper()} фандинг · {len(f)} выплат")
    print(_row("средняя ставка за выплату", f"{avg*100:+.4f}%"))
    print(_row("в год (3 выплаты/сутки)", f"{ann*100:+.2f}%"))
    print(_row("положительных выплат", f"{sum(1 for r in rates if r>0)/len(rates)*100:.0f}%"))
    print(_row("медиана", f"{sorted(rates)[len(rates)//2]*100:+.4f}%"))
    print("\n  Карри = лонг спот + шорт перп. Годовой доход ≈ ставка фандинга")
    print("  минус комиссии (вход+выход) и минус спред между спот и перп.")
    if args.json:
        print(json.dumps({"avg": avg, "annual": ann, "n": len(f)}, ensure_ascii=False))


def cmd_json(args) -> None:
    bars = load(args)
    sig = S.build(args.strategy, bars)
    r = engine.run_backtest(bars, sig, symbol=args.symbol, interval=args.interval,
                            strategy=args.strategy, fee=args.fee,
                            stop_loss=args.stop, trailing_stop=args.trail,
                            take_profit=args.tp)
    print(json.dumps({"summary": r.summary(), "equity": r.equity,
                      "positions": r.positions,
                      "trades": [t.__dict__ for t in r.trades],
                      "bars": [{"t": b.t, "o": b.o, "h": b.h, "l": b.l,
                                "c": b.c, "v": b.v} for b in bars]},
                     ensure_ascii=False, default=str))


def main() -> None:
    p = argparse.ArgumentParser(description="crypto-lab: проверка торговых гипотез на данных Binance")
    p.add_argument("--json", action="store_true", help="дополнительно вывести JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--symbol", default="BTCUSDT")
        sp.add_argument("--interval", default="1d", choices=list(D.INTERVALS))
        sp.add_argument("--limit", type=int, default=1000)
        sp.add_argument("--fee", type=float, default=0.001, help="комиссия за сделку, доля")
        return sp

    sp = common(sub.add_parser("scan", help="прогнать все стратегии"))
    sp.set_defaults(func=cmd_scan)

    sp = common(sub.add_parser("bt", help="одна стратегия"))
    sp.add_argument("--strategy", default="ma_cross")
    sp.add_argument("--fast", type=int); sp.add_argument("--slow", type=int)
    sp.add_argument("--lookback", type=int); sp.add_argument("--n", type=int)
    sp.add_argument("--low", type=float); sp.add_argument("--high", type=float)
    sp.add_argument("--k", type=int); sp.add_argument("--window", type=int)
    sp.add_argument("--price", type=float); sp.add_argument("--direction", default="up")
    sp.add_argument("--i1", type=int); sp.add_argument("--p1", type=float)
    sp.add_argument("--i2", type=int); sp.add_argument("--p2", type=float)
    sp.add_argument("--entry", type=float); sp.add_argument("--threshold", type=float)
    sp.add_argument("--stop", type=float); sp.add_argument("--tp", type=float)
    sp.add_argument("--trail", type=float)
    sp.add_argument("--capital", type=float, default=1.0)
    sp.set_defaults(func=cmd_bt)

    sp = common(sub.add_parser("stops", help="сравнить стопы и тейки"))
    sp.set_defaults(func=cmd_stops)

    sp = common(sub.add_parser("levels", help="горизонтальные уровни и их статистика"))
    sp.add_argument("--k", type=int, default=5); sp.add_argument("--tol", type=float, default=0.02)
    sp.add_argument("--top", type=int, default=10); sp.add_argument("--trials", type=int, default=200)
    sp.set_defaults(func=cmd_levels)

    sp = common(sub.add_parser("trendlines", help="трендлайны по экстремумам"))
    sp.add_argument("--k", type=int, default=5)
    sp.set_defaults(func=cmd_trendlines)

    sp = common(sub.add_parser("patterns", help="фигуры и их предсказательная сила"))
    sp.add_argument("--k", type=int, default=5); sp.add_argument("--horizon", type=int, default=20)
    sp.set_defaults(func=cmd_patterns)

    sp = common(sub.add_parser("robust", help="тест стратегии на случайность"))
    sp.add_argument("--strategy", default="ma_cross")
    sp.add_argument("--trials", type=int, default=300)
    sp.set_defaults(func=cmd_robust)

    sp = common(sub.add_parser("funding", help="фандинг-карри"))
    sp.set_defaults(func=cmd_funding)

    sp = common(sub.add_parser("json", help="полный вывод в JSON"))
    sp.add_argument("--strategy", default="buy_hold")
    sp.add_argument("--stop", type=float); sp.add_argument("--tp", type=float)
    sp.add_argument("--trail", type=float)
    sp.set_defaults(func=cmd_json)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
