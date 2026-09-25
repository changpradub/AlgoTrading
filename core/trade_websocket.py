"""
Alpaca Trade Updates WebSocket Client
Subscribes to real-time trade update events (order fills, cancellations, partial fills)
via Alpaca's WebSocket streaming API.

Replaces REST polling for bracket fill detection with event-driven updates:
- Order filled → immediately detect TP/SL triggers
- Order cancelled → update tracking state
- Partial fills → track intermediate fill status

See UNIFIED_PLAN.md Section 4.7.
"""

import asyncio
import json
from enum import Enum
from typing import Callable, Dict, List, Optional, Awaitable
import structlog

from config.settings import settings
from utils.timezone import now_utc

logger = structlog.get_logger(__name__)

# Alpaca WebSocket endpoints
WS_URL_PAPER = "wss://paper-api.alpaca.markets/stream"
WS_URL_LIVE = "wss://api.alpaca.markets/stream"


class TradeEventType(str, Enum):
    """Alpaca trade update event types."""
    NEW = "new"
    PARTIAL_FILL = "partial_fill"
    FILL = "fill"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    REJECTED = "rejected"
    PENDING_NEW = "pending_new"
    CALCULATED = "calculated"
    SUSPENDED = "suspended"
    STOPPED = "stopped"


class TradeEvent:
    """Parsed Alpaca trade update event."""

    def __init__(self, raw: Dict):
        order_data = raw.get("order", raw)
        self.event_type = raw.get("event", "unknown")
        self.order_id = str(order_data.get("id", ""))
        self.client_order_id = str(order_data.get("client_order_id", ""))
        self.symbol = str(order_data.get("symbol", "")).upper()
        self.side = str(order_data.get("side", ""))
        self.order_type = str(order_data.get("type", ""))
        self.qty = float(order_data.get("qty", 0) or 0)
        self.filled_qty = float(order_data.get("filled_qty", 0) or 0)
        self.filled_avg_price = float(order_data.get("filled_avg_price", 0) or 0)
        self.status = str(order_data.get("status", ""))
        self.timestamp = raw.get("timestamp", str(now_utc()))

    @property
    def is_fill(self) -> bool:
        return self.event_type == TradeEventType.FILL

    @property
    def is_partial_fill(self) -> bool:
        return self.event_type == TradeEventType.PARTIAL_FILL

    @property
    def is_terminal(self) -> bool:
        """Event indicates order lifecycle is complete."""
        return self.event_type in (
            TradeEventType.FILL,
            TradeEventType.CANCELED,
            TradeEventType.EXPIRED,
            TradeEventType.REJECTED,
        )

    def __repr__(self) -> str:
        return (
            f"TradeEvent(event={self.event_type}, symbol={self.symbol}, "
            f"side={self.side}, qty={self.filled_qty}/{self.qty}, "
            f"price={self.filled_avg_price}, status={self.status})"
        )


# Type alias for event handler callbacks
TradeEventHandler = Callable[[TradeEvent], Awaitable[None]]


class AlpacaTradeWebSocket:
    """
    WebSocket client for Alpaca Trade Updates stream.
    Provides real-time order fill notifications instead of REST polling.

    Usage:
        ws = AlpacaTradeWebSocket()
        ws.on_fill(handle_fill_event)
        ws.on_cancel(handle_cancel_event)
        await ws.connect()  # runs forever, reconnects on disconnect
    """

    def __init__(self):
        self._ws = None
        self._running = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._handlers: Dict[str, List[TradeEventHandler]] = {
            "fill": [],
            "partial_fill": [],
            "canceled": [],
            "expired": [],
            "rejected": [],
            "new": [],
            "all": [],  # catch-all handlers
        }

    def on_fill(self, handler: TradeEventHandler) -> None:
        """Register handler for order fill events."""
        self._handlers["fill"].append(handler)

    def on_partial_fill(self, handler: TradeEventHandler) -> None:
        """Register handler for partial fill events."""
        self._handlers["partial_fill"].append(handler)

    def on_cancel(self, handler: TradeEventHandler) -> None:
        """Register handler for order cancellation events."""
        self._handlers["canceled"].append(handler)

    def on_any(self, handler: TradeEventHandler) -> None:
        """Register handler for ALL trade events."""
        self._handlers["all"].append(handler)

    async def connect(self) -> None:
        """
        Connect to Alpaca Trade Updates WebSocket.
        Automatically reconnects on disconnect with exponential backoff.
        """
        try:
            import websockets
        except ImportError:
            logger.error("websockets package not installed. Run: pip install websockets")
            return

        ws_url = WS_URL_PAPER if settings.is_paper_trading else WS_URL_LIVE
        self._running = True
        delay = self._reconnect_delay

        while self._running:
            try:
                logger.info("Connecting to Alpaca Trade Updates WebSocket...", url=ws_url)
                async with websockets.connect(ws_url) as ws:
                    self._ws = ws
                    delay = self._reconnect_delay  # reset on successful connect

                    # 1. Authenticate
                    auth_msg = {
                        "action": "authenticate",
                        "data": {
                            "key_id": settings.ALPACA_API_KEY,
                            "secret_key": settings.ALPACA_SECRET_KEY,
                        },
                    }
                    await ws.send(json.dumps(auth_msg))
                    auth_response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    auth_data = json.loads(auth_response)
                    logger.info("WebSocket auth response", data=auth_data)

                    # 2. Subscribe to trade updates
                    listen_msg = {
                        "action": "listen",
                        "data": {"streams": ["trade_updates"]},
                    }
                    await ws.send(json.dumps(listen_msg))
                    listen_response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    logger.info("WebSocket subscribed to trade_updates", response=json.loads(listen_response))

                    # 3. Message loop
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            stream = data.get("stream", "")

                            if stream == "trade_updates":
                                event_data = data.get("data", {})
                                event = TradeEvent(event_data)
                                logger.info("Trade event received", event=repr(event))
                                await self._dispatch_event(event)
                            elif stream == "authorization":
                                # Auth confirmation
                                pass
                            elif stream == "listening":
                                # Subscription confirmation
                                pass
                            else:
                                logger.debug("Unknown WebSocket message", stream=stream)

                        except json.JSONDecodeError:
                            logger.warning("Non-JSON WebSocket message received")
                        except Exception as e:
                            logger.error("Error processing WebSocket message", error=str(e))

            except asyncio.CancelledError:
                logger.info("WebSocket connection cancelled")
                self._running = False
                break
            except Exception as e:
                if not self._running:
                    break
                logger.warning(
                    "WebSocket disconnected, reconnecting...",
                    error=str(e),
                    reconnect_delay=delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._max_reconnect_delay)

        self._ws = None
        logger.info("WebSocket client stopped")

    async def disconnect(self) -> None:
        """Gracefully disconnect from WebSocket."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _dispatch_event(self, event: TradeEvent) -> None:
        """Dispatch event to registered handlers."""
        # Specific handlers
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(
                    "Trade event handler error",
                    event_type=event.event_type,
                    symbol=event.symbol,
                    error=str(e),
                )

        # All-events handlers
        for handler in self._handlers.get("all", []):
            try:
                await handler(event)
            except Exception as e:
                logger.error("All-events handler error", error=str(e))

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and self._running


# Global singleton
trade_websocket = AlpacaTradeWebSocket()
