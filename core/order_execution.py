"""
Order Execution Engine Module
Handles order placement, bracket order generation, status tracking, and slippage monitoring.
Rule: Every BUY order MUST be a Bracket Order with Take Profit and Stop Loss attached.
See UNIFIED_PLAN.md Section 4.7.
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
import structlog
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    TakeProfitRequest,
    StopLossRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus
from alpaca.trading.models import Order

from core.alpaca_client import alpaca_trading_client
from core.failsafe import safe_mode_manager
from notifications import dispatcher
from utils.timezone import now_utc, format_multi_tz_display

logger = structlog.get_logger(__name__)


@dataclass
class OrderExecutionReport:
    client_order_id: str
    alpaca_order_id: Optional[str]
    symbol: str
    status: str
    filled_qty: float
    filled_avg_price: float
    expected_price: float
    slippage_usd: float
    slippage_pct: float
    take_profit_price: float
    stop_loss_price: float
    submitted_at: datetime
    error_message: Optional[str] = None


class OrderExecutionEngine:
    """Executes trades strictly as Bracket Orders and monitors fills."""

    def __init__(self, default_time_in_force: TimeInForce = TimeInForce.GTC):
        self.default_time_in_force = default_time_in_force

    def build_bracket_order_request(
        self,
        symbol: str,
        qty: float,
        take_profit_price: float,
        stop_loss_price: float,
        limit_price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> MarketOrderRequest | LimitOrderRequest:
        """
        Build Alpaca Bracket Order request.
        Invariant: Every order MUST contain both take_profit and stop_loss.
        """
        cid = client_order_id or f"bot_{symbol.lower()}_{uuid.uuid4().hex[:10]}"

        tp_request = TakeProfitRequest(limit_price=round(take_profit_price, 2))
        sl_request = StopLossRequest(stop_price=round(stop_loss_price, 2))

        if limit_price is not None:
            return LimitOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=self.default_time_in_force,
                order_class=OrderClass.BRACKET,
                limit_price=round(limit_price, 2),
                take_profit=tp_request,
                stop_loss=sl_request,
                client_order_id=cid,
            )

        return MarketOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=self.default_time_in_force,
            order_class=OrderClass.BRACKET,
            take_profit=tp_request,
            stop_loss=sl_request,
            client_order_id=cid,
        )

    async def submit_bracket_buy(
        self,
        symbol: str,
        qty: float,
        expected_price: float,
        take_profit_price: float,
        stop_loss_price: float,
        limit_price: Optional[float] = None,
    ) -> OrderExecutionReport:
        """
        Submit a Bracket Buy order asynchronously and await confirmation.
        """
        submitted_at = now_utc()
        req = self.build_bracket_order_request(
            symbol=symbol,
            qty=qty,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            limit_price=limit_price,
        )

        logger.info(
            "Submitting Bracket BUY order",
            symbol=symbol,
            qty=qty,
            tp=take_profit_price,
            sl=stop_loss_price,
            client_order_id=req.client_order_id,
        )

        if not safe_mode_manager.can_trade:
            reason = f"Trading blocked: system is in {safe_mode_manager.state.value} state."
            logger.error("Order rejected by SafeModeManager", reason=reason)
            return OrderExecutionReport(
                client_order_id=req.client_order_id,
                alpaca_order_id=None,
                symbol=symbol.upper(),
                status="rejected",
                filled_qty=0.0,
                filled_avg_price=0.0,
                expected_price=expected_price,
                slippage_usd=0.0,
                slippage_pct=0.0,
                take_profit_price=take_profit_price,
                stop_loss_price=stop_loss_price,
                submitted_at=submitted_at,
                error_message=reason,
            )

        try:
            # 1. Dispatch order to Alpaca
            raw_client = alpaca_trading_client._ensure_client()
            order: Order = await asyncio.to_thread(raw_client.submit_order, req)

            # 2. Monitor status until accepted or filled
            alpaca_id = str(order.id)
            filled_order = await self.monitor_order_fill(alpaca_id, timeout_seconds=30)

            status_str = filled_order.status.value if hasattr(filled_order.status, "value") else str(filled_order.status)
            filled_qty = float(filled_order.filled_qty or 0.0)
            avg_price = float(filled_order.filled_avg_price or expected_price)

            # 3. Calculate Slippage
            slippage_usd = round(avg_price - expected_price, 4)
            slippage_pct = round((slippage_usd / expected_price) * 100.0, 3) if expected_price > 0 else 0.0

            report = OrderExecutionReport(
                client_order_id=req.client_order_id,
                alpaca_order_id=alpaca_id,
                symbol=symbol.upper(),
                status=status_str,
                filled_qty=filled_qty,
                filled_avg_price=avg_price,
                expected_price=expected_price,
                slippage_usd=slippage_usd,
                slippage_pct=slippage_pct,
                take_profit_price=take_profit_price,
                stop_loss_price=stop_loss_price,
                submitted_at=submitted_at,
            )

            safe_mode_manager.record_success()

            # 4. Notify via Telegram
            await dispatcher.notify_trade(
                symbol=symbol,
                action=f"BUY ({status_str.upper()})",
                details={
                    "qty": filled_qty,
                    "price": f"${avg_price:.2f} (Slip: {slippage_pct:+.2f}%)",
                    "tp": f"${take_profit_price:.2f}",
                    "sl": f"${stop_loss_price:.2f}",
                },
            )

            logger.info("Bracket order executed", report=report)
            return report

        except Exception as e:
            logger.error("Order submission failed", symbol=symbol, error=str(e))
            await safe_mode_manager.record_error("OrderSubmissionError", str(e))
            await dispatcher.notify_warning(f"Order failed for {symbol}: {str(e)}")
            return OrderExecutionReport(
                client_order_id=req.client_order_id,
                alpaca_order_id=None,
                symbol=symbol.upper(),
                status="rejected",
                filled_qty=0.0,
                filled_avg_price=0.0,
                expected_price=expected_price,
                slippage_usd=0.0,
                slippage_pct=0.0,
                take_profit_price=take_profit_price,
                stop_loss_price=stop_loss_price,
                submitted_at=submitted_at,
                error_message=str(e),
            )

    async def monitor_order_fill(self, alpaca_order_id: str, timeout_seconds: int = 30) -> Order:
        """
        Poll order status asynchronously until filled, canceled, or timed out.
        """
        start = asyncio.get_event_loop().time()
        raw_client = alpaca_trading_client._ensure_client()

        while (asyncio.get_event_loop().time() - start) < timeout_seconds:
            order: Order = await asyncio.to_thread(raw_client.get_order_by_id, alpaca_order_id)
            status = order.status.value if hasattr(order.status, "value") else str(order.status)

            if status in ("filled", "partially_filled", "canceled", "rejected", "expired"):
                return order

            await asyncio.sleep(1.5)

        # Return latest state on timeout
        return await asyncio.to_thread(raw_client.get_order_by_id, alpaca_order_id)


# Global Order Execution Engine singleton
order_engine = OrderExecutionEngine()
