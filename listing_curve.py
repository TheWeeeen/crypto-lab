#!/usr/bin/env python3
"""Листинги Binance: при каком входе вообще что-то остаётся.

Ключевая мысль: «открытие» первой свечи — фантомная цена (первая сделка),
её не исполнить. Считаем доход для РЕАЛЬНЫХ входов:
  • вход = закрытие свечи i (i*5 минут после открытия торгов), i = 0,1,2,3,6,12
  • держим +5м / +1ч / +24ч от входа, комиссия 0,1% x2
Контроль: те же монеты, свечи 1000+ (обычная торговля), входы каждые 12 свечей.
"""
import json, time, urllib.request, urllib.error, statistics as st

SPOT = "https://api.binance.com"
FEE = 0.001
HOLD = [("+5m", 1), ("+1h", 12), ("+24h", 288)]
ENTRIES = [0, 1, 2, 3, 6, 12]      # через сколько 5-мин свечей входим

def get(url, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            time.sleep(5 * (i + 1))
        except Exception:
            time.sleep(2)
    return None

def klines(symbol, start=0):
    d = get(f"{SPOT}/api/v3/klines?symbol={symbol}&interval=5m&startTime={start}&limit=1000")
    return d if isinstance(d, list) else []

items = json.load(open("listings.json"))
seen, rows = set(), []
for it in items:
    for t in it["tickers"]:
        if t in seen or t.isdigit():
            continue
        seen.add(t)
        sym = t + "USDT"
        k = klines(sym)
        if len(k) < 400:
            continue
        # кривая входа
        curve = {}
        for i in ENTRIES:
            if i >= len(k):
                continue
            entry = float(k[i][4])
            d = {}
            for name, n in HOLD:
                j = i + n
                if j < len(k):
                    d[name] = (float(k[j][4]) / entry - 1) - 2 * FEE
            curve[i] = d
        rows.append({
            "sym": sym, "open_ms": k[0][0],
            "c0": {"o": float(k[0][1]), "h": float(k[0][2]), "l": float(k[0][3]), "c": float(k[0][4])},
            "curve": curve,
        })
        time.sleep(0.3)

print(f"листингов: {len(rows)}")
json.dump(rows, open("listing_curve.json", "w"), ensure_ascii=False)

print("\n=== КРИВАЯ ВХОДА (медиана дохода, комиссии учтены) ===")
print(f"{'вход':>7} | " + " | ".join(f"{h:>16}" for h, _ in HOLD))
print(f"{'':>7} | " + " | ".join(f"{'медиана  %плюс':>16}" for _ in HOLD))
for i in ENTRIES:
    cells = []
    for name, _ in HOLD:
        v = [r["curve"][i][name] for r in rows if i in r["curve"] and name in r["curve"][i]]
        if not v:
            cells.append(f"{'—':>16}")
            continue
        pos = 100 * sum(1 for x in v if x > 0) / len(v)
        cells.append(f"{100*st.median(v):>7.1f}% {pos:>7.0f}%")
    print(f"{i*5:>4}м | " + " | ".join(cells))

# фантомное «открытие» для контраста
ph = []
for r in rows:
    c = r["c0"]
    if c["o"] > 0:
        ph.append(c["c"] / c["o"] - 1)
print(f"\nконтраст: закрытие 1-й свечи к её открытию — медиана {100*st.median(ph):.0f}%, "
      f"среднее {100*st.mean(ph):.0f}%  (это «доход» от фантомной цены открытия)")

# контроль: обычная торговля
ctrl = {n: [] for n, _ in HOLD}
for r in rows:
    k2 = klines(r["sym"], start=r["open_ms"] + 1000 * 5 * 60 * 1000)
    if len(k2) < 400:
        continue
    for i0 in range(0, len(k2) - 289, 12):
        entry = float(k2[i0][4])
        for name, n in HOLD:
            j = i0 + n
            if j < len(k2):
                ctrl[name].append((float(k2[j][4]) / entry - 1) - 2 * FEE)
    time.sleep(0.3)
print("\n=== КОНТРОЛЬ: обычная торговля (та же монета, спустя недели) ===")
print(f"{'гориз':>6} {'n':>7} {'медиана':>9} {'среднее':>9} {'%плюс':>6}")
for name, _ in HOLD:
    v = ctrl[name]
    if not v:
        continue
    pos = 100 * sum(1 for x in v if x > 0) / len(v)
    print(f"{name:>6} {len(v):>7} {100*st.median(v):>8.2f}% {100*st.mean(v):>8.2f}% {pos:>5.1f}%")
