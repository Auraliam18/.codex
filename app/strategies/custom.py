"""Rule-based custom strategies, definable from the dashboard UI.

A custom strategy is a JSON document of conditions per direction. All listed
conditions for a direction must hold on the latest closed candle. The
indicator menu below covers the major indicators; each entry computes one
numeric value on the latest bar that conditions compare against.
"""

from __future__ import annotations

import operator
from typing import Optional

from . import (
    BaseStrategy,
    Signal,
    StrategyMeta,
    adx,
    atr,
    bollinger,
    cci,
    ema,
    macd,
    mfi,
    obv,
    psar,
    rsi,
    sma,
    stoch_rsi,
    stochastic,
    supertrend,
    vwap,
    williams_r,
)

_OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq}

# id -> (Persian label, hint about the value range)
INDICATOR_MENU: list[dict] = [
    {"id": "rsi", "label": "RSI (14)", "hint": "0 تا 100"},
    {"id": "stoch_k", "label": "استوکاستیک %K (14,3)", "hint": "0 تا 100"},
    {"id": "stoch_d", "label": "استوکاستیک %D", "hint": "0 تا 100"},
    {"id": "stoch_rsi", "label": "Stochastic RSI", "hint": "0 تا 100"},
    {"id": "macd_line", "label": "خط MACD", "hint": "مثبت = صعودی"},
    {"id": "macd_signal", "label": "خط سیگنال MACD", "hint": ""},
    {"id": "macd_hist", "label": "هیستوگرام MACD", "hint": "مثبت = صعودی"},
    {"id": "macd_cross", "label": "کراس MACD", "hint": "1 = خط بالای سیگنال"},
    {"id": "ema9_vs_21", "label": "EMA9 بالای EMA21", "hint": "1 یا 0"},
    {"id": "ema21_vs_50", "label": "EMA21 بالای EMA50", "hint": "1 یا 0"},
    {"id": "ema50_vs_200", "label": "EMA50 بالای EMA200", "hint": "1 یا 0"},
    {"id": "price_vs_ema20", "label": "قیمت بالای EMA20", "hint": "1 یا 0"},
    {"id": "price_vs_ema50", "label": "قیمت بالای EMA50", "hint": "1 یا 0"},
    {"id": "price_vs_ema200", "label": "قیمت بالای EMA200", "hint": "1 یا 0"},
    {"id": "bb_pos", "label": "موقعیت در باند بولینگر", "hint": "0=باند پایین، 1=باند بالا"},
    {"id": "bb_width_pct", "label": "پهنای باند بولینگر ٪", "hint": "نوسان بازار"},
    {"id": "adx", "label": "ADX (14)", "hint": "بالای 25 = روند قوی"},
    {"id": "plus_di", "label": "+DI", "hint": "0 تا 100"},
    {"id": "minus_di", "label": "-DI", "hint": "0 تا 100"},
    {"id": "cci", "label": "CCI (20)", "hint": "±100 مرزها"},
    {"id": "mfi", "label": "MFI (14)", "hint": "0 تا 100"},
    {"id": "willr", "label": "Williams %R (14)", "hint": "-100 تا 0"},
    {"id": "supertrend_dir", "label": "جهت SuperTrend (10,3)", "hint": "1 صعودی، -1 نزولی"},
    {"id": "psar_bull", "label": "PSAR زیر قیمت", "hint": "1 = صعودی"},
    {"id": "vwap_diff_pct", "label": "فاصله قیمت از VWAP ٪", "hint": "مثبت = بالای VWAP"},
    {"id": "atr_pct", "label": "ATR نسبت به قیمت ٪", "hint": "نوسان"},
    {"id": "vol_ratio", "label": "نسبت حجم به میانگین 20", "hint": "بالای 1 = حجم بالا"},
    {"id": "obv_slope", "label": "شیب OBV (10 کندل)", "hint": "مثبت = ورود پول"},
    {"id": "momentum_5", "label": "مومنتوم ۵ کندل ٪", "hint": "درصد تغییر"},
    {"id": "close", "label": "قیمت پایانی", "hint": "مقدار خام"},
]


def compute_indicator_values(candles: list[dict]) -> Optional[dict]:
    """All menu indicators evaluated on the latest closed candle."""
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    i = len(candles) - 1

    r = rsi(closes, 14)
    k, d = stochastic(candles)
    srsi = stoch_rsi(closes, 14)
    line, sig, hist = macd(closes)
    e9, e20, e21, e50, e200 = (ema(closes, p) for p in (9, 20, 21, 50, 200))
    upper, mid, lower = bollinger(closes, 20, 2.0)
    adx_v, pdi, mdi = adx(candles, 14)
    cci_v = cci(candles, 20)
    mfi_v = mfi(candles, 14)
    wr = williams_r(candles, 14)
    st_dir = supertrend(candles, 10, 3.0)
    ps = psar(candles)
    vw = vwap(candles, 50)
    a = atr(candles, 14)
    vol_ma = sma(volumes, 20)
    obv_v = obv(candles)

    core = (r[i], k[i], d[i], line[i], sig[i], hist[i], e9[i], e20[i], e21[i], e50[i],
            e200[i], upper[i], lower[i], adx_v[i], pdi[i], mdi[i], cci_v[i], mfi_v[i],
            wr[i], st_dir[i], ps[i], vw[i], a[i], vol_ma[i], srsi[i])
    if any(v is None for v in core):
        return None

    price = closes[i]
    band = upper[i] - lower[i]
    return {
        "rsi": r[i],
        "stoch_k": k[i],
        "stoch_d": d[i],
        "stoch_rsi": srsi[i],
        "macd_line": line[i],
        "macd_signal": sig[i],
        "macd_hist": hist[i],
        "macd_cross": 1.0 if line[i] > sig[i] else 0.0,
        "ema9_vs_21": 1.0 if e9[i] > e21[i] else 0.0,
        "ema21_vs_50": 1.0 if e21[i] > e50[i] else 0.0,
        "ema50_vs_200": 1.0 if e50[i] > e200[i] else 0.0,
        "price_vs_ema20": 1.0 if price > e20[i] else 0.0,
        "price_vs_ema50": 1.0 if price > e50[i] else 0.0,
        "price_vs_ema200": 1.0 if price > e200[i] else 0.0,
        "bb_pos": (price - lower[i]) / band if band > 0 else 0.5,
        "bb_width_pct": band / mid[i] * 100 if mid[i] else 0.0,
        "adx": adx_v[i],
        "plus_di": pdi[i],
        "minus_di": mdi[i],
        "cci": cci_v[i],
        "mfi": mfi_v[i],
        "willr": wr[i],
        "supertrend_dir": float(st_dir[i]),
        "psar_bull": 1.0 if ps[i] < price else 0.0,
        "vwap_diff_pct": (price - vw[i]) / vw[i] * 100 if vw[i] else 0.0,
        "atr_pct": a[i] / price * 100 if price else 0.0,
        "vol_ratio": volumes[i] / vol_ma[i] if vol_ma[i] else 1.0,
        "obv_slope": obv_v[i] - obv_v[i - 10] if i >= 10 else 0.0,
        "momentum_5": (price - closes[i - 5]) / closes[i - 5] * 100 if i >= 5 else 0.0,
        "close": price,
    }


class CustomRuleStrategy(BaseStrategy):
    """Instantiated dynamically via make_custom_strategy()."""

    meta = StrategyMeta(
        id="_custom_template",
        name="Custom",
        description="",
        builtin=False,
        source="custom",
        default_config={"atr_sl_mult": 1.5, "rr_ratio": 2.0},
    )
    rules: dict = {}

    def min_candles(self) -> int:
        return 220  # EMA200 + warmup

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
        values = compute_indicator_values(candles)
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
                reason=f"قوانین «{self.meta.name}» (لانگ)",
                sl=price - sl_dist, tp=price + sl_dist * rr,
            )
        if self._check(self.rules.get("short", []), values):
            return Signal(
                side="SHORT", price=price, confidence=0.5,
                reason=f"قوانین «{self.meta.name}» (شورت)",
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
        source="custom",
        default_config={
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
