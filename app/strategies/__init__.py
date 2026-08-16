"""Strategy framework: indicators, base class, and an open registry.

The registry supports unlimited strategies — built-ins register themselves via
@register, and rule-based custom strategies can be added at runtime from the
dashboard without writing code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

# ------------------------------------------------------------------ indicators


def sma(values: list[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    running = sum(values[:period])
    out[period - 1] = running / period
    for i in range(period, len(values)):
        running += values[i] - values[i - period]
        out[i] = running / period
    return out


def ema(values: list[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    k = 2 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: list[float], period: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        diff = values[i] - values[i - 1]
        gains += max(diff, 0)
        losses += max(-diff, 0)
    avg_gain, avg_loss = gains / period, losses / period
    out[period] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, len(values)):
        diff = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(diff, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-diff, 0)) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def macd(
    values: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[Optional[float]], list[Optional[float]], list[Optional[float]]]:
    ema_fast, ema_slow = ema(values, fast), ema(values, slow)
    line: list[Optional[float]] = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    known = [v for v in line if v is not None]
    sig_known = ema(known, signal) if len(known) >= signal else []
    sig: list[Optional[float]] = [None] * len(line)
    offset = len(line) - len(known)
    for i, v in enumerate(sig_known):
        sig[offset + i] = v
    hist = [
        (l - s) if l is not None and s is not None else None for l, s in zip(line, sig)
    ]
    return line, sig, hist


def bollinger(
    values: list[float], period: int = 20, mult: float = 2.0
) -> tuple[list[Optional[float]], list[Optional[float]], list[Optional[float]]]:
    mid = sma(values, period)
    upper: list[Optional[float]] = [None] * len(values)
    lower: list[Optional[float]] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        m = mid[i]
        if m is None:
            continue
        std = math.sqrt(sum((v - m) ** 2 for v in window) / period)
        upper[i] = m + mult * std
        lower[i] = m - mult * std
    return upper, mid, lower


def atr(candles: list[dict], period: int = 14) -> list[Optional[float]]:
    trs: list[float] = []
    for i, c in enumerate(candles):
        if i == 0:
            trs.append(c["high"] - c["low"])
        else:
            prev_close = candles[i - 1]["close"]
            trs.append(
                max(
                    c["high"] - c["low"],
                    abs(c["high"] - prev_close),
                    abs(c["low"] - prev_close),
                )
            )
    out: list[Optional[float]] = [None] * len(candles)
    if len(trs) < period:
        return out
    prev = sum(trs[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(trs)):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


# --------------------------------------------------------------------- signal


@dataclass
class Signal:
    side: str  # LONG | SHORT
    price: float
    confidence: float  # 0..1
    reason: str
    sl: Optional[float] = None
    tp: Optional[float] = None


@dataclass
class StrategyMeta:
    id: str
    name: str
    description: str
    builtin: bool = True
    default_config: dict = field(default_factory=dict)


class BaseStrategy:
    meta: StrategyMeta

    def __init__(self, config: Optional[dict] = None):
        self.config = {**self.meta.default_config, **(config or {})}

    def min_candles(self) -> int:
        return 120

    def analyze(self, candles: list[dict]) -> Optional[Signal]:  # pragma: no cover
        raise NotImplementedError


# ------------------------------------------------------------------- registry

_REGISTRY: dict[str, type[BaseStrategy]] = {}


def register(cls: type[BaseStrategy]) -> type[BaseStrategy]:
    _REGISTRY[cls.meta.id] = cls
    return cls


def get_strategy_class(strategy_id: str) -> Optional[type[BaseStrategy]]:
    return _REGISTRY.get(strategy_id)


def all_strategies() -> dict[str, type[BaseStrategy]]:
    return dict(_REGISTRY)


DEFAULT_TRADE_CONFIG = {
    "symbol": "BTCUSDT",
    "interval": "15m",
    "leverage": 5,
    "risk_pct": 2.0,  # percent of equity risked per trade
    "max_positions": 1,
    "cooldown_sec": 300,
}

# Import built-ins so they self-register.
from . import aura_liam_max, liam_trader_9, ema_cross, rsi_reversal, macd_trend, bollinger_breakout  # noqa: E402,F401
from .custom import CustomRuleStrategy, make_custom_strategy  # noqa: E402,F401
