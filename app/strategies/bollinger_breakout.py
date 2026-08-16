"""Bollinger Breakout — volatility breakout with volume confirmation."""

from __future__ import annotations

from typing import Optional

from . import BaseStrategy, Signal, StrategyMeta, atr, bollinger, register, sma


@register
class BollingerBreakout(BaseStrategy):
    meta = StrategyMeta(
        id="bollinger_breakout",
        name="Bollinger Breakout",
        description="شکست باند بولینگر با تایید حجم — ورود روی کندل شکست، حد ضرر روی خط میانی",
        default_config={
            "period": 20,
            "mult": 2.0,
            "atr_period": 14,
            "rr_ratio": 1.8,
        },
    )

    def min_candles(self) -> int:
        return 90

    def analyze(self, candles: list[dict]) -> Optional[Signal]:
        cfg = self.config
        closes = [c["close"] for c in candles]
        volumes = [c["volume"] for c in candles]
        i = len(candles) - 1
        upper, mid, lower = bollinger(closes, cfg["period"], cfg["mult"])
        vol_ma = sma(volumes, 20)
        a = atr(candles, cfg["atr_period"])
        if any(v is None for v in (upper[i], upper[i - 1], mid[i], lower[i], lower[i - 1], vol_ma[i], a[i])):
            return None
        price = closes[i]
        vol_ok = volumes[i] > vol_ma[i] * 1.2
        if closes[i - 1] <= upper[i - 1] and price > upper[i] and vol_ok:
            sl = mid[i]
            return Signal(
                side="LONG",
                price=price,
                confidence=0.6,
                reason="شکست باند بالایی بولینگر با حجم",
                sl=sl,
                tp=price + (price - sl) * cfg["rr_ratio"],
            )
        if closes[i - 1] >= lower[i - 1] and price < lower[i] and vol_ok:
            sl = mid[i]
            return Signal(
                side="SHORT",
                price=price,
                confidence=0.6,
                reason="شکست باند پایینی بولینگر با حجم",
                sl=sl,
                tp=price - (sl - price) * cfg["rr_ratio"],
            )
        return None
