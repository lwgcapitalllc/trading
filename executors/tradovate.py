"""
executors/tradovate.py — Tradovate API Executor

Handles all communication with the Tradovate REST + WebSocket API.
Used by bot4_lucidflex.py and copier.py.

Tradovate supports:
  - REST API for account info, order placement, positions
  - WebSocket for real-time market data and order updates
  - Both demo (md.tradovate.com) and live (live.tradovate.com) environments

Install:
    pip install aiohttp websockets pandas numpy

Tradovate API docs: https://api.tradovate.com
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import pandas as pd
import numpy as np

log = logging.getLogger("TRADOVATE")

# ── Endpoints ─────────────────────────────────────────────────────────────────
DEMO_REST  = "https://demo.tradovateapi.com/v1"
LIVE_REST  = "https://live.tradovateapi.com/v1"
DEMO_MD    = "wss://md.tradovateapi.com/v1/websocket"
LIVE_MD    = "wss://live.tradovateapi.com/v1/websocket"


class TradovateExecutor:
    """
    Full Tradovate API executor.

    Usage:
        exec = TradovateExecutor(credentials, environment="demo")
        await exec.connect()
        price = await exec.get_price("MNQ")
        ticket = await exec.place_order("MNQ", "Buy", 1, sl=18000, tp=18100)
        await exec.close_position(ticket)
        await exec.disconnect()

    Credentials dict:
        {
            "username":    "your_username",
            "password":    "your_password",
            "account_id":  12345678,
            "environment": "demo"  or  "live"
        }
    """

    def __init__(self, credentials: dict, environment: str = "demo"):
        self.creds       = credentials
        self.env         = environment
        self.base_url    = DEMO_REST if environment == "demo" else LIVE_REST
        self.md_url      = DEMO_MD   if environment == "demo" else LIVE_MD
        self.token       = None
        self.token_expiry= 0
        self.account_id  = credentials.get("account_id")
        self.session     = None
        self._ws         = None
        self._prices     = {}   # symbol -> latest price
        self._connected  = False

    # ── Authentication ────────────────────────────────────────────────────────

    async def _auth(self):
        """Authenticate and get access token."""
        url  = f"{self.base_url}/auth/accesstokenrequest"
        body = {
            "name":       self.creds["username"],
            "password":   self.creds["password"],
            "appId":      "Sample App",
            "appVersion": "1.0",
            "cid":        0,
            "sec":        "",
        }
        async with self.session.post(url, json=body) as r:
            data = await r.json()
            if "accessToken" not in data:
                raise ConnectionError(
                    f"Tradovate auth failed: {data.get('errorText', data)}"
                )
            self.token        = data["accessToken"]
            # Token expires in 80 minutes — refresh every 70
            self.token_expiry = time.time() + 4200
            log.info(f"Tradovate authenticated | env={self.env} | "
                     f"account={self.account_id}")
            return self.token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type":  "application/json",
        }

    async def _ensure_token(self):
        if not self.token or time.time() > self.token_expiry - 60:
            await self._auth()

    async def _get(self, path: str) -> dict:
        await self._ensure_token()
        async with self.session.get(
            f"{self.base_url}{path}", headers=self._headers()
        ) as r:
            return await r.json()

    async def _post(self, path: str, body: dict) -> dict:
        await self._ensure_token()
        async with self.session.post(
            f"{self.base_url}{path}",
            json=body,
            headers=self._headers()
        ) as r:
            return await r.json()

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self):
        """Open session and authenticate."""
        self.session = aiohttp.ClientSession()
        await self._auth()
        self._connected = True
        log.info("Tradovate executor connected.")

    async def disconnect(self):
        """Close session cleanly."""
        if self.session:
            await self.session.close()
        self._connected = False
        log.info("Tradovate executor disconnected.")

    # ── Account Info ──────────────────────────────────────────────────────────

    async def get_account_balance(self) -> float:
        """Return current account cash balance."""
        data = await self._get(f"/cashBalance/getCashBalanceSnapshot"
                               f"?accountId={self.account_id}")
        return float(data.get("totalCashValue", 0))

    async def get_account_info(self) -> dict:
        """Return full account info including P&L."""
        data = await self._get(f"/account/item?id={self.account_id}")
        return data

    async def get_positions(self) -> list:
        """Return all open positions."""
        data = await self._get(f"/position/list")
        positions = data if isinstance(data, list) else []
        return [p for p in positions
                if p.get("accountId") == self.account_id
                and p.get("netPos", 0) != 0]

    # ── Market Data ───────────────────────────────────────────────────────────

    async def get_price(self, symbol: str) -> tuple[float, float]:
        """Return (bid, ask) for a symbol. Falls back to last if WS unavailable."""
        data = await self._get(f"/marketData/getQuote?symbol={symbol}")
        bid = float(data.get("bid", 0))
        ask = float(data.get("ask", 0) or data.get("bid", 0))
        return bid, ask

    async def get_candles(self, symbol: str, timeframe: str,
                          count: int = 100) -> pd.DataFrame:
        """
        Fetch OHLCV candles.
        timeframe: '1min', '5min', '15min', '60min', '1D'
        """
        url  = (f"/marketData/getBars?symbol={symbol}"
                f"&elementSize={count}&elementSizeUnit=UnderlyingUnits"
                f"&closestTimestamp={int(time.time()*1000)}"
                f"&asMuchAsElements={count}"
                f"&underlyingUnit={timeframe}")
        data = await self._get(url)
        bars = data if isinstance(data, list) else data.get("bars", [])
        if not bars:
            return pd.DataFrame()
        df = pd.DataFrame(bars)
        df.rename(columns={
            "timestamp": "time",
            "open":      "open",
            "high":      "high",
            "low":       "low",
            "close":     "close",
            "upVolume":  "volume",
        }, inplace=True)
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        return df[["time","open","high","low","close","volume"]].copy()

    # ── Order Management ──────────────────────────────────────────────────────

    async def place_order(self, symbol: str, side: str, qty: int,
                          sl: float = None, tp: float = None,
                          order_type: str = "Market") -> dict:
        """
        Place an order.
        side: "Buy" or "Sell"
        Returns order result dict with orderId.
        """
        body = {
            "accountSpec":   str(self.account_id),
            "accountId":     self.account_id,
            "action":        side,
            "symbol":        symbol,
            "orderQty":      qty,
            "orderType":     order_type,
            "isAutomated":   True,
        }
        if sl:
            body["stopLoss"] = {
                "stopType": "Limit" if order_type == "Limit" else "Stop",
                "price":    sl,
            }
        if tp:
            body["takeProfit"] = {"price": tp}

        result = await self._post("/order/placeorder", body)
        if result.get("failureReason"):
            log.error(f"Order failed: {result}")
            return None
        log.info(f"ORDER PLACED | {side} {qty}x {symbol} | "
                 f"SL={sl} TP={tp} | id={result.get('orderId')}")
        return result

    async def cancel_order(self, order_id: int) -> bool:
        result = await self._post("/order/cancelorder",
                                  {"orderId": order_id})
        return result.get("ordStatus") == "Canceled"

    async def close_position(self, symbol: str, position: dict) -> bool:
        """Close an open position at market."""
        net = position.get("netPos", 0)
        if net == 0:
            return True
        side = "Sell" if net > 0 else "Buy"
        qty  = abs(net)
        result = await self.place_order(symbol, side, qty)
        return result is not None

    async def close_all_positions(self, symbol: str = None,
                                   reason: str = "force-close"):
        """Close all open positions. Optionally filter by symbol."""
        positions = await self.get_positions()
        for pos in positions:
            if symbol and pos.get("contractId") != symbol:
                continue
            await self.close_position(pos.get("symbol", symbol), pos)
            log.info(f"Closed position | {pos} | reason={reason}")

    async def modify_sl(self, order_id: int, new_sl: float) -> bool:
        """Modify stop loss on an existing order."""
        result = await self._post("/order/modifyorder", {
            "orderId":  order_id,
            "stopLoss": {"price": new_sl},
        })
        return not result.get("failureReason")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def calculate_contracts(self, account_balance: float,
                             risk_pct: float, sl_points: float,
                             point_value: float,
                             max_contracts: int = 4,
                             min_contracts: int = 1) -> int:
        """
        Calculate number of contracts to trade.

        risk_pct:    e.g. 1.0 for 1% risk
        sl_points:   stop loss distance in index points
        point_value: dollar value per point (MNQ = $2, NQ = $20, MES = $5)
        """
        if sl_points <= 0 or point_value <= 0:
            return min_contracts
        risk_dollars  = account_balance * (risk_pct / 100)
        sl_dollars    = sl_points * point_value
        contracts     = int(risk_dollars / sl_dollars)
        contracts     = max(min_contracts, min(contracts, max_contracts))
        log.info(f"Sizing: ${account_balance:,.0f} | risk={risk_pct}% "
                 f"(${risk_dollars:.0f}) | SL={sl_points}pts "
                 f"(${sl_dollars:.0f}) | contracts={contracts}")
        return contracts

    def now_et(self) -> datetime:
        """Current time in US Eastern."""
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))

    def is_session_open(self, open_et: str = "09:30",
                         close_et: str = "16:00") -> bool:
        """Check if market session is open."""
        now   = self.now_et()
        open_h, open_m   = map(int, open_et.split(":"))
        close_h, close_m = map(int, close_et.split(":"))
        open_mins  = open_h * 60 + open_m
        close_mins = close_h * 60 + close_m
        cur_mins   = now.hour * 60 + now.minute
        return open_mins <= cur_mins < close_mins

    def should_force_close(self, close_time_et: str = "16:30") -> bool:
        """
        Returns True when it's time to force-close all positions.
        Default 16:30 ET — 15 min before Lucid's 16:45 hard close.
        """
        now  = self.now_et()
        h, m = map(int, close_time_et.split(":"))
        return now.hour > h or (now.hour == h and now.minute >= m)
