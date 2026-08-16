"""Rule-based custom strategies, definable from the dashboard UI.

A custom strategy is a JSON document of conditions per direction, e.g.:

    {
      "name": "استراتژی من",
      "long":  [{"indicator": "rsi", "op": "<", "value": 30},
                {"indicator": "ema_fast_above_slow", "op": "==", "value": 1}],
      "short": [{"indicator": "rsi", "op": ">", "value": 70}],
      "atr_sl_mult": 1.5, "rr_ratio": 2.0
    }

All listed conditions for a direction must hold on the latest closed candle.
Supported indicators: rsi, macd_hist, macd_line, close, ema_fast_above_slow
(1/0, uses ema_fast/ema_slow config), bb_pos (position between Bollinger
bands, 0=lower 1=upper), vol_ratio (volume / 20-bar average).
"""

from __future__ import annotations

import operator
from typing import Optional

from . import BaseStrategy, Signal, StrategyMeta, atr, bollinger, ema, macd, rsi, sma

_OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq}


class CustomRuleStrategy(BaseStrategy):
    """Instantiated dynamically via make_custom_strategy()."""

    meta = StrategyMeta(
        id="_custom_template",
        name="Custom",
        description="",
        builtin=False,
        default_config={"ema_fast": 12, "ema_slow": 26, "atr_sl_mult": 1.5, "rr_ratio": 2.0},
    )
    rules: dict = {}

    def min_candles(self) -> int:
        return 120

    def _indicator_values(self, candles: list[dict]) -> Optional[dict]:
        closes = [c["close"] for c in candles]
        volumes = [c["volume"] for c in candles]
        i = len(candles) - 1
        r = rsi(closes, 14)
        line, sig, hist = macd(closes)
        f = ema(closes, int(self.config.get("ema_fast", 12)))
        s = ema(closes, int(self.config.get("ema_slow", 26)))
        upper, mid, lower = bollinger(closes, 20, 2.0)
        vol_ma = sma(volumes, 20)
        if any(v is None for v in (r[i], line[i], hist[i], f[i], s[i], upper[i], lower[i], vol_ma[i])):
            return None
        band = upper[i] - lower[i]
        return {
            "rsi": r[i],
            "macd_line": line[i],
            "macd_hist": hist[i],
            "close": closes[i],
            "ema_fast_above_slow": 1.0 if f[i] > s[i] else 0.0,
            "bb_pos": (closes[i] - lower[i]) / band if band > 0 else 0.5,
            "vol_ratio": volumes[i] / vol_ma[i] if vol_ma[i] else 1.0,
        }

    def _check(self, conditions: list[dict], values: dict) -> bool:
        if not conditions:
            return False
        for cond in conditions:
            ind = values.get(cond.get("indicator"))
            op = _OPS.get(cond.get("op"))
            if ind is None or op is None:
                return False
            try:
                if not op(ind, float(cond.get("value"))):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    def analyze(self, candles: list[dict]) -> Optional[Signal]:
        values = self._indicator_values(candles)
        if values is None:
            return None
        i = len(candles) - 1
        price = candles[i]["close"]
        a = atr(candles, 14)
        if a[i] is None:
            return None
        sl_dist = a[i] * float(self.config.get("atr_sl_mult", 1.5))
        rr = float(self.config.get("rr_ratio", 2.0))
        if self._check(self.rules.get("long", []), values):
            return Signal(
                side="LONG", price=price, confidence=0.5,
                reason=f"قوانین سفارشی «{self.meta.name}» (لانگ)",
                sl=price - sl_dist, tp=price + sl_dist * rr,
            )
        if self._check(self.rules.get("short", []), values):
            return Signal(
                side="SHORT", price=price, confidence=0.5,
                reason=f"قوانین سفارشی «{self.meta.name}» (شورت)",
                sl=price + sl_dist, tp=price - sl_dist * rr,
            )
        return None


def make_custom_strategy(strategy_id: str, definition: dict) -> type[CustomRuleStrategy]:
    """Build a registrable strategy class from a JSON rule definition."""
    meta = StrategyMeta(
        id=strategy_id,
        name=definition.get("name", strategy_id),
        description=definition.get("description", "استراتژی سفارشی مبتنی بر قوانین"),
        builtin=False,
        default_config={
            "ema_fast": definition.get("ema_fast", 12),
            "ema_slow": definition.get("ema_slow", 26),
            "atr_sl_mult": definition.get("atr_sl_mult", 1.5),
            "rr_ratio": definition.get("rr_ratio", 2.0),
        },
    )
    rules = {"long": definition.get("long", []), "short": definition.get("short", [])}
    return type(
        f"Custom_{strategy_id}",
        (CustomRuleStrategy,),
        {"meta": meta, "rules": rules},
    )
