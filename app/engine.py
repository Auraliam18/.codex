"""Trading engine.

Runs one async loop per enabled strategy. Each loop walks the strategy's
watchlist symbols: fetch klines from Bitunix, ask the strategy for a signal,
apply the global risk rules (daily loss cap, open-position cap, leverage cap),
size the position from equity and risk %, then execute — on the paper broker
in demo mode, or on Bitunix futures in live mode. Every state change is
broadcast to the dashboard over WebSocket.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import store
from .bitunix import BitunixClient, BitunixError
from .strategies import (
    DEFAULT_TRADE_CONFIG,
    Signal,
    all_strategies,
    get_strategy_class,
    load_user_strategies,
    make_custom_strategy,
    save_user_strategy_code,
)
from .strategies import _REGISTRY  # registry is intentionally open
from .strategies.loader import delete_user_strategy_file

POLL_SECONDS = 10
MAX_LOG = 200
MAX_SIGNALS = 100


def _strategy_symbols(cfg: dict) -> list[str]:
    """Watchlist for a strategy; tolerates the legacy single-symbol key."""
    symbols = cfg.get("symbols")
    if not symbols:
        symbols = [cfg.get("symbol", "BTCUSDT")]
    return [s.strip().upper() for s in symbols if s and s.strip()]


class PaperBroker:
    """Simulated futures account: market fills, SL/TP monitoring, leveraged PnL."""

    def __init__(self, balance: float):
        self.balance = balance
        self.positions: dict[str, dict] = {}

    def open(self, symbol: str, side: str, price: float, qty: float, leverage: int,
             sl: Optional[float], tp: Optional[float], strategy_id: str) -> dict:
        pos_id = uuid.uuid4().hex[:12]
        margin = price * qty / max(leverage, 1)
        pos = {
            "id": pos_id, "symbol": symbol, "side": side, "entry": price,
            "qty": qty, "leverage": leverage, "margin": margin,
            "sl": sl, "tp": tp, "strategy_id": strategy_id,
            "opened_at": int(time.time() * 1000), "mark": price, "pnl": 0.0,
        }
        self.balance -= margin
        self.positions[pos_id] = pos
        return pos

    def mark(self, symbol: str, price: float) -> list[dict]:
        """Update mark price; return positions closed by SL/TP."""
        closed = []
        for pos in list(self.positions.values()):
            if pos["symbol"] != symbol:
                continue
            pos["mark"] = price
            direction = 1 if pos["side"] == "LONG" else -1
            pos["pnl"] = (price - pos["entry"]) * direction * pos["qty"]
            hit_sl = pos["sl"] is not None and (
                price <= pos["sl"] if direction == 1 else price >= pos["sl"])
            hit_tp = pos["tp"] is not None and (
                price >= pos["tp"] if direction == 1 else price <= pos["tp"])
            if hit_sl or hit_tp:
                exit_price = pos["sl"] if hit_sl else pos["tp"]
                closed.append(self.close(pos["id"], exit_price, "SL" if hit_sl else "TP"))
        return [c for c in closed if c]

    def close(self, pos_id: str, price: float, reason: str = "MANUAL") -> Optional[dict]:
        pos = self.positions.pop(pos_id, None)
        if not pos:
            return None
        direction = 1 if pos["side"] == "LONG" else -1
        pnl = (price - pos["entry"]) * direction * pos["qty"]
        self.balance += pos["margin"] + pnl
        return {**pos, "exit": price, "pnl": pnl, "close_reason": reason,
                "closed_at": int(time.time() * 1000)}


class Engine:
    def __init__(self):
        self.config = store.load_config()
        self.trades: list[dict] = store.load_trades()
        self.client = BitunixClient(self.config["api_key"], self.config["secret_key"])
        self.paper = PaperBroker(float(self.config.get("paper_balance", 10000.0)))
        self.running = False
        self.signals: list[dict] = []
        self.executions: list[dict] = []  # orders actually sent/opened, per strategy
        self.logs: list[dict] = []
        self.live_account: dict = {}
        self.live_positions: list[dict] = []
        self.last_prices: dict[str, float] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._cooldowns: dict[str, float] = {}
        self._listeners: list[Callable[[dict], Any]] = []
        self.user_files: dict[str, str] = {}  # strategy_id -> filename
        self._load_custom_strategies()
        self.user_files = load_user_strategies()

    # ------------------------------------------------------------- lifecycle

    def _load_custom_strategies(self) -> None:
        for sid, definition in self.config.get("custom_strategies", {}).items():
            _REGISTRY[sid] = make_custom_strategy(sid, definition)

    def add_listener(self, fn: Callable[[dict], Any]) -> None:
        self._listeners.append(fn)

    def remove_listener(self, fn: Callable[[dict], Any]) -> None:
        if fn in self._listeners:
            self._listeners.remove(fn)

    async def _broadcast(self, event: str, payload: Any = None) -> None:
        msg = {"event": event, "payload": payload, "ts": int(time.time() * 1000)}
        for fn in list(self._listeners):
            try:
                res = fn(msg)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                self._listeners.remove(fn)

    def log(self, level: str, text: str) -> None:
        self.logs.append({"ts": int(time.time() * 1000), "level": level, "text": text})
        self.logs = self.logs[-MAX_LOG:]

    async def start(self) -> None:
        if self.running:
            return
        if self.config.get("mode") == "live" and not self.client.has_keys:
            self.log("error", "حالت واقعی فعال است ولی کلید API تنظیم نشده — از تنظیمات وارد کنید")
            await self._broadcast("engine", {"running": False})
            return
        self.running = True
        self.log("info", f"موتور معاملات روشن شد (حالت {'واقعی' if self.config.get('mode') == 'live' else 'دمو'})")
        for sid, st in self.config.get("strategies", {}).items():
            if st.get("enabled"):
                self._spawn(sid)
        await self._broadcast("engine", {"running": True})

    async def stop(self) -> None:
        self.running = False
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()
        self.log("info", "موتور معاملات خاموش شد")
        await self._broadcast("engine", {"running": False})

    def _spawn(self, strategy_id: str) -> None:
        if strategy_id in self._tasks:
            return
        cls = get_strategy_class(strategy_id)
        if not cls:
            self.log("error", f"استراتژی {strategy_id} یافت نشد")
            return
        self._tasks[strategy_id] = asyncio.create_task(self._run_strategy(strategy_id))

    def _despawn(self, strategy_id: str) -> None:
        task = self._tasks.pop(strategy_id, None)
        if task:
            task.cancel()

    # ------------------------------------------------------------ settings

    def strategy_state(self, strategy_id: str) -> dict:
        st = self.config.setdefault("strategies", {}).setdefault(
            strategy_id, {"enabled": False, "config": dict(DEFAULT_TRADE_CONFIG)}
        )
        st.setdefault("config", dict(DEFAULT_TRADE_CONFIG))
        return st

    async def set_enabled(self, strategy_id: str, enabled: bool) -> None:
        st = self.strategy_state(strategy_id)
        st["enabled"] = enabled
        store.save_config(self.config)
        meta = getattr(get_strategy_class(strategy_id), "meta", None)
        label = meta.name if meta else strategy_id
        if enabled:
            self.log("info", f"استراتژی «{label}» فعال شد")
            if self.running:
                self._spawn(strategy_id)
        else:
            self.log("info", f"استراتژی «{label}» غیرفعال شد")
            self._despawn(strategy_id)
        await self._broadcast("strategies", self.describe_strategies())

    async def update_settings(self, api_key: Optional[str], secret_key: Optional[str],
                              mode: Optional[str], paper_balance: Optional[float]) -> None:
        if api_key is not None:
            self.config["api_key"] = api_key
        if secret_key is not None:
            self.config["secret_key"] = secret_key
        if mode in ("paper", "live"):
            self.config["mode"] = mode
        if paper_balance is not None:
            self.config["paper_balance"] = float(paper_balance)
            self.paper.balance = float(paper_balance)
        store.save_config(self.config)
        await self.client.close()
        self.client = BitunixClient(self.config["api_key"], self.config["secret_key"])
        self.log("info", f"تنظیمات ذخیره شد (حالت: {'واقعی' if self.config['mode'] == 'live' else 'دمو'})")
        await self._broadcast("settings", self.describe_settings())

    def update_risk(self, risk: dict) -> dict:
        current = self.config.setdefault("risk", dict(store.DEFAULT_RISK))
        for key in store.DEFAULT_RISK:
            if key in risk and risk[key] is not None:
                current[key] = float(risk[key]) if "pct" in key else int(risk[key])
        store.save_config(self.config)
        self.log("info", "تنظیمات مدیریت ریسک و سرمایه به‌روزرسانی شد")
        return current

    def add_custom_strategy(self, definition: dict) -> str:
        sid = "custom_" + uuid.uuid4().hex[:8]
        self.config.setdefault("custom_strategies", {})[sid] = definition
        _REGISTRY[sid] = make_custom_strategy(sid, definition)
        self.strategy_state(sid)
        store.save_config(self.config)
        self.log("info", f"استراتژی سفارشی «{definition.get('name', sid)}» اضافه شد")
        return sid

    def add_user_strategy(self, filename: str, code: str) -> list[str]:
        mapping = save_user_strategy_code(filename, code)
        self.user_files.update(mapping)
        for sid in mapping:
            self.strategy_state(sid)
        store.save_config(self.config)
        names = ", ".join(_REGISTRY[sid].meta.name for sid in mapping)
        self.log("info", f"استراتژی شما بارگذاری شد: {names}")
        return list(mapping)

    def remove_strategy(self, strategy_id: str) -> bool:
        """Remove a custom or user strategy."""
        removed = False
        if strategy_id in self.config.get("custom_strategies", {}):
            self.config["custom_strategies"].pop(strategy_id, None)
            removed = True
        if strategy_id in self.user_files:
            filename = self.user_files.pop(strategy_id)
            # only delete the file when no other strategy id still uses it
            if filename not in self.user_files.values():
                delete_user_strategy_file(filename)
            removed = True
        if not removed:
            return False
        self._despawn(strategy_id)
        self.config.get("strategies", {}).pop(strategy_id, None)
        _REGISTRY.pop(strategy_id, None)
        store.save_config(self.config)
        return True

    # ------------------------------------------------------------- describe

    def describe_strategies(self) -> list[dict]:
        out = []
        for sid, cls in all_strategies().items():
            if sid == "_custom_template":
                continue
            st = self.strategy_state(sid)
            cfg = {**DEFAULT_TRADE_CONFIG, **st.get("config", {})}
            cfg["symbols"] = _strategy_symbols(cfg)
            out.append({
                "id": sid,
                "name": cls.meta.name,
                "description": cls.meta.description,
                "source": getattr(cls.meta, "source", "custom"),
                "enabled": bool(st.get("enabled")),
                "config": cfg,
                "file": self.user_files.get(sid),
            })
        return out

    def describe_settings(self) -> dict:
        return {
            "mode": self.config.get("mode", "live"),
            "has_keys": bool(self.config.get("api_key") and self.config.get("secret_key")),
            "api_key_masked": (self.config.get("api_key", "")[:4] + "•••") if self.config.get("api_key") else "",
            "paper_balance": self.config.get("paper_balance", 10000.0),
            "margin_coin": self.config.get("margin_coin", "USDT"),
            "risk": self.config.get("risk", dict(store.DEFAULT_RISK)),
        }

    def _daily_realized_pnl(self) -> float:
        today = datetime.now(timezone.utc).date()
        total = 0.0
        for t in self.trades:
            ts = t.get("closed_at")
            if ts and datetime.fromtimestamp(ts / 1000, timezone.utc).date() == today:
                total += t.get("pnl", 0.0)
        return total

    def describe_state(self) -> dict:
        paper_positions = list(self.paper.positions.values())
        closed = [t for t in self.trades if "pnl" in t]
        wins = [t for t in closed if t["pnl"] > 0]
        return {
            "running": self.running,
            "mode": self.config.get("mode", "live"),
            "paper_balance": self.paper.balance,
            "paper_equity": self.paper.balance + sum(p["margin"] + p["pnl"] for p in paper_positions),
            "live_account": self.live_account,
            "positions": paper_positions if self.config.get("mode") != "live" else self.live_positions,
            "trades": self.trades[-50:][::-1],
            "signals": self.signals[-30:][::-1],
            "executions": self.executions[-40:][::-1],
            "logs": self.logs[-60:][::-1],
            "prices": self.last_prices,
            "risk": self.config.get("risk", {}),
            "daily_pnl": self._daily_realized_pnl(),
            "stats": {
                "total_trades": len(closed),
                "wins": len(wins),
                "win_rate": (len(wins) / len(closed) * 100) if closed else 0.0,
                "total_pnl": sum(t["pnl"] for t in closed),
            },
        }

    # ------------------------------------------------------------- trading

    async def _run_strategy(self, strategy_id: str) -> None:
        cls = get_strategy_class(strategy_id)
        while self.running and cls:
            st = self.strategy_state(strategy_id)
            cfg = {**DEFAULT_TRADE_CONFIG, **st.get("config", {})}
            for symbol in _strategy_symbols(cfg):
                try:
                    await self._tick(strategy_id, cls, cfg, symbol)
                except asyncio.CancelledError:
                    return
                except BitunixError as e:
                    self.log("error", f"[{cls.meta.name} · {symbol}] خطای صرافی: {e.message}")
                except Exception as e:  # keep the loop alive on transient errors
                    self.log("error", f"[{cls.meta.name} · {symbol}] خطا: {e}")
            await asyncio.sleep(POLL_SECONDS)

    async def _tick(self, strategy_id: str, cls, cfg: dict, symbol: str) -> None:
        interval = cfg["interval"]
        strategy = cls(cfg)
        candles = await self.client.klines(symbol, interval, max(strategy.min_candles(), 150))
        if len(candles) < strategy.min_candles():
            return
        price = candles[-1]["close"]
        self.last_prices[symbol] = price

        # paper broker SL/TP watching happens on every tick
        for closed in self.paper.mark(symbol, price):
            self._record_trade(closed)
            self.log("trade", f"پوزیشن {closed['side']} {symbol} بسته شد ({closed['close_reason']}) "
                              f"PnL: {closed['pnl']:+.2f}")
            await self._broadcast("state", self.describe_state())

        signal = strategy.analyze(candles)
        if not signal:
            return

        now = time.time()
        cd_key = f"{strategy_id}:{symbol}"
        if now - self._cooldowns.get(cd_key, 0) < cfg.get("cooldown_sec", 300):
            return
        self._cooldowns[cd_key] = now

        sig_record = {
            "ts": int(now * 1000), "strategy_id": strategy_id, "strategy": cls.meta.name,
            "symbol": symbol, "side": signal.side, "price": signal.price,
            "confidence": signal.confidence, "reason": signal.reason,
            "sl": signal.sl, "tp": signal.tp,
        }
        self.signals.append(sig_record)
        self.signals = self.signals[-MAX_SIGNALS:]
        self.log("signal", f"سیگنال {signal.side} از «{cls.meta.name}» روی {symbol} @ {signal.price:g}")
        await self._broadcast("signal", sig_record)

        await self._execute(strategy_id, cls.meta.name, symbol, signal, cfg)
        await self._broadcast("state", self.describe_state())

    def _position_qty(self, equity: float, signal: Signal, risk_pct: float) -> float:
        """Risk-based sizing: risk_pct of equity lost if SL is hit."""
        risk_amount = equity * risk_pct / 100.0
        sl_dist = abs(signal.price - signal.sl) if signal.sl else signal.price * 0.01
        if sl_dist <= 0:
            sl_dist = signal.price * 0.01
        return max(round(risk_amount / sl_dist, 6), 0.0)

    def _risk_gate(self, name: str) -> bool:
        """Global money-management rules; True when a new trade may open."""
        risk = self.config.get("risk", store.DEFAULT_RISK)
        open_count = (len(self.live_positions) if self.config.get("mode") == "live"
                      else len(self.paper.positions))
        if open_count >= int(risk.get("max_open_positions", 5)):
            self.log("info", f"[{name}] سقف کل پوزیشن‌های باز ({open_count}) پر است — ورود جدید مسدود شد")
            return False
        equity = (float(self.live_account.get("equity") or self.live_account.get("available") or 0)
                  if self.config.get("mode") == "live" else self.paper.balance)
        daily = self._daily_realized_pnl()
        max_daily = float(risk.get("max_daily_loss_pct", 5.0))
        if equity > 0 and daily < 0 and abs(daily) >= equity * max_daily / 100.0:
            self.log("error", f"[{name}] سقف ضرر روزانه ({max_daily}٪) پر شده — معاملات امروز متوقف است")
            return False
        return True

    async def _execute(self, strategy_id: str, name: str, symbol: str,
                       signal: Signal, cfg: dict) -> None:
        if not self._risk_gate(name):
            return
        open_here = ([p for p in self.paper.positions.values() if p["strategy_id"] == strategy_id]
                     if self.config.get("mode") != "live"
                     else [p for p in self.live_positions if p.get("symbol") == symbol])
        if len(open_here) >= int(cfg.get("max_positions", 1)):
            self.log("info", f"[{name}] سقف پوزیشن این استراتژی پر است — سیگنال نادیده گرفته شد")
            return

        risk = self.config.get("risk", store.DEFAULT_RISK)
        leverage = min(int(cfg.get("leverage", 5)), int(risk.get("max_leverage", 20)))
        risk_pct = float(cfg.get("risk_pct") or risk.get("default_risk_pct", 2.0))

        if self.config.get("mode") == "live":
            equity = float(self.live_account.get("available", 0) or 0)
            if equity <= 0:
                acc = await self.client.account(self.config.get("margin_coin", "USDT"))
                self.live_account = acc
                equity = float(acc.get("available", 0) or 0)
            qty = self._position_qty(equity * leverage, signal, risk_pct)
            if qty <= 0:
                self.log("error", f"[{name}] موجودی کافی برای باز کردن پوزیشن نیست")
                return
            try:
                await self.client.change_leverage(symbol, leverage,
                                                 self.config.get("margin_coin", "USDT"))
            except BitunixError:
                pass  # leverage may already be set
            side = "BUY" if signal.side == "LONG" else "SELL"
            await self.client.place_order(
                symbol=symbol, side=side, qty=qty, trade_side="OPEN",
                order_type="MARKET", tp_price=signal.tp, sl_price=signal.sl,
                client_id=f"dash{uuid.uuid4().hex[:10]}",
            )
            self.log("trade", f"سفارش واقعی {signal.side} {symbol} با حجم {qty:g} ثبت شد")
            self.executions.append({
                "ts": int(time.time() * 1000), "strategy_id": strategy_id,
                "symbol": symbol, "side": signal.side, "qty": qty,
                "price": signal.price, "mode": "live",
            })
            self.executions = self.executions[-100:]
        else:
            equity = self.paper.balance
            qty = self._position_qty(equity * leverage, signal, risk_pct)
            if qty <= 0 or self.paper.balance <= 0:
                self.log("error", f"[{name}] موجودی دمو کافی نیست")
                return
            margin_needed = signal.price * qty / max(leverage, 1)
            if margin_needed > self.paper.balance:
                qty = round(self.paper.balance * 0.95 * leverage / signal.price, 6)
            self.paper.open(symbol, signal.side, signal.price, qty, leverage,
                            signal.sl, signal.tp, strategy_id)
            self.log("trade", f"پوزیشن دمو {signal.side} {symbol} باز شد "
                              f"(حجم {qty:g}، اهرم {leverage}x)")
            self.executions.append({
                "ts": int(time.time() * 1000), "strategy_id": strategy_id,
                "symbol": symbol, "side": signal.side, "qty": qty,
                "price": signal.price, "mode": "paper",
            })
            self.executions = self.executions[-100:]

    def _record_trade(self, trade: dict) -> None:
        self.trades.append(trade)
        self.trades = self.trades[-500:]
        store.save_trades(self.trades)

    async def close_paper_position(self, pos_id: str) -> Optional[dict]:
        pos = self.paper.positions.get(pos_id)
        if not pos:
            return None
        price = self.last_prices.get(pos["symbol"], pos["mark"])
        closed = self.paper.close(pos_id, price, "MANUAL")
        if closed:
            self._record_trade(closed)
            self.log("trade", f"پوزیشن {closed['side']} {closed['symbol']} دستی بسته شد "
                              f"PnL: {closed['pnl']:+.2f}")
            await self._broadcast("state", self.describe_state())
        return closed

    async def refresh_live(self) -> None:
        if not self.client.has_keys:
            return
        try:
            self.live_account = await self.client.account(self.config.get("margin_coin", "USDT"))
            self.live_positions = await self.client.positions()
        except (BitunixError, Exception) as e:
            self.log("error", f"خطا در دریافت حساب: {e}")
