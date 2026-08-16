"""EMA Cross — classic golden/death cross with ATR stops."""

from __future__ import annotations

from typing import Optional

from . import BaseStrategy, Signal, StrategyMeta, atr, ema, register


@register
class EmaCross(BaseStrategy):
    meta = StrategyMeta(
        id="ema_cross",
        name="EMA Cross",
        description="کراس کلاسیک EMA سریع/کند (پیش‌فرض ۱۲/۲۶) با حد ضرر ATR — مناسب بازارهای رونددار",
        default_config={
            "fast": 12,
            "slow": 26,
            "atr_period": 14,
            "atr_sl_mult": 2.0,
            "rr_ratio": 2.0,
        },
    )

    def min_candles(self) -> int:
        return max(self.config["slow"] * 3, 100)

    def analyze(self, candles: list[dict]) -> Optional[Signal]:
        cfg = self.config
        closes = [c["close"] for c in candles]
        i = len(candles) - 1
        f = ema(closes, cfg["fast"])
        s = ema(closes, cfg["slow"])
        a = atr(candles, cfg["atr_period"])
        if any(v is None for v in (f[i], f[i - 1], s[i], s[i - 1], a[i])):
            return None
        price = closes[i]
        sl_dist = a[i] * cfg["atr_sl_mult"]
        if f[i - 1] <= s[i - 1] and f[i] > s[i]:
            return Signal(
                side="LONG",
                price=price,
                confidence=0.6,
                reason=f"کراس صعودی EMA{cfg['fast']}/{cfg['slow']}",
                sl=price - sl_dist,
                tp=price + sl_dist * cfg["rr_ratio"],
            )
        if f[i - 1] >= s[i - 1] and f[i] < s[i]:
            return Signal(
                side="SHORT",
                price=price,
                confidence=0.6,
                reason=f"کراس نزولی EMA{cfg['fast']}/{cfg['slow']}",
                sl=price + sl_dist,
                tp=price - sl_dist * cfg["rr_ratio"],
            )
        return None
