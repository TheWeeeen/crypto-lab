"""Наблюдатель за рынком: всплески объёма/цены и новые анонсы Binance.

Не торгует. Задача — поймать событие и отдать его человеку раньше, чем
он увидит его в ленте. Запуск: python3 watcher.py [--top N]

Состояние (что уже отправлено) — cache/watch_state.json.
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
import time
import urllib.request
from datetime import datetime, timezone

SPOT = "https://api.binance.com"
CMS = "https://www.binance.com/bapi/composite/v1/public/cms/article"
ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "cache", "watch_state.json")
HEADERS = {"User-Agent": "Mozilla/5.0 crypto-lab/1.0"}

# пороги срабатывания
MOVE_5M = 0.02        # ±2% за 5 минут
MOVE_15M = 0.04       # ±4% за 15 минут
VOL_MULT = 6.0        # объём последней 5м свечи > 6x среднего
MIN_QUOTE_VOL = 5_000_000   # отсечь неликвид


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def load_state() -> dict:
    try:
        return json.load(open(STATE))
    except Exception:
        return {"seen_articles": [], "alerts": {}}


def save_state(s: dict) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    s["seen_articles"] = s["seen_articles"][-400:]
    json.dump(s, open(STATE, "w"), ensure_ascii=False, indent=1)


def liquid_symbols(top: int) -> list[str]:
    tick = get(f"{SPOT}/api/v3/ticker/24hr")
    rows = [(t["symbol"], float(t["quoteVolume"]))
            for t in tick
            if t["symbol"].endswith("USDT")
            and float(t.get("quoteVolume", 0)) >= MIN_QUOTE_VOL]
    rows.sort(key=lambda r: -r[1])
    return [s for s, _ in rows[:top]]


def scan_moves(symbols: list[str], state: dict, cooldown: int = 3600) -> list[str]:
    """Всплески по последним закрытым 5м свечам. Повтор — не чаще раза в cooldown."""
    out = []
    seen = state.setdefault("alerts", {})
    now = time.time()
    for s in symbols:
        try:
            raw = get(f"{SPOT}/api/v3/klines?symbol={s}&interval=5m&limit=290")
        except Exception:
            continue
        if len(raw) < 290:
            continue
        closes = [float(x[4]) for x in raw]
        vols = [float(x[5]) for x in raw]
        last = raw[-2]                      # последняя закрытая свеча
        c, v = float(last[4]), float(last[5])
        avg_v = st.mean(vols[:-1])
        ch5 = c / float(last[1]) - 1
        ch15 = c / closes[-4] - 1
        ch60 = c / closes[-13] - 1
        reasons = []
        if abs(ch5) >= MOVE_5M:
            reasons.append(f"{ch5:+.1%} за 5м")
        if abs(ch15) >= MOVE_15M:
            reasons.append(f"{ch15:+.1%} за 15м")
        # объём сам по себе шумит (золото, стейблы) — только вместе с движением
        if v > VOL_MULT * avg_v and abs(ch5) >= 0.01:
            reasons.append(f"объём {v/avg_v:.0f}x")
        if not reasons:
            continue
        key = f"{s}|{last[0]}"
        if key in seen:
            continue
        seen[key] = int(now)
        out.append(f"{s}: {', '.join(reasons)}  (за час {ch60:+.1%}, цена {c:g})")
    # чистка старых меток
    state["alerts"] = {k: t for k, t in seen.items() if now - t < cooldown * 6}
    return out



def scan_announcements(state: dict) -> list[str]:
    """Новые анонсы листингов/пар — единственная новость с открытым API."""
    out = []
    try:
        data = get(f"{CMS}/catalog/list/query?catalogId=48&pageNo=1&pageSize=20")["data"]
    except Exception:
        return out
    for a in data.get("articles", []):
        aid = a["id"]
        if aid in state["seen_articles"]:
            continue
        state["seen_articles"].append(aid)
        t = a.get("title") or ""
        if any(k in t for k in ("Will List", "Will Add", "Launchpool",
                                "Will Delist", "Trading Pairs")):
            out.append(t)
    return out


def main() -> int:
    top = 120
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])
    state = load_state()
    now = datetime.now(timezone.utc).strftime("%d.%m %H:%M UTC")

    try:
        symbols = liquid_symbols(top)
    except Exception as e:
        print(f"Binance недоступен: {e}")
        return 1

    moves = scan_moves(symbols, state)
    news = scan_announcements(state)
    save_state(state)

    if not moves and not news:
        return 0
    lines = [f"*Рынок {now}*"]
    if moves:
        lines.append("Движения:")
        lines += [f"• {m}" for m in moves[:15]]
    if news:
        lines.append("Анонсы Binance:")
        lines += [f"• {n}" for n in news[:10]]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
