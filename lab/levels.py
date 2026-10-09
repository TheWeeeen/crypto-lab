"""Уровни, трендлайны и фигуры: автодетекция + статистика.

Отвечает на вопрос «работает ли рисование» числами:
касания, отскоки, пробои, и сравнение с тем же тестом на случайном блуждании.
"""
from __future__ import annotations

import random
import statistics as st

from .data import Bar


# ---------- экстремумы и кластеризация ----------

def local_extrema(bars: list[Bar], k: int = 5) -> tuple[list[int], list[int]]:
    """Фракталы: индекс выше/ниже k соседей с каждой стороны."""
    highs, lows = [], []
    for i in range(k, len(bars) - k):
        wh = [bars[j].h for j in range(i - k, i + k + 1)]
        wl = [bars[j].l for j in range(i - k, i + k + 1)]
        if bars[i].h >= max(wh):
            highs.append(i)
        if bars[i].l <= min(wl):
            lows.append(i)
    return highs, lows


def cluster_levels(bars: list[Bar], k: int = 5, tol: float = 0.02,
                   min_touches: int = 2) -> list[dict]:
    """Горизонтальные уровни: кластеры локальных экстремумов по цене."""
    highs, lows = local_extrema(bars, k)
    pts = [(i, bars[i].h) for i in highs] + [(i, bars[i].l) for i in lows]
    pts.sort(key=lambda x: x[1])
    clusters: list[dict] = []
    for i, p in pts:
        hit = None
        for c in clusters:
            if abs(p - c["price"]) / c["price"] <= tol:
                hit = c
                break
        if hit:
            hit["touches"].append((i, p))
            hit["price"] = st.mean(x[1] for x in hit["touches"])
        else:
            clusters.append({"price": p, "touches": [(i, p)]})
    out = []
    for c in clusters:
        if len(c["touches"]) >= min_touches:
            idx = [i for i, _ in c["touches"]]
            out.append({"price": c["price"], "touches": len(c["touches"]),
                        "first_i": min(idx), "last_i": max(idx)})
    out.sort(key=lambda c: -c["touches"])
    return out


def level_stats(bars: list[Bar], price: float, tol: float = 0.01,
                horizon: int = 10) -> dict:
    """Что происходит, когда цена подходит к уровню."""
    touches, broke_up, broke_down, bounced = 0, 0, 0, 0
    i = 1
    while i < len(bars) - horizon:
        b = bars[i]
        near = b.l <= price * (1 + tol) and b.h >= price * (1 - tol)
        if near:
            touches += 1
            fwd = bars[i + horizon].c / b.c - 1
            if b.c > price * (1 + tol):
                broke_up += 1
            elif b.c < price * (1 - tol):
                broke_down += 1
            else:
                bounced += 1 if fwd > 0 else 0
            i += horizon  # не считаем одно и то же касание много раз
        else:
            i += 1
    return {"price": price, "touches": touches, "broke_up": broke_up,
            "broke_down": broke_down, "bounced": bounced,
            "hold_rate": (bounced / touches) if touches else 0.0}


# ---------- трендлайны ----------

def fit_trendlines(bars: list[Bar], k: int = 5, max_lines: int = 5) -> list[dict]:
    """Линии поддержки (по минимумам) и сопротивления (по максимумам)."""
    highs, lows = local_extrema(bars, k)
    out: list[dict] = []
    for kind, idxs, pick in (("support", lows, lambda b: b.l),
                             ("resistance", highs, lambda b: b.h)):
        best = []
        for a in range(len(idxs)):
            for b_ in range(a + 1, len(idxs)):
                i1, i2 = idxs[a], idxs[b_]
                if i2 - i1 < 10:
                    continue
                p1, p2 = pick(bars[i1]), pick(bars[i2])
                if p1 == p2:
                    continue
                slope = (p2 - p1) / (i2 - i1)
                touches, breaks = 0, 0
                for j in range(i1 + 1, len(bars)):
                    line = p1 + slope * (j - i1)
                    if line <= 0:
                        break
                    if kind == "support":
                        if abs(bars[j].l - line) / line <= 0.015:
                            touches += 1
                        elif bars[j].c < line * 0.985:
                            breaks += 1
                    else:
                        if abs(bars[j].h - line) / line <= 0.015:
                            touches += 1
                        elif bars[j].c > line * 1.015:
                            breaks += 1
                score = touches - 2 * breaks
                if touches >= 2:
                    best.append({"kind": kind, "i1": i1, "p1": p1, "i2": i2, "p2": p2,
                                 "slope": slope, "touches": touches, "breaks": breaks,
                                 "score": score})
        best.sort(key=lambda x: -x["score"])
        out.extend(best[:max_lines])
    return out


# ---------- фигуры ----------

def detect_patterns(bars: list[Bar], k: int = 5, tol: float = 0.03) -> list[dict]:
    """Простые фигуры: двойная вершина/основание, голова-плечи, треугольник."""
    highs, lows = local_extrema(bars, k)
    out: list[dict] = []

    def pair_check(idxs, pick, name, invert=False):
        for a in range(len(idxs) - 1):
            i1, i2 = idxs[a], idxs[a + 1]
            if i2 - i1 < 5:
                continue
            p1, p2 = pick(bars[i1]), pick(bars[i2])
            if abs(p1 - p2) / p1 <= tol:
                mid = bars[(i1 + i2) // 2]
                depth = abs(mid.c - (p1 + p2) / 2) / p1
                if depth >= tol:
                    out.append({"name": name, "i1": i1, "i2": i2,
                                "price": (p1 + p2) / 2, "depth": depth,
                                "confirmed": False})

    pair_check(highs, lambda b: b.h, "двойная вершина")
    pair_check(lows, lambda b: b.l, "двойное основание")

    # голова-плечи: три максимума, средний заметно выше
    for a in range(len(highs) - 2):
        i1, i2, i3 = highs[a], highs[a + 1], highs[a + 2]
        p1, p2, p3 = bars[i1].h, bars[i2].h, bars[i3].h
        if p2 > p1 * 1.02 and p2 > p3 * 1.02 and abs(p1 - p3) / p1 <= tol:
            out.append({"name": "голова-плечи", "i1": i1, "i2": i2, "i3": i3,
                        "price": (p1 + p3) / 2, "confirmed": False})

    # треугольник: сжимающийся диапазон по последним экстремумам
    recent_h = [i for i in highs if i > len(bars) - 90]
    recent_l = [i for i in lows if i > len(bars) - 90]
    if len(recent_h) >= 2 and len(recent_l) >= 2:
        rh = max(bars[i].h for i in recent_h) - min(bars[i].h for i in recent_h)
        rl = max(bars[i].l for i in recent_l) - min(bars[i].l for i in recent_l)
        span = max(b.h for b in bars[-90:]) - min(b.l for b in bars[-90:])
        if span and (rh + rl) / span < 0.5:
            out.append({"name": "треугольник (сжатие)", "i1": recent_h[0],
                        "i2": recent_l[-1], "price": bars[-1].c,
                        "depth": (rh + rl) / span, "confirmed": False})
    return out


# ---------- тест на случайность ----------

def random_walk_like(bars: list[Bar], seed: int = 0) -> list[float]:
    """Случайное блуждание с той же волатильностью и дрейфом, что у ряда."""
    rnd = random.Random(seed)
    px = [b.c for b in bars]
    rs = [px[i] / px[i - 1] - 1 for i in range(1, len(px))]
    mu, sd = st.mean(rs), st.pstdev(rs)
    out = [px[0]]
    for _ in rs:
        out.append(out[-1] * (1 + rnd.gauss(mu, sd)))
    return out


def level_hold_randomness(bars: list[Bar], price: float, tol: float = 0.01,
                          horizon: int = 10, trials: int = 200) -> dict:
    """Держит ли уровень лучше, чем случайное блуждание с теми же свойствами."""
    real = level_stats(bars, price, tol, horizon)["hold_rate"]
    sims = []
    for s in range(trials):
        px = random_walk_like(bars, seed=s)
        fake = [Bar(b.t, p, p, p, p, 0.0) for b, p in zip(bars, px)]
        sims.append(level_stats(fake, price, tol, horizon)["hold_rate"])
    better = sum(1 for v in sims if v >= real) / trials
    return {"real_hold_rate": real, "random_mean": st.mean(sims),
            "p_value": better, "trials": trials}


def pattern_edge(bars: list[Bar], horizon: int = 20) -> list[dict]:
    """Средний ход цены после каждой найденной фигуры против базовой ставки."""
    pats = detect_patterns(bars)
    px = [b.c for b in bars]
    base = st.mean([px[i + horizon] / px[i] - 1
                    for i in range(len(px) - horizon)]) if len(px) > horizon else 0.0
    out = []
    for p in pats:
        i = p.get("i2", p.get("i1", 0))
        if i + horizon >= len(px):
            continue
        fwd = px[i + horizon] / px[i] - 1
        out.append({**p, "fwd": fwd, "edge_vs_base": fwd - base})
    if out:
        out.append({"name": "ИТОГО", "n": len(out), "base": base,
                    "fwd": st.mean(x["fwd"] for x in out),
                    "edge_vs_base": st.mean(x["edge_vs_base"] for x in out)})
    return out
