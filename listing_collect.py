#!/usr/bin/env python3
"""Сбор анонсов листингов Binance — с кэшем страниц и мягким темпом (анти-429).

Кэш: cache/ann_page_N.json — повторный запуск не дёргает сеть по уже скачанному.
Детали (точное время) тянем только для выборки --details N (по умолчанию 40).
"""
import json, os, re, sys, time, urllib.request, urllib.error

BASE = "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query"
DET = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode="
UA = {"User-Agent": "Mozilla/5.0"}
CACHE = "cache"
os.makedirs(CACHE, exist_ok=True)
TICK_RE = re.compile(r"\(([A-Z0-9]{2,12})\)")
PACE = 2.5

def get(url, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            wait = 45 * (i + 1)
            print(f"    HTTP {e.code} -> пауза {wait}s", flush=True)
            time.sleep(wait)
        except Exception as e:
            print(f"    err {e} -> 5s", flush=True)
            time.sleep(5)
    return None

def page(p):
    fp = f"{CACHE}/ann_page_{p}.json"
    if os.path.exists(fp):
        return json.load(open(fp))
    raw = get(f"{BASE}?catalogId=48&pageNo={p}&pageSize=20")
    time.sleep(PACE)
    if not raw:
        return None
    try:
        arts = json.loads(raw, strict=False)["data"]["articles"]
    except Exception:
        m = re.search(r'"articles"\s*:\s*(\[.*?\])\s*,\s*"', raw, re.S)
        arts = json.loads(m.group(1), strict=False) if m else []
    json.dump(arts, open(fp, "w"), ensure_ascii=False)
    return arts

out, seen, empty = [], set(), 0
for p in range(1, 121):
    arts = page(p)
    if arts is None:
        print(f"page {p}: не получена, пропуск"); continue
    if not arts:
        empty += 1
        if empty >= 2:
            print(f"page {p}: пусто x2, стоп"); break
        continue
    empty = 0
    for a in arts:
        code, title = a.get("code"), a.get("title") or ""
        if code in seen:
            continue
        seen.add(code)
        if "Will List" in title:
            out.append({"id": a["id"], "code": code, "title": title,
                        "tickers": TICK_RE.findall(title), "ts_ms": None})
    if p % 20 == 0:
        print(f"  ..page {p}: листингов {len(out)}", flush=True)

print(f"всего 'Will List': {len(out)}", flush=True)

# точное время — только для выборки
n_det = int(sys.argv[1]) if len(sys.argv) > 1 else 40
for it in [x for x in out if x["tickers"]][:n_det]:
    raw = get(DET + it["code"])
    time.sleep(PACE)
    if raw:
        m = re.search(r'"publishDate"\s*:\s*(\d{13})', raw)
        if m:
            it["ts_ms"] = int(m.group(1))

json.dump(out, open("listings.json", "w"), ensure_ascii=False, indent=1)
ok = [x for x in out if x["tickers"]]
print(f"с тикером: {len(ok)}, из них со временем: {sum(1 for x in ok if x['ts_ms'])}")
for x in ok[:12]:
    t = time.strftime("%Y-%m-%d %H:%M", time.gmtime(x["ts_ms"] / 1000)) if x["ts_ms"] else "?"
    print(" ", t, x["tickers"], "|", x["title"][:70])
