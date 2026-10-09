#!/usr/bin/env python3
"""Достаём точное время публикации анонса (detail-эндпоинт)."""
import json, re, urllib.request

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")

code = "a1a7996170f246da90ea49f199a61bcd"
raw = get(f"https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode={code}")

# все ключи, похожие на дату
for m in sorted(set(re.findall(r'"([a-zA-Z]*[Dd]ate[a-zA-Z]*)"\s*:\s*([^,}]{0,40})', raw))):
    print("DATE-FIELD:", m)
print()
# верхнеуровневые ключи data
m = re.search(r'"data"\s*:\s*\{', raw)
head = raw[m.end():m.end()+1500] if m else ""
print("data head:", head[:800])
print()
# любые большие числа (эпоха ms)
for m in sorted(set(re.findall(r'"(1[6-9]\d{11})"', raw)))[:10]:
    print("epoch-like:", m)
