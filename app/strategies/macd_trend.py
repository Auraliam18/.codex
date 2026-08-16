"""MACD Trend — MACD signal-line cross filtered by the long-term trend."""

from __future__ import annotations

from typing import Optional

from . import BaseStrategy, Signal, StrategyMeta, atr, ema, macd, register


@register
class MacdTrend(BaseStrategy):
    meta = StrategyMeta(
        id="macd_trend",
        name="MACD Trend",
        description="کراس MACD با فیلتر روند EMA200 — فقط در جهت روند اصلی معامله می‌کند",
        default_config={
            "trend_ema": 100,
            "atr_period": 14,
            "atr_sl_mult": 1.8,
            "rr_ratio": 2.0,
        },
    )

    def min_candles(self) -> int:
        return self.config["trend_ema"] + 60

    def analyze(self, candles: list[dict]) -> Optional[Signal]:
        cfg = self.config
        closes = [c["close"] for c in candles]
        i = len(candles) - 1
        line, sig, _ = macd(closes)
        trend = ema(closes, cfg["trend_ema"])
        a = atr(candles, cfg["atr_period"])
        if any(v is None for v in (line[i], line[i - 1], sig[i], sig[i - 1], trend[i], a[i])):
            return None
        price = closes[i]
        sl_dist = a[i] * cfg["atr_sl_mult"]
        crossed_up = line[i - 1] <= sig[i - 1] and line[i] > sig[i]
        crossed_down = line[i - 1] >= sig[i - 1] and line[i] < sig[i]
        if crossed_up and price > trend[i]:
            return Signal(
                side="LONG",
                price=price,
                confidence=0.65,
                reason="کراس صعودی MACD همسو با روند",
                sl=price - sl_dist,
                tp=price + sl_dist * cfg["rr_ratio"],
            )
        if crossed_down and price < trend[i]:
            return Signal(
                side="SHORT",
                price=price,
                confidence=0.65,
                reason="کراس نزولی MACD همسو با روند",
                sl=price + sl_dist,
                tp=price - sl_dist * cfg["rr_ratio"],
            )
        return None
