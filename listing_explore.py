#!/usr/bin/env python3
"""Разведка: что вообще отдаёт публичный API анонсов Binance (catalogId=48)."""
import json, urllib.request, sys

BASE = "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def fetch(page, size=20):
    url = f"{BASE}?catalogId=48&pageNo={page}&pageSize={size}"
    return get(url)["data"]

first = fetch(1)
print("total:", first.get("total"))
arts = first["articles"]
print("page1 count:", len(arts))
print("keys of an article:", list(arts[0].keys()))
print()
for a in arts[:8]:
    print(a["publishDate"], "|", a["id"], "|", a["title"][:110])
print()
# how far back can we page?
for p in (2, 3, 5, 10, 20, 40, 80, 120, 200):
    try:
        d = fetch(p)
        a = d["articles"]
        if not a:
            print(f"page {p}: EMPTY")
            break
        print(f"page {p}: {len(a)} arts, newest={a[0]['releaseDate']}, oldest={a[-1]['releaseDate']}")
    except Exception as e:
        print(f"page {p}: ERR {e}")
        break
