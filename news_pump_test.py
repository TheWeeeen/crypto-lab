"""Проверка гипотезы «новость -> памп -> можно поймать».

Механический прокси: покупка после большой свечи (то, что делает бот,
читающий новости/твиты), удержание N баров, выход. Комиссии считаются.
Вход: открытие следующего бара (без look-ahead). Проверяются обе стороны.
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
import urllib.request

SPOT = "https://api.binance.com"
HEADERS = {"User-Agent": "Mozilla/5.0 crypto-lab/1.0"}
FEE = 0.001  # 0,1% taker за сторону


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def klines_range(symbol, interval, start_ms, end_ms, step_ms):
    out, cur = [], start_ms
    while cur < end_ms:
        url = (f"{SPOT}/api/v3/klines?symbol={symbol}&interval={interval}"
               f"&startTime={cur}&endTime={end_ms}&limit=1000")
        raw = get(url)
        if not raw:
            break
        for x in raw:
            out.append((int(x[0]), float(x[1]), float(x[2]), float(x[3]),
                        float(x[4]), float(x[5])))
        cur = int(raw[-1][0]) + step_ms
        if len(raw) < 1000:
            break
    return out


def analyse(bars, thresh, horizons, vol_mult=2.0):
    o = [b[1] for b in bars]
    c = [b[4] for b in bars]
    v = [b[5] for b in bars]
    n = len(bars)
    avg_v = st.mean(v) if v else 0
    idx = [i for i in range(1, n - 1)
           if c[i] / o[i] - 1 >= thresh and v[i] > vol_mult * avg_v]
    res = {}
    for h in horizons:
        longs, shorts = [], []
        for i in idx:
            if i + h + 1 >= n:
                continue
            entry, exit_ = o[i + 1], c[i + h]
            g = exit_ / entry - 1
            longs.append(g - 2 * FEE)
            shorts.append(-g - 2 * FEE)
        if not longs:
            res[h] = None
            continue
        res[h] = {
            "n": len(longs),
            "long_net": st.mean(longs),
            "long_med": st.median(longs),
            "long_win": sum(1 for x in longs if x > 0) / len(longs),
            "short_net": st.mean(shorts),
            "short_win": sum(1 for x in shorts if x > 0) / len(shorts),
        }
    base = {}
    for h in horizons:
        rs = [c[i + h] / o[i + 1] - 1 - 2 * FEE
              for i in range(0, n - h - 1, max(1, n // 500))]
        base[h] = st.mean(rs) if rs else 0.0
    comp = []
    for i in idx:
        if i + 60 >= n:
            continue
        m1h = c[i + 60] / o[i] - 1
        if abs(m1h) > 1e-9:
            comp.append((c[i] / o[i] - 1) / m1h)
    return {"thresh": thresh, "spikes": len(idx), "horizons": res,
            "baseline": base,
            "share_in_bar_1h": st.median(comp) if comp else None}


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    end = int(time.time() * 1000)
    start = end - days * 86400_000
    symbols = sys.argv[2].split(",") if len(sys.argv) > 2 else ["DOGEUSDT", "BTCUSDT"]
    horizons = [1, 5, 15, 60]
    report = []
    for s in symbols:
        bars = klines_range(s, "1m", start, end, 60_000)
        print(f"### {s}: {len(bars)} баров 1m (~{len(bars)/1440:.0f} дн)", file=sys.stderr)
        for th in (0.005, 0.01, 0.02):
            r = analyse(bars, th, horizons)
            r["symbol"] = s
            report.append(r)
            if not r["spikes"]:
                print(f"{s} порог {th:.1%}: спайков нет", file=sys.stderr)
                continue
            print(f"\n{s}  спайк>={th:.1%} + объём>2x   (случаев {r['spikes']})", file=sys.stderr)
            for h in horizons:
                d = r["horizons"][h]
                if d:
                    print(f"  держим {h:>2}м: ЛОНГ {d['long_net']:+.3%} "
                          f"(плюсовых {d['long_win']:.0%}) | ШОРТ {d['short_net']:+.3%} "
                          f"(плюсовых {d['short_win']:.0%}) | базлайн {r['baseline'][h]:+.3%}",
                          file=sys.stderr)
            if r["share_in_bar_1h"] is not None:
                print(f"  доля часового хода, уже внутри свечи: {r['share_in_bar_1h']:.0%}",
                      file=sys.stderr)
    json.dump(report, open("reports/news_pump_test.json", "w"), ensure_ascii=False, indent=1)
    print("saved reports/news_pump_test.json")
