"""Bitunix Futures REST client.

Implements the official Bitunix OpenAPI signing scheme (double SHA-256):

    digest = sha256(nonce + timestamp + api_key + query_params + body)
    sign   = sha256(digest + secret_key)

Headers sent on private endpoints: api-key, sign, nonce, timestamp, language.
`query_params` is the request's query string flattened as key+value pairs
sorted by key ascending with no separators; `body` is the raw JSON string.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

import httpx

BASE_URL = "https://fapi.bitunix.com"


class BitunixError(Exception):
    def __init__(self, code: Any, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Bitunix error {code}: {message}")


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class BitunixClient:
    def __init__(self, api_key: str = "", secret_key: str = "", base_url: str = BASE_URL):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=15.0)

    async def close(self) -> None:
        await self._http.aclose()

    @property
    def has_keys(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _auth_headers(self, params: Optional[dict], body_str: str) -> dict:
        import time as _time

        nonce = uuid.uuid4().hex
        timestamp = str(int(_time.time() * 1000))
        query = ""
        if params:
            query = "".join(f"{k}{params[k]}" for k in sorted(params))
        digest = _sha256_hex(nonce + timestamp + self.api_key + query + body_str)
        sign = _sha256_hex(digest + self.secret_key)
        return {
            "api-key": self.api_key,
            "sign": sign,
            "nonce": nonce,
            "timestamp": timestamp,
            "language": "en-US",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        auth: bool = False,
    ) -> Any:
        url = self.base_url + path
        params = {k: v for k, v in (params or {}).items() if v is not None}
        body_str = json.dumps(body, separators=(",", ":")) if body is not None else ""
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self.has_keys:
                raise BitunixError("NO_KEYS", "API key/secret not configured")
            headers = self._auth_headers(params, body_str)
        resp = await self._http.request(
            method,
            url,
            params=params or None,
            content=body_str if body is not None else None,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        # Bitunix wraps responses as {"code": 0, "msg": "Success", "data": ...}
        if isinstance(data, dict) and "code" in data:
            if str(data.get("code")) not in ("0", "00000"):
                raise BitunixError(data.get("code"), data.get("msg") or data.get("message", ""))
            return data.get("data")
        return data

    # ------------------------------------------------------------------ public

    async def klines(self, symbol: str, interval: str = "15m", limit: int = 200) -> list[dict]:
        data = await self._request(
            "GET",
            "/api/v1/futures/market/kline",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        candles = []
        for row in data or []:
            if isinstance(row, dict):
                candles.append(
                    {
                        "time": int(row.get("time") or row.get("ts") or 0),
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": float(row.get("baseVol") or row.get("volume") or 0),
                    }
                )
            elif isinstance(row, (list, tuple)) and len(row) >= 5:
                candles.append(
                    {
                        "time": int(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "volume": float(row[5]) if len(row) > 5 else 0.0,
                    }
                )
        candles.sort(key=lambda c: c["time"])
        return candles

    async def tickers(self, symbols: Optional[list[str]] = None) -> list[dict]:
        params = {"symbols": ",".join(symbols)} if symbols else None
        data = await self._request("GET", "/api/v1/futures/market/tickers", params=params)
        return data or []

    async def last_price(self, symbol: str) -> Optional[float]:
        for t in await self.tickers([symbol]):
            if t.get("symbol") == symbol:
                price = t.get("lastPrice") or t.get("last") or t.get("close")
                return float(price) if price is not None else None
        return None

    # ----------------------------------------------------------------- private

    async def account(self, margin_coin: str = "USDT") -> dict:
        data = await self._request(
            "GET", "/api/v1/futures/account", params={"marginCoin": margin_coin}, auth=True
        )
        if isinstance(data, list):
            return data[0] if data else {}
        return data or {}

    async def positions(self, symbol: Optional[str] = None) -> list[dict]:
        data = await self._request(
            "GET",
            "/api/v1/futures/position/get_pending_positions",
            params={"symbol": symbol} if symbol else None,
            auth=True,
        )
        return data or []

    async def change_leverage(self, symbol: str, leverage: int, margin_coin: str = "USDT") -> Any:
        return await self._request(
            "POST",
            "/api/v1/futures/account/change_leverage",
            body={"symbol": symbol, "marginCoin": margin_coin, "leverage": leverage},
            auth=True,
        )

    async def place_order(
        self,
        symbol: str,
        side: str,  # BUY | SELL
        qty: float,
        trade_side: str = "OPEN",  # OPEN | CLOSE
        order_type: str = "MARKET",
        price: Optional[float] = None,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        client_id: Optional[str] = None,
    ) -> Any:
        body: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
            "tradeSide": trade_side,
        }
        if price is not None:
            body["price"] = str(price)
        if tp_price is not None:
            body["tpPrice"] = str(tp_price)
            body["tpStopType"] = "MARK_PRICE"
            body["tpOrderType"] = "MARKET"
        if sl_price is not None:
            body["slPrice"] = str(sl_price)
            body["slStopType"] = "MARK_PRICE"
            body["slOrderType"] = "MARKET"
        if client_id:
            body["clientId"] = client_id
        return await self._request("POST", "/api/v1/futures/trade/place_order", body=body, auth=True)

    async def flash_close_position(self, position_id: str) -> Any:
        return await self._request(
            "POST",
            "/api/v1/futures/trade/flash_close_position",
            body={"positionId": position_id},
            auth=True,
        )
