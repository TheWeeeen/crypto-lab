#!/usr/bin/env python3
"""Тест: что остаётся от «новости» (листинг Binance), если покупать по факту.

Для каждого спот-листинга — первые 5м свечи на Binance. Вход:
  • на открытии торгов (0-я свеча) — «успел к открытию»
  • через 5 минут (1-я свеча)      — «пока дошёл»
Горизонты: +5м / +15м / +1ч / +6ч / +24ч. Комиссия 0,1% x2.
Контроль: те же монеты, случайные входы в обычной торговле (свечи 800+).
"""
import json, time, urllib.request, urllib.error, statistics as st

SPOT = "https://api.binance.com"
FEE = 0.001
HOR = [("5m", 1), ("15m", 3), ("1h", 12), ("6h", 72), ("24h", 288)]

def get(url, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):        # неверный символ — повторять бессмысленно
                return None
            time.sleep(5 * (i + 1))          # 429/418/5xx — backoff
        except Exception:
            time.sleep(2)
    return None

def klines(symbol, interval="5m", start=0, limit=2000):
    d = get(f"{SPOT}/api/v3/klines?symbol={symbol}&interval={interval}&startTime={start}&limit={limit}")
    return d if isinstance(d, list) else []

def rets_from(k, i0):
    """Доход от открытия свечи i0 до закрытия i0+n (n — в свечах), минус комиссии."""
    if i0 >= len(k):
        return {}
    entry = float(k[i0][1])
    out = {}
    for name, n in HOR:
        j = i0 + n
        if j < len(k):
            out[name] = (float(k[j][4]) / entry - 1) - 2 * FEE
    return out

items = json.load(open("listings.json"))
seen, rows, ctrl = set(), [], {n: [] for n, _ in HOR}
tried = 0
for it in items:
    for t in it["tickers"]:
        if t in seen or t.isdigit():       # чисто цифровые — артефакты «Quarterly Delivery Contracts»
            continue
        seen.add(t)
        sym = t + "USDT"
        k = klines(sym)
        tried += 1
        if tried % 25 == 0:
            print(f"  ..проверено {tried}, листингов {len(rows)}", flush=True)
        if len(k) < 300:
            continue
        lead = ((k[0][0] - it["ts_ms"]) / 3.6e6) if it.get("ts_ms") else None
        rows.append({
            "sym": sym, "open_ms": k[0][0], "lead_h": round(lead, 2) if lead is not None else None,
            "spike": float(k[0][2]) / float(k[0][1]) - 1,
            "open": rets_from(k, 0), "next": rets_from(k, 1), "n": len(k),
        })
        if len(k) >= 1000:
            for i0 in range(800, min(len(k) - 289, 1800), 12):
                rr = rets_from(k, i0)
                for n, _ in HOR:
                    if n in rr:
                        ctrl[n].append(rr[n])
        time.sleep(0.35)

print(f"листингов с данными: {len(rows)}")
json.dump(rows, open("listing_test_raw.json", "w"), ensure_ascii=False)

def summarise(key, title):
    print(f"\n=== {title} ===")
    print(f"{'гориз':>5} {'n':>4} {'медиана':>9} {'среднее':>9} {'%плюс':>6} {'макс':>8} {'мин':>8}")
    for name, _ in HOR:
        v = [r[key][name] for r in rows if name in r[key]]
        if not v:
            continue
        pos = 100 * sum(1 for x in v if x > 0) / len(v)
        print(f"{name:>5} {len(v):>4} {100*st.median(v):>8.2f}% {100*st.mean(v):>8.2f}% "
              f"{pos:>5.1f}% {100*max(v):>7.1f}% {100*min(v):>7.1f}%")

summarise("open", "ВХОД на открытии листинга")
summarise("next", "ВХОД через 5 минут после открытия")

print("\n=== КОНТРОЛЬ: обычная торговля, случайные входы ===")
print(f"{'гориз':>5} {'n':>6} {'медиана':>9} {'среднее':>9} {'%плюс':>6}")
for name, _ in HOR:
    v = ctrl[name]
    if not v:
        continue
    pos = 100 * sum(1 for x in v if x > 0) / len(v)
    print(f"{name:>5} {len(v):>6} {100*st.median(v):>8.2f}% {100*st.mean(v):>8.2f}% {pos:>5.1f}%")

sp = [r["spike"] for r in rows]
print(f"\nпервая свеча: хай/открытие — медиана {100*st.median(sp):.1f}%, "
      f"среднее {100*st.mean(sp):.1f}%, макс {100*max(sp):.0f}%")
lead = [r["lead_h"] for r in rows if r.get("lead_h") is not None]
if lead:
    print(f"от анонса до открытия торгов: медиана {st.median(lead):.1f} ч "
          f"(мин {min(lead):.1f}, макс {max(lead):.1f}) — по {len(lead)} анонсам")
