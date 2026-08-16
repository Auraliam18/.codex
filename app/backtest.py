"""Walk-forward backtester.

Replays historical klines bar by bar: on each bar the strategy sees only the
past, open positions are checked against the bar's high/low for SL/TP
(stop-loss checked first, conservative), and new signals open positions sized
with the same risk model the live engine uses.
"""

from __future__ import annotations

from typing import Optional


def run_backtest(
    strategy,
    candles: list[dict],
    initial_balance: float = 10000.0,
    leverage: int = 5,
    risk_pct: float = 2.0,
    cooldown_bars: int = 3,
) -> dict:
    min_c = strategy.min_candles()
    balance = initial_balance
    equity_curve: list[float] = []
    trades: list[dict] = []
    pos: Optional[dict] = None
    last_entry_bar = -10**9

    def qty_for(price: float, sl: Optional[float]) -> float:
        risk_amount = balance * leverage * risk_pct / 100.0
        sl_dist = abs(price - sl) if sl else price * 0.01
        if sl_dist <= 0:
            sl_dist = price * 0.01
        return max(risk_amount / sl_dist, 0.0)

    def close_pos(exit_price: float, reason: str, bar_i: int) -> None:
        nonlocal balance, pos
        direction = 1 if pos["side"] == "LONG" else -1
        pnl = (exit_price - pos["entry"]) * direction * pos["qty"]
        balance += pnl
        trades.append({
            "side": pos["side"], "entry": pos["entry"], "exit": exit_price,
            "qty": pos["qty"], "pnl": pnl, "reason": reason,
            "entry_time": pos["time"], "exit_time": candles[bar_i]["time"],
        })
        pos = None

    for i in range(min_c, len(candles)):
        bar = candles[i]

        if pos is not None:
            direction = 1 if pos["side"] == "LONG" else -1
            sl, tp = pos["sl"], pos["tp"]
            if direction == 1:
                if sl is not None and bar["low"] <= sl:
                    close_pos(sl, "SL", i)
                elif tp is not None and bar["high"] >= tp:
                    close_pos(tp, "TP", i)
            else:
                if sl is not None and bar["high"] >= sl:
                    close_pos(sl, "SL", i)
                elif tp is not None and bar["low"] <= tp:
                    close_pos(tp, "TP", i)

        if pos is None and i - last_entry_bar >= cooldown_bars:
            signal = strategy.analyze(candles[: i + 1])
            if signal and balance > 0:
                qty = qty_for(signal.price, signal.sl)
                if qty > 0:
                    pos = {
                        "side": signal.side, "entry": signal.price, "qty": qty,
                        "sl": signal.sl, "tp": signal.tp, "time": bar["time"],
                    }
                    last_entry_bar = i

        mark = balance
        if pos is not None:
            direction = 1 if pos["side"] == "LONG" else -1
            mark += (bar["close"] - pos["entry"]) * direction * pos["qty"]
        equity_curve.append(round(mark, 2))

    if pos is not None:
        close_pos(candles[-1]["close"], "END", len(candles) - 1)

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    peak, max_dd = initial_balance, 0.0
    for v in equity_curve:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak * 100)

    return {
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "return_pct": round((balance - initial_balance) / initial_balance * 100, 2),
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "max_drawdown_pct": round(max_dd, 2),
        "equity_curve": equity_curve[:: max(1, len(equity_curve) // 200)],
        "trades": trades[-40:],
    }
