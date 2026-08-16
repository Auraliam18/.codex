"""Liam Trader 9 — nine-factor scoring system.

Scores nine independent conditions per direction (EMA9 cross, trend stack,
RSI, MACD line & histogram, Bollinger position, momentum, volume, market
structure). Trades when a direction reaches the threshold score.
"""

from __future__ import annotations

from typing import Optional

from . import (
    BaseStrategy,
    Signal,
    StrategyMeta,
    atr,
    bollinger,
    ema,
    macd,
    register,
    rsi,
    sma,
)


@register
class LiamTrader9(BaseStrategy):
    meta = StrategyMeta(
        id="liam_trader_9",
        name="Liam Trader 9",
        description="سیستم امتیازدهی ۹ فاکتوره: کراس EMA9، پشته روند، RSI، خط و هیستوگرام MACD، موقعیت بولینگر، مومنتوم، حجم و ساختار بازار — ورود با امتیاز ۷ از ۹",
        default_config={
            "min_score": 7,
            "atr_period": 14,
            "atr_sl_mult": 1.8,
            "rr_ratio": 1.8,
        },
    )

    def min_candles(self) -> int:
        return 160

    def analyze(self, candles: list[dict]) -> Optional[Signal]:
        cfg = self.config
        closes = [c["close"] for c in candles]
        volumes = [c["volume"] for c in candles]
        i = len(candles) - 1

        ema9 = ema(closes, 9)
        ema21 = ema(closes, 21)
        ema50 = ema(closes, 50)
        rsi_v = rsi(closes, 14)
        line, sig, hist = macd(closes)
        upper, mid, lower = bollinger(closes, 20, 2.0)
        atr_v = atr(candles, cfg["atr_period"])
        vol_ma = sma(volumes, 20)

        needed = (
            ema9[i], ema9[i - 1], ema21[i], ema21[i - 1], ema50[i],
            rsi_v[i], line[i], sig[i], hist[i], hist[i - 1],
            upper[i], mid[i], lower[i], atr_v[i], vol_ma[i],
        )
        if any(v is None for v in needed):
            return None

        price = closes[i]
        long_s = 0
        short_s = 0

        # 1) EMA9 vs EMA21 cross state
        if ema9[i] > ema21[i]:
            long_s += 1
        else:
            short_s += 1
        # 2) fresh cross within last bar strengthens
        if ema9[i - 1] <= ema21[i - 1] and ema9[i] > ema21[i]:
            long_s += 1
        elif ema9[i - 1] >= ema21[i - 1] and ema9[i] < ema21[i]:
            short_s += 1
        # 3) trend stack with EMA50
        if ema21[i] > ema50[i]:
            long_s += 1
        else:
            short_s += 1
        # 4) RSI direction
        if 50 < rsi_v[i] < 75:
            long_s += 1
        elif 25 < rsi_v[i] < 50:
            short_s += 1
        # 5) MACD line vs signal
        if line[i] > sig[i]:
            long_s += 1
        else:
            short_s += 1
        # 6) MACD histogram expanding
        if hist[i] > hist[i - 1]:
            long_s += 1
        else:
            short_s += 1
        # 7) Bollinger position: above mid but not over upper band
        if mid[i] < price < upper[i]:
            long_s += 1
        elif lower[i] < price < mid[i]:
            short_s += 1
        # 8) momentum: close vs close 5 bars ago
        if price > closes[i - 5]:
            long_s += 1
        else:
            short_s += 1
        # 9) volume confirmation
        if volumes[i] > vol_ma[i]:
            if long_s >= short_s:
                long_s += 1
            else:
                short_s += 1

        min_score = cfg["min_score"]
        sl_dist = atr_v[i] * cfg["atr_sl_mult"]
        if long_s >= min_score and long_s > short_s:
            return Signal(
                side="LONG",
                price=price,
                confidence=long_s / 9,
                reason=f"Liam9 score {long_s}/9 صعودی",
                sl=price - sl_dist,
                tp=price + sl_dist * cfg["rr_ratio"],
            )
        if short_s >= min_score and short_s > long_s:
            return Signal(
                side="SHORT",
                price=price,
                confidence=short_s / 9,
                reason=f"Liam9 score {short_s}/9 نزولی",
                sl=price + sl_dist,
                tp=price - sl_dist * cfg["rr_ratio"],
            )
        return None
