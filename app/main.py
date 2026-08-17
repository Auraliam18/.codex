"""FastAPI application: REST API + WebSocket + static dashboard."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .backtest import run_backtest
from .bitunix import BitunixError
from .engine import Engine
from .strategies import INDICATOR_MENU, get_strategy_class

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

engine = Engine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_live_refresher())
    yield
    task.cancel()
    await engine.stop()
    await engine.client.close()


async def _live_refresher():
    while True:
        if engine.config.get("mode") == "live" and engine.client.has_keys:
            await engine.refresh_live()
        await asyncio.sleep(15)


app = FastAPI(title="Liam Trader 9", lifespan=lifespan)


# --------------------------------------------------------------------- models

class SettingsIn(BaseModel):
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    mode: Optional[str] = None
    paper_balance: Optional[float] = None


class RiskIn(BaseModel):
    default_risk_pct: Optional[float] = None
    max_daily_loss_pct: Optional[float] = None
    max_open_positions: Optional[int] = None
    max_leverage: Optional[int] = None


class StrategyToggleIn(BaseModel):
    enabled: bool


class StrategyConfigIn(BaseModel):
    config: dict


class CustomStrategyIn(BaseModel):
    name: str
    description: Optional[str] = ""
    long: list[dict] = []
    short: list[dict] = []
    atr_sl_mult: float = 1.5
    rr_ratio: float = 2.0


class UserStrategyIn(BaseModel):
    filename: str
    code: str


class BacktestIn(BaseModel):
    strategy_id: str
    symbol: str = "BTCUSDT"
    interval: str = "15m"
    bars: int = 500
    initial_balance: float = 10000.0


# ----------------------------------------------------------------------- api

@app.get("/api/state")
async def get_state():
    return engine.describe_state()


@app.get("/api/settings")
async def get_settings():
    return engine.describe_settings()


@app.post("/api/settings")
async def post_settings(body: SettingsIn):
    await engine.update_settings(body.api_key, body.secret_key, body.mode, body.paper_balance)
    return engine.describe_settings()


@app.post("/api/settings/risk")
async def post_risk(body: RiskIn):
    return {"ok": True, "risk": engine.update_risk(body.model_dump())}


@app.post("/api/settings/test")
async def test_connection():
    """Verify API keys by fetching the futures account."""
    try:
        acc = await engine.client.account(engine.config.get("margin_coin", "USDT"))
        return {"ok": True, "account": acc}
    except BitunixError as e:
        return JSONResponse({"ok": False, "error": e.message}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.get("/api/indicators")
async def get_indicators():
    return INDICATOR_MENU


@app.get("/api/strategies")
async def get_strategies():
    return engine.describe_strategies()


@app.post("/api/strategies/{strategy_id}/toggle")
async def toggle_strategy(strategy_id: str, body: StrategyToggleIn):
    await engine.set_enabled(strategy_id, body.enabled)
    return {"ok": True}


@app.post("/api/strategies/{strategy_id}/config")
async def config_strategy(strategy_id: str, body: StrategyConfigIn):
    st = engine.strategy_state(strategy_id)
    st["config"] = {**st.get("config", {}), **body.config}
    from . import store
    store.save_config(engine.config)
    engine.log("info", f"تنظیمات استراتژی {strategy_id} به‌روزرسانی شد")
    return {"ok": True, "config": st["config"]}


@app.post("/api/strategies/custom")
async def add_custom(body: CustomStrategyIn):
    sid = engine.add_custom_strategy(body.model_dump())
    return {"ok": True, "id": sid}


@app.post("/api/strategies/upload")
async def upload_strategy(body: UserStrategyIn):
    try:
        ids = engine.add_user_strategy(body.filename, body.code)
        return {"ok": True, "ids": ids}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.delete("/api/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str):
    if engine.remove_strategy(strategy_id):
        return {"ok": True}
    return JSONResponse({"ok": False, "error": "not found"}, status_code=404)


@app.post("/api/backtest")
async def backtest(body: BacktestIn):
    cls = get_strategy_class(body.strategy_id)
    if not cls:
        return JSONResponse({"ok": False, "error": "استراتژی پیدا نشد"}, status_code=404)
    st = engine.strategy_state(body.strategy_id)
    cfg = st.get("config", {})
    bars = max(200, min(int(body.bars), 1000))
    try:
        candles = await engine.client.klines(body.symbol, body.interval, bars)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"دریافت کندل ناموفق: {e}"}, status_code=502)
    strategy = cls(cfg)
    if len(candles) <= strategy.min_candles():
        return JSONResponse(
            {"ok": False, "error": f"کندل کافی نیست ({len(candles)} از {strategy.min_candles()} موردنیاز)"},
            status_code=400,
        )
    result = run_backtest(
        strategy, candles,
        initial_balance=float(body.initial_balance),
        leverage=int(cfg.get("leverage", 5)),
        risk_pct=float(cfg.get("risk_pct", 2.0)),
    )
    return {"ok": True, "symbol": body.symbol, "interval": body.interval,
            "bars": len(candles), "result": result}


@app.post("/api/engine/start")
async def start_engine():
    await engine.start()
    return {"running": engine.running}


@app.post("/api/engine/stop")
async def stop_engine():
    await engine.stop()
    return {"running": False}


@app.post("/api/positions/{pos_id}/close")
async def close_position(pos_id: str):
    if engine.config.get("mode") == "live":
        try:
            await engine.client.flash_close_position(pos_id)
            await engine.refresh_live()
            return {"ok": True}
        except BitunixError as e:
            return JSONResponse({"ok": False, "error": e.message}, status_code=400)
    closed = await engine.close_paper_position(pos_id)
    if closed:
        return {"ok": True, "trade": closed}
    return JSONResponse({"ok": False, "error": "position not found"}, status_code=404)


@app.get("/api/klines")
async def get_klines(symbol: str = "BTCUSDT", interval: str = "15m", limit: int = 120):
    try:
        return await engine.client.klines(symbol, interval, limit)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ----------------------------------------------------------------- websocket

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    def listener(msg: dict):
        try:
            queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass

    engine.add_listener(listener)
    try:
        await ws.send_text(json.dumps(
            {"event": "state", "payload": engine.describe_state()}, ensure_ascii=False))
        while True:
            msg = await queue.get()
            await ws.send_text(json.dumps(msg, ensure_ascii=False, default=str))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        engine.remove_listener(listener)


# -------------------------------------------------------------------- static

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
