"""RSI Reversal — mean-reversion from oversold/overbought extremes."""

from __future__ import annotations

from typing import Optional

from . import BaseStrategy, Signal, StrategyMeta, atr, register, rsi


@register
class RsiReversal(BaseStrategy):
    meta = StrategyMeta(
        id="rsi_reversal",
        name="RSI Reversal",
        description="بازگشت از اشباع خرید/فروش: ورود وقتی RSI از زیر ۳۰ یا بالای ۷۰ برمی‌گردد — مناسب بازارهای رنج",
        default_config={
            "period": 14,
            "oversold": 30,
            "overbought": 70,
            "atr_period": 14,
            "atr_sl_mult": 1.5,
            "rr_ratio": 1.5,
        },
    )

    def min_candles(self) -> int:
        return 80

    def analyze(self, candles: list[dict]) -> Optional[Signal]:
        cfg = self.config
        closes = [c["close"] for c in candles]
        i = len(candles) - 1
        r = rsi(closes, cfg["period"])
        a = atr(candles, cfg["atr_period"])
        if any(v is None for v in (r[i], r[i - 1], a[i])):
            return None
        price = closes[i]
        sl_dist = a[i] * cfg["atr_sl_mult"]
        if r[i - 1] < cfg["oversold"] <= r[i]:
            return Signal(
                side="LONG",
                price=price,
                confidence=0.55,
                reason=f"بازگشت RSI از اشباع فروش ({r[i - 1]:.0f}→{r[i]:.0f})",
                sl=price - sl_dist,
                tp=price + sl_dist * cfg["rr_ratio"],
            )
        if r[i - 1] > cfg["overbought"] >= r[i]:
            return Signal(
                side="SHORT",
                price=price,
                confidence=0.55,
                reason=f"بازگشت RSI از اشباع خرید ({r[i - 1]:.0f}→{r[i]:.0f})",
                sl=price + sl_dist,
                tp=price - sl_dist * cfg["rr_ratio"],
            )
        return None
