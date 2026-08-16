"""Strategy framework: indicators, base class, and an open registry.

No strategies ship built-in — the panel is a host for the user's own
strategies, added either as Python files (data/user_strategies/) or as
rule-based custom strategies built in the dashboard UI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

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


def stochastic(
    candles: list[dict], k_period: int = 14, smooth: int = 3, d_period: int = 3
) -> tuple[list[Optional[float]], list[Optional[float]]]:
    """Slow stochastic: %K (smoothed) and %D."""
    raw: list[Optional[float]] = [None] * len(candles)
    for i in range(k_period - 1, len(candles)):
        window = candles[i - k_period + 1 : i + 1]
        hi = max(c["high"] for c in window)
        lo = min(c["low"] for c in window)
        raw[i] = 50.0 if hi == lo else (candles[i]["close"] - lo) / (hi - lo) * 100
    known = [v for v in raw if v is not None]
    offset = len(raw) - len(known)
    k_s = sma(known, smooth)
    k: list[Optional[float]] = [None] * len(raw)
    for i, v in enumerate(k_s):
        k[offset + i] = v
    k_known = [v for v in k if v is not None]
    d_s = sma(k_known, d_period)
    d: list[Optional[float]] = [None] * len(raw)
    offset_d = len(k) - len(k_known)
    for i, v in enumerate(d_s):
        d[offset_d + i] = v
    return k, d


def stoch_rsi(values: list[float], period: int = 14) -> list[Optional[float]]:
    r = rsi(values, period)
    out: list[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        window = [v for v in r[max(0, i - period + 1) : i + 1] if v is not None]
        if len(window) < period:
            continue
        hi, lo = max(window), min(window)
        out[i] = 50.0 if hi == lo else (r[i] - lo) / (hi - lo) * 100
    return out


def williams_r(candles: list[dict], period: int = 14) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(candles)
    for i in range(period - 1, len(candles)):
        window = candles[i - period + 1 : i + 1]
        hi = max(c["high"] for c in window)
        lo = min(c["low"] for c in window)
        out[i] = -50.0 if hi == lo else -100 * (hi - candles[i]["close"]) / (hi - lo)
    return out


def cci(candles: list[dict], period: int = 20) -> list[Optional[float]]:
    tp = [(c["high"] + c["low"] + c["close"]) / 3 for c in candles]
    tp_sma = sma(tp, period)
    out: list[Optional[float]] = [None] * len(candles)
    for i in range(period - 1, len(candles)):
        m = tp_sma[i]
        if m is None:
            continue
        dev = sum(abs(v - m) for v in tp[i - period + 1 : i + 1]) / period
        out[i] = 0.0 if dev == 0 else (tp[i] - m) / (0.015 * dev)
    return out


def mfi(candles: list[dict], period: int = 14) -> list[Optional[float]]:
    tp = [(c["high"] + c["low"] + c["close"]) / 3 for c in candles]
    out: list[Optional[float]] = [None] * len(candles)
    for i in range(period, len(candles)):
        pos = neg = 0.0
        for j in range(i - period + 1, i + 1):
            flow = tp[j] * candles[j]["volume"]
            if tp[j] > tp[j - 1]:
                pos += flow
            elif tp[j] < tp[j - 1]:
                neg += flow
        out[i] = 100.0 if neg == 0 else 100 - 100 / (1 + pos / neg)
    return out


def adx(
    candles: list[dict], period: int = 14
) -> tuple[list[Optional[float]], list[Optional[float]], list[Optional[float]]]:
    """Wilder's ADX; returns (adx, +DI, -DI)."""
    n = len(candles)
    adx_out: list[Optional[float]] = [None] * n
    pdi_out: list[Optional[float]] = [None] * n
    mdi_out: list[Optional[float]] = [None] * n
    if n <= period * 2:
        return adx_out, pdi_out, mdi_out
    trs, pdms, mdms = [], [], []
    for i in range(1, n):
        c, p = candles[i], candles[i - 1]
        trs.append(max(c["high"] - c["low"], abs(c["high"] - p["close"]), abs(c["low"] - p["close"])))
        up, dn = c["high"] - p["high"], p["low"] - c["low"]
        pdms.append(up if up > dn and up > 0 else 0.0)
        mdms.append(dn if dn > up and dn > 0 else 0.0)
    s_tr, s_pdm, s_mdm = sum(trs[:period]), sum(pdms[:period]), sum(mdms[:period])
    dxs: list[float] = []
    for i in range(period, len(trs) + 1):
        if i > period:
            s_tr = s_tr - s_tr / period + trs[i - 1]
            s_pdm = s_pdm - s_pdm / period + pdms[i - 1]
            s_mdm = s_mdm - s_mdm / period + mdms[i - 1]
        pdi = 100 * s_pdm / s_tr if s_tr else 0.0
        mdi = 100 * s_mdm / s_tr if s_tr else 0.0
        pdi_out[i] = pdi
        mdi_out[i] = mdi
        dx = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0
        dxs.append(dx)
        if len(dxs) == period:
            adx_out[i] = sum(dxs) / period
        elif len(dxs) > period:
            adx_out[i] = (adx_out[i - 1] * (period - 1) + dx) / period
    return adx_out, pdi_out, mdi_out


def supertrend(
    candles: list[dict], period: int = 10, mult: float = 3.0
) -> list[Optional[int]]:
    """Direction only: +1 bullish, -1 bearish."""
    a = atr(candles, period)
    n = len(candles)
    dir_out: list[Optional[int]] = [None] * n
    up_band = dn_band = None
    direction = 1
    for i in range(n):
        if a[i] is None:
            continue
        mid = (candles[i]["high"] + candles[i]["low"]) / 2
        basic_up = mid + mult * a[i]
        basic_dn = mid - mult * a[i]
        close_prev = candles[i - 1]["close"] if i else candles[i]["close"]
        up_band = basic_up if up_band is None or basic_up < up_band or close_prev > up_band else up_band
        dn_band = basic_dn if dn_band is None or basic_dn > dn_band or close_prev < dn_band else dn_band
        close = candles[i]["close"]
        if close > up_band:
            direction = 1
        elif close < dn_band:
            direction = -1
        dir_out[i] = direction
    return dir_out


def psar(
    candles: list[dict], step: float = 0.02, max_step: float = 0.2
) -> list[Optional[float]]:
    n = len(candles)
    out: list[Optional[float]] = [None] * n
    if n < 3:
        return out
    bull = candles[1]["close"] > candles[0]["close"]
    sar = candles[0]["low"] if bull else candles[0]["high"]
    ep = candles[0]["high"] if bull else candles[0]["low"]
    af = step
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        c = candles[i]
        if bull:
            sar = min(sar, candles[i - 1]["low"], candles[i - 2]["low"] if i > 1 else candles[i - 1]["low"])
            if c["low"] < sar:
                bull, sar, ep, af = False, ep, c["low"], step
            elif c["high"] > ep:
                ep, af = c["high"], min(af + step, max_step)
        else:
            sar = max(sar, candles[i - 1]["high"], candles[i - 2]["high"] if i > 1 else candles[i - 1]["high"])
            if c["high"] > sar:
                bull, sar, ep, af = True, ep, c["high"], step
            elif c["low"] < ep:
                ep, af = c["low"], min(af + step, max_step)
        out[i] = sar
    return out


def obv(candles: list[dict]) -> list[float]:
    out = [0.0] * len(candles)
    for i in range(1, len(candles)):
        if candles[i]["close"] > candles[i - 1]["close"]:
            out[i] = out[i - 1] + candles[i]["volume"]
        elif candles[i]["close"] < candles[i - 1]["close"]:
            out[i] = out[i - 1] - candles[i]["volume"]
        else:
            out[i] = out[i - 1]
    return out


def vwap(candles: list[dict], period: int = 50) -> list[Optional[float]]:
    """Rolling VWAP over the last `period` bars."""
    out: list[Optional[float]] = [None] * len(candles)
    for i in range(period - 1, len(candles)):
        window = candles[i - period + 1 : i + 1]
        vol = sum(c["volume"] for c in window)
        if vol <= 0:
            continue
        out[i] = sum((c["high"] + c["low"] + c["close"]) / 3 * c["volume"] for c in window) / vol
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
    source: str = "builtin"  # builtin | custom | user
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
    "symbols": ["BTCUSDT"],
    "interval": "15m",
    "leverage": 5,
    "risk_pct": 2.0,  # percent of equity risked per trade
    "max_positions": 1,
    "cooldown_sec": 300,
}

from .custom import CustomRuleStrategy, INDICATOR_MENU, make_custom_strategy  # noqa: E402,F401
from .loader import load_user_strategies, save_user_strategy_code  # noqa: E402,F401
