"""Движок бэктеста: сигналы -> сделки -> кривая капитала + метрики.

Правило против заглядывания в будущее: решение, принятое по закрытию бара i,
действует начиная с бара i+1.

Инвариант: len(equity) == len(positions) == len(bars).
"""
from __future__ import annotations

from dataclasses import dataclass

from .data import Bar
from . import metrics as M


@dataclass
class Trade:
    side: str          # "long" / "short"
    entry_t: int
    entry_px: float
    exit_t: int | None = None
    exit_px: float | None = None
    reason: str = ""   # signal / stop_loss / take_profit / trailing / end
    bars_held: int = 0

    @property
    def pnl(self) -> float:
        if self.exit_px is None or not self.entry_px:
            return 0.0
        raw = self.exit_px / self.entry_px - 1
        return raw if self.side == "long" else -raw


@dataclass
class Result:
    symbol: str
    interval: str
    strategy: str
    params: dict
    equity: list[float]
    positions: list[float]
    trades: list[Trade]
    bars: list[Bar]
    initial: float = 1.0
    fee: float = 0.001
    slippage: float = 0.0

    @property
    def total_return(self) -> float:
        return self.equity[-1] / self.initial - 1 if self.equity else 0.0

    @property
    def benchmark(self) -> float:
        if not self.bars:
            return 0.0
        return self.bars[-1].c / self.bars[0].c - 1

    @property
    def fees_paid(self) -> float:
        turn = sum(abs(self.positions[i] - self.positions[i - 1])
                   for i in range(1, len(self.positions)))
        return turn * (self.fee + self.slippage)

    @property
    def exposure(self) -> float:
        if not self.positions:
            return 0.0
        return sum(1 for p in self.positions if p) / len(self.positions)

    @property
    def closed_trades(self) -> list[Trade]:
        return [t for t in self.trades if t.exit_px is not None]

    @property
    def win_rate(self) -> float:
        done = self.closed_trades
        return sum(1 for t in done if t.pnl > 0) / len(done) if done else 0.0

    @property
    def avg_trade(self) -> float:
        done = self.closed_trades
        return sum(t.pnl for t in done) / len(done) if done else 0.0

    def summary(self) -> dict:
        eq = self.equity or [self.initial]
        rs = M.returns(eq)
        return {
            "symbol": self.symbol, "interval": self.interval,
            "strategy": self.strategy, "params": self.params,
            "bars": len(self.bars),
            "from": self.bars[0].date if self.bars else None,
            "to": self.bars[-1].date if self.bars else None,
            "total_return": self.total_return,
            "benchmark_return": self.benchmark,
            "excess": self.total_return - self.benchmark,
            "cagr": M.ann_return(rs, self.interval),
            "vol": M.ann_vol(rs, self.interval),
            "sharpe": M.sharpe(rs, interval=self.interval),
            "sortino": M.sortino(rs, self.interval),
            "max_drawdown": M.max_drawdown(eq),
            "calmar": M.calmar(eq, rs, self.interval),
            "trades": len(self.trades),
            "win_rate": self.win_rate,
            "avg_trade": self.avg_trade,
            "fees_paid": self.fees_paid,
            "exposure": self.exposure,
            "final_equity": eq[-1],
        }


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def run_backtest(
    bars: list[Bar],
    signals: list[float],
    *,
    symbol: str = "",
    interval: str = "1d",
    strategy: str = "custom",
    params: dict | None = None,
    fee: float = 0.001,
    slippage: float = 0.0,
    initial: float = 1.0,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    trailing_stop: float | None = None,
    allow_short: bool = True,
) -> Result:
    """signals[i] — целевая позиция ПОСЛЕ бара i (0 вне рынка, 1 лонг, -1 шорт)."""
    n = len(bars)
    if n < 2:
        raise ValueError("нужно минимум 2 бара")
    if len(signals) != n:
        raise ValueError(f"длина signals ({len(signals)}) != число баров ({n})")

    lo = -1.0 if allow_short else 0.0
    sig = [_clamp(float(s), lo, 1.0) for s in signals]
    cost = fee + slippage

    equity = [initial]
    positions = [0.0]
    trades: list[Trade] = []

    eq = initial
    pos = 0.0
    entry_px: float | None = None
    entry_t: int | None = None
    entry_i: int | None = None
    peak: float | None = None
    blocked = False     # после стопа не перезаходим, пока сигнал не сменится на 0

    def open_pos(i: int, px: float, side: float) -> None:
        nonlocal eq, pos, entry_px, entry_t, entry_i, peak
        eq *= (1 - cost)
        pos = side
        entry_px = px
        entry_t = bars[i].t
        entry_i = i
        peak = px
        trades.append(Trade(side="long" if side > 0 else "short",
                            entry_t=bars[i].t, entry_px=px))

    def close_pos(i: int, px: float, reason: str) -> None:
        nonlocal eq, pos, entry_px, entry_t, entry_i, peak
        if pos and entry_px is not None:
            eq *= (1 - cost)
            trades.append(Trade(side="long" if pos > 0 else "short",
                                entry_t=entry_t or bars[i].t, entry_px=entry_px,
                                exit_t=bars[i].t, exit_px=px, reason=reason,
                                bars_held=i - (entry_i if entry_i is not None else i)))
        pos = 0.0
        entry_px = entry_t = entry_i = peak = None

    for i in range(1, n):
        b = bars[i]

        # 1) стопы и тейки внутри бара
        if pos and entry_px is not None:
            if pos > 0:
                peak = max(peak or b.h, b.h)
                stop_px = entry_px * (1 - stop_loss) if stop_loss else None
                if trailing_stop:
                    tr = peak * (1 - trailing_stop)
                    stop_px = max(stop_px, tr) if stop_px else tr
                if stop_px and b.l <= stop_px:
                    close_pos(i, stop_px, "trailing" if (trailing_stop and
                              stop_px > entry_px * (1 - (stop_loss or 1.0))) else "stop_loss")
                    blocked = True
                elif take_profit and b.h >= entry_px * (1 + take_profit):
                    close_pos(i, entry_px * (1 + take_profit), "take_profit")
                    blocked = True
            else:
                peak = min(peak or b.l, b.l)
                stop_px = entry_px * (1 + stop_loss) if stop_loss else None
                if trailing_stop:
                    tr = peak * (1 + trailing_stop)
                    stop_px = min(stop_px, tr) if stop_px else tr
                if stop_px and b.h >= stop_px:
                    close_pos(i, stop_px, "stop_loss")
                    blocked = True
                elif take_profit and b.l <= entry_px * (1 - take_profit):
                    close_pos(i, entry_px * (1 - take_profit), "take_profit")
                    blocked = True

        # 2) сигнал, принятый по закрытию прошлого бара
        target = sig[i - 1]
        if blocked:
            if target == 0:
                blocked = False
            else:
                target = 0.0
        if abs(target - pos) > 1e-9:
            if pos:
                close_pos(i, b.c, "signal")
            if target:
                open_pos(i, b.c, target)

        # 3) доходность бара на текущую позицию
        r = b.c / bars[i - 1].c - 1
        eq *= (1 + pos * r)
        equity.append(eq)
        positions.append(pos)

    if pos and entry_px is not None:
        close_pos(n - 1, bars[-1].c, "end")
        positions[-1] = 0.0

    return Result(symbol=symbol, interval=interval, strategy=strategy,
                  params=params or {}, equity=equity, positions=positions,
                  trades=trades, bars=bars, initial=initial,
                  fee=fee, slippage=slippage)


def run_many(bars: list[Bar], signals_by_name: dict, **kw) -> list[Result]:
    return [run_backtest(bars, sig, strategy=name, **kw)
            for name, sig in signals_by_name.items()]
