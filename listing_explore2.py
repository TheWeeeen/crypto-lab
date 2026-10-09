#!/usr/bin/env python3
"""Смотрим полный JSON одного анонса + пробуем detail-эндпоинт с точным временем."""
import json, urllib.request

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

lst = get("https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query?catalogId=48&pageNo=1&pageSize=3")["data"]["articles"]
a = lst[0]
print("=== raw article ===")
print(json.dumps(a, ensure_ascii=False, indent=1)[:2500])
print()
print("code:", a.get("code"), "shortLink:", a.get("shortLink"))
print()
for tmpl in [
    "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode={c}",
    "https://www.binance.com/bapi/apex/v1/public/apex/cms/article/detail/query?articleCode={c}",
]:
    url = tmpl.format(c=a.get("code"))
    try:
        d = get(url)
        print("OK", url[:80], "->", json.dumps(d, ensure_ascii=False)[:600])
    except Exception as e:
        print("ERR", url[:80], e)
