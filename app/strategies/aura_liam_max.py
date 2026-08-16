"""Aura Liam Max — multi-confluence trend strategy.

Confluence of: EMA(21/55) trend alignment, RSI momentum zone, MACD histogram
expansion, volume confirmation. ATR-based stop loss and take profit
(risk:reward 1:2). Fires only when at least 4 of 5 factors agree.
"""

from __future__ import annotations

from typing import Optional

from . import BaseStrategy, Signal, StrategyMeta, atr, ema, macd, register, rsi, sma


@register
class AuraLiamMax(BaseStrategy):
    meta = StrategyMeta(
        id="aura_liam_max",
        name="Aura Liam Max",
        description="کانفلوئنس چندلایه: روند EMA 21/55 + مومنتوم RSI + هیستوگرام MACD + تایید حجم، با حد ضرر و حد سود مبتنی بر ATR (ریسک به ریوارد ۱:۲)",
        default_config={
            "ema_fast": 21,
            "ema_slow": 55,
            "rsi_period": 14,
            "atr_period": 14,
            "atr_sl_mult": 1.5,
            "rr_ratio": 2.0,
            "min_score": 4,
        },
    )

    def min_candles(self) -> int:
        return max(self.config["ema_slow"] * 2, 130)

    def analyze(self, candles: list[dict]) -> Optional[Signal]:
        cfg = self.config
        closes = [c["close"] for c in candles]
        volumes = [c["volume"] for c in candles]
        i = len(candles) - 1

        ema_f = ema(closes, cfg["ema_fast"])
        ema_s = ema(closes, cfg["ema_slow"])
        rsi_v = rsi(closes, cfg["rsi_period"])
        _, _, hist = macd(closes)
        atr_v = atr(candles, cfg["atr_period"])
        vol_ma = sma(volumes, 20)

        needed = (ema_f[i], ema_s[i], rsi_v[i], hist[i], hist[i - 1], atr_v[i], vol_ma[i])
        if any(v is None for v in needed):
            return None

        price = closes[i]
        long_score = 0
        short_score = 0

        # 1) trend alignment
        if ema_f[i] > ema_s[i]:
            long_score += 1
        elif ema_f[i] < ema_s[i]:
            short_score += 1
        # 2) price on the right side of fast EMA
        if price > ema_f[i]:
            long_score += 1
        elif price < ema_f[i]:
            short_score += 1
        # 3) RSI momentum zone (not overextended)
        if 52 <= rsi_v[i] <= 72:
            long_score += 1
        elif 28 <= rsi_v[i] <= 48:
            short_score += 1
        # 4) MACD histogram expanding in trade direction
        if hist[i] > 0 and hist[i] > hist[i - 1]:
            long_score += 1
        elif hist[i] < 0 and hist[i] < hist[i - 1]:
            short_score += 1
        # 5) volume above its 20-bar average
        if volumes[i] > vol_ma[i]:
            if long_score >= short_score:
                long_score += 1
            else:
                short_score += 1

        min_score = cfg["min_score"]
        sl_dist = atr_v[i] * cfg["atr_sl_mult"]
        if long_score >= min_score and long_score > short_score:
            return Signal(
                side="LONG",
                price=price,
                confidence=long_score / 5,
                reason=f"Aura confluence {long_score}/5 (EMA↑ RSI={rsi_v[i]:.0f} MACD↑)",
                sl=price - sl_dist,
                tp=price + sl_dist * cfg["rr_ratio"],
            )
        if short_score >= min_score and short_score > long_score:
            return Signal(
                side="SHORT",
                price=price,
                confidence=short_score / 5,
                reason=f"Aura confluence {short_score}/5 (EMA↓ RSI={rsi_v[i]:.0f} MACD↓)",
                sl=price + sl_dist,
                tp=price - sl_dist * cfg["rr_ratio"],
            )
        return None
