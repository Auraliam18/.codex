"""JSON persistence for settings, strategy states, and trade history."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

_LOCK = threading.Lock()

DEFAULT_RISK: dict[str, Any] = {
    "default_risk_pct": 2.0,     # percent of equity risked per trade
    "max_daily_loss_pct": 5.0,   # stop opening trades after this daily loss
    "max_open_positions": 5,     # global cap across all strategies
    "max_leverage": 20,          # hard cap applied to every order
}

DEFAULT_CONFIG: dict[str, Any] = {
    "api_key": "",
    "secret_key": "",
    "mode": "live",  # live | paper
    "paper_balance": 10000.0,
    "margin_coin": "USDT",
    "risk": dict(DEFAULT_RISK),
    "strategies": {},  # id -> {"enabled": bool, "config": {...}}
    "custom_strategies": {},  # id -> rule definition
}


def _path(name: str) -> Path:
    return DATA_DIR / name


def load_json(name: str, default: Any) -> Any:
    p = _path(name)
    if not p.exists():
        return json.loads(json.dumps(default))
    with _LOCK:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(default))


def save_json(name: str, data: Any) -> None:
    p = _path(name)
    with _LOCK:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)


def load_config() -> dict:
    cfg = {**DEFAULT_CONFIG, **load_json("config.json", {})}
    cfg["risk"] = {**DEFAULT_RISK, **cfg.get("risk", {})}
    return cfg


def save_config(cfg: dict) -> None:
    save_json("config.json", cfg)


def load_trades() -> list[dict]:
    return load_json("trades.json", [])


def save_trades(trades: list[dict]) -> None:
    save_json("trades.json", trades[-500:])
