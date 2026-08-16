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
    aroon,
    atr,
    awesome_oscillator,
    bollinger,
    cci,
    classic_pivot,
    cmf,
    donchian,
    ema,
    heikin_ashi_trend,
    hull,
    ichimoku,
    keltner,
    macd,
    mfi,
    obv,
    psar,
    roc,
    rsi,
    sma,
    squeeze_momentum,
    stoch_rsi,
    stochastic,
    supertrend,
    swing_points,
    vwap,
    wavetrend,
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
    # ── محبوب‌ترین‌های TradingView ──
    {"id": "wt1", "label": "WaveTrend خط اصلی (WT1)", "hint": "±60 مرزهای اشباع"},
    {"id": "wt2", "label": "WaveTrend خط سیگنال (WT2)", "hint": ""},
    {"id": "wt_cross", "label": "کراس WaveTrend", "hint": "1 = WT1 بالای WT2"},
    {"id": "squeeze_on", "label": "Squeeze فعال (BB داخل KC)", "hint": "1 = فشردگی، آماده انفجار"},
    {"id": "squeeze_mom", "label": "مومنتوم Squeeze", "hint": "مثبت = صعودی"},
    {"id": "ichimoku_bull", "label": "قیمت بالای ابر ایچیموکو", "hint": "1 یا 0"},
    {"id": "tenkan_vs_kijun", "label": "تنکان بالای کیجون (ایچیموکو)", "hint": "1 یا 0"},
    {"id": "keltner_pos", "label": "موقعیت در کانال کلتنر", "hint": "0=پایین، 1=بالا"},
    {"id": "donchian_pos", "label": "موقعیت در کانال دانچین", "hint": "0=کف 20 کندل، 1=سقف"},
    {"id": "hull_rising", "label": "Hull MA صعودی (HMA21)", "hint": "1 یا 0"},
    {"id": "ao", "label": "Awesome Oscillator", "hint": "مثبت = صعودی"},
    {"id": "cmf", "label": "Chaikin Money Flow (20)", "hint": "مثبت = ورود پول"},
    {"id": "roc_10", "label": "ROC نرخ تغییر ۱۰ کندل ٪", "hint": "درصد"},
    {"id": "aroon_up", "label": "Aroon Up (25)", "hint": "0 تا 100"},
    {"id": "aroon_down", "label": "Aroon Down (25)", "hint": "0 تا 100"},
    {"id": "pivot_diff_pct", "label": "فاصله از پیوت کلاسیک ٪", "hint": "مثبت = بالای پیوت"},
    {"id": "heikin_trend", "label": "روند هیکین‌آشی", "hint": "1 صعودی، -1 نزولی"},
    {"id": "bos_bull", "label": "شکست ساختار صعودی (BOS)", "hint": "1 = عبور از سقف سوینگ"},
    {"id": "bos_bear", "label": "شکست ساختار نزولی (BOS)", "hint": "1 = عبور از کف سوینگ"},
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

    wt1, wt2 = wavetrend(candles)
    sq_on, sq_mom = squeeze_momentum(candles, 20)
    tenkan, kijun, senkou_a, senkou_b = ichimoku(candles)
    kel_u, kel_m, kel_l = keltner(candles, 20, 2.0)
    don_h, don_l = donchian(candles, 20)
    hma = hull(closes, 21)
    ao_v = awesome_oscillator(candles)
    cmf_v = cmf(candles, 20)
    roc_v = roc(closes, 10)
    ar_up, ar_dn = aroon(candles, 25)
    pivot = classic_pivot(candles, 24)
    ha_trend = heikin_ashi_trend(candles)
    swing_hi, swing_lo = swing_points(candles, 2)

    core = (r[i], k[i], d[i], line[i], sig[i], hist[i], e9[i], e20[i], e21[i], e50[i],
            e200[i], upper[i], lower[i], adx_v[i], pdi[i], mdi[i], cci_v[i], mfi_v[i],
            wr[i], st_dir[i], ps[i], vw[i], a[i], vol_ma[i], srsi[i],
            wt1[i], wt2[i], sq_on, sq_mom, tenkan, kijun, senkou_a, senkou_b,
            kel_u[i], kel_l[i], don_h[i], don_l[i], hma[i], hma[i - 3],
            ao_v[i], cmf_v[i], roc_v[i], ar_up[i], ar_dn[i], pivot, ha_trend)
    if any(v is None for v in core):
        return None

    price = closes[i]
    band = upper[i] - lower[i]
    kel_band = kel_u[i] - kel_l[i]
    don_band = don_h[i] - don_l[i]
    cloud_top = max(senkou_a, senkou_b)
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
        "wt1": wt1[i],
        "wt2": wt2[i],
        "wt_cross": 1.0 if wt1[i] > wt2[i] else 0.0,
        "squeeze_on": 1.0 if sq_on else 0.0,
        "squeeze_mom": sq_mom,
        "ichimoku_bull": 1.0 if price > cloud_top else 0.0,
        "tenkan_vs_kijun": 1.0 if tenkan > kijun else 0.0,
        "keltner_pos": (price - kel_l[i]) / kel_band if kel_band > 0 else 0.5,
        "donchian_pos": (price - don_l[i]) / don_band if don_band > 0 else 0.5,
        "hull_rising": 1.0 if hma[i] > hma[i - 3] else 0.0,
        "ao": ao_v[i],
        "cmf": cmf_v[i],
        "roc_10": roc_v[i],
        "aroon_up": ar_up[i],
        "aroon_down": ar_dn[i],
        "pivot_diff_pct": (price - pivot) / pivot * 100 if pivot else 0.0,
        "heikin_trend": float(ha_trend),
        "bos_bull": 1.0 if swing_hi is not None and price > swing_hi else 0.0,
        "bos_bear": 1.0 if swing_lo is not None and price < swing_lo else 0.0,
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
