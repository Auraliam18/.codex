"""JSON persistence for settings, strategy states, and trade history."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

_LOCK = threading.Lock()

DEFAULT_CONFIG: dict[str, Any] = {
    "api_key": "",
    "secret_key": "",
    "mode": "paper",  # paper | live
    "paper_balance": 10000.0,
    "margin_coin": "USDT",
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
    return cfg


def save_config(cfg: dict) -> None:
    save_json("config.json", cfg)


def load_trades() -> list[dict]:
    return load_json("trades.json", [])


def save_trades(trades: list[dict]) -> None:
    save_json("trades.json", trades[-500:])
