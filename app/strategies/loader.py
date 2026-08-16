"""Loader for the user's own Python strategy files.

Strategy files live in data/user_strategies/. Each file is a normal Python
module that subclasses BaseStrategy; every subclass with a `meta` is
registered automatically (no @register needed, though it also works).

NOTE: these files run with full Python access inside your own panel — only
put code here that you wrote or trust.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from . import BaseStrategy, _REGISTRY

USER_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "user_strategies"


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_").lower()
    return s or "strategy"


def _load_file(path: Path) -> dict[str, type[BaseStrategy]]:
    """Import one file and register the strategies it defines."""
    mod_name = f"user_strategy_{_slug(path.stem)}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)

    found: dict[str, type[BaseStrategy]] = {}
    for obj in vars(module).values():
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseStrategy)
            and obj is not BaseStrategy
            and getattr(obj, "meta", None) is not None
            and obj.meta.id != "_custom_template"
        ):
            obj.meta.builtin = False
            obj.meta.source = "user"
            _REGISTRY[obj.meta.id] = obj
            found[obj.meta.id] = obj
    if not found:
        raise ValueError(
            f"{path.name}: هیچ کلاس استراتژی (BaseStrategy با meta) در فایل پیدا نشد"
        )
    return found


def load_user_strategies() -> dict[str, str]:
    """Load every .py file in USER_DIR; returns {strategy_id: filename}."""
    USER_DIR.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    for path in sorted(USER_DIR.glob("*.py")):
        try:
            for sid in _load_file(path):
                mapping[sid] = path.name
        except Exception as e:
            print(f"[user-strategy] failed to load {path.name}: {e}")
    return mapping


def save_user_strategy_code(filename: str, code: str) -> dict[str, str]:
    """Save a strategy file, load it, and return {strategy_id: filename}.
    On failure the file is removed and the error re-raised."""
    USER_DIR.mkdir(parents=True, exist_ok=True)
    safe = _slug(Path(filename).stem) + ".py"
    path = USER_DIR / safe
    path.write_text(code, encoding="utf-8")
    try:
        found = _load_file(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {sid: safe for sid in found}


def delete_user_strategy_file(filename: str) -> None:
    path = USER_DIR / Path(filename).name
    path.unlink(missing_ok=True)
