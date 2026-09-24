"""
Master Entry Point for Personal Algo-Trading Bot
Executes the main asyncio event loop coordinating:
1. Startup Recovery & State Reconciliation
2. Market Hours Scheduler & Pre-Market Gap Scanner
3. Indicator Warmup (>= 100 bars) & Technical Analysis
4. Swing Trading Strategy & AI Gatekeeper (Google Gemini 3.8 Flash)
5. Risk Engine & PDT Rule Enforcement & Position Sizing
6. Bracket Order Execution (Entry + Attached TP + SL) & Monitoring
7. Health Monitoring & Telegram Heartbeats

See UNIFIED_PLAN.md Section 3, Section 4, & Section 7.
"""

import argparse
import asyncio
from datetime import datetime, date
import os
import signal
import sys
from typing import Dict, List, Optional, Set
import structlog
from alpaca.data.timeframe import TimeFrame

# Windows UTF-8 encoding support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure root directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.constants import WARMUP_BARS_MIN
from config.settings import settings
from core.ai_sentiment import ai_gatekeeper
from core.alpaca_client import alpaca_trading_client
from core.failsafe import safe_mode_manager
from core.market_data import market_data_client
from core.order_execution import order_engine
from core.position_sizing import position_calculator
from core.pre_market_scan import pre_market_scanner
from core.risk_engine import risk_engine
from core.scheduler import market_scheduler, MarketPhase
from core.startup_recovery import startup_recovery_engine
from core.state_manager import state_manager
from core.strategy import swing_strategy, SignalType, TradingSignal
from db.connection import db_manager
from monitoring.health_check import health_monitor
from notifications import dispatcher
from utils.timezone import now_utc, format_multi_tz_display

logger = structlog.get_logger("bot")


class TradingBot:
    """Master Asynchronous Trading Bot Coordinator."""

    def __init__(
        self,
        dry_run: bool = False,
        single_cycle: bool = False,
        heartbeat_interval_sec: int = 3600,
        scan_interval_sec: int = 60,
    ):
        self.dry_run = dry_run
        self.single_cycle = single_cycle
        self.heartbeat_interval_sec = heartbeat_interval_sec
        self.scan_interval_sec = scan_interval_sec

        self._stop_event = asyncio.Event()
        self._last_pre_market_date: Optional[date] = None
        self._last_heartbeat_time: float = 0.0

    def trigger_shutdown(self) -> None:
        """Signal bot to terminate gracefully."""
        logger.info("Shutdown signal received. Initiating graceful shutdown...")
        self._stop_event.set()

    async def initialize(self) -> bool:
        """Initialize database, run startup recovery and verify prerequisites."""
        logger.info(
            "Initializing Trading Bot...",
            trading_mode=settings.TRADING_MODE,
            symbols=settings.target_symbol_list,
            dry_run=self.dry_run,
        )

        # 1. Connect to PostgreSQL
        try:
            await db_manager.connect()
            logger.info("Database connection established.")
        except Exception as e:
            logger.error("Database connection failed", error=str(e))
            # Continue if DB optional in certain test setups, but warn
            if not self.dry_run:
                logger.warning("Proceeding with caution; DB operations may be degraded.")

        # 2. Run Startup Recovery Engine
        try:
            recovery_report = await startup_recovery_engine.run_recovery()
            if not recovery_report.system_ready and not self.dry_run:
                logger.error("Startup recovery indicated system not ready for trading.")
                return False
            logger.info(
                "Startup recovery completed successfully",
                equity=recovery_report.equity,
                buying_power=recovery_report.buying_power,
                pdt_count=recovery_report.pdt_daytrade_count,
            )
        except Exception as e:
            logger.critical("Startup recovery failed", error=str(e))
            await safe_mode_manager.record_error("StartupRecoveryError", str(e))
            if not self.dry_run:
                return False

        # 3. Dispatch Bot Started notification
        mode_label = "DRY-RUN / SIMULATION" if self.dry_run else settings.TRADING_MODE.upper()
        start_msg = (
            f"🚀 <b>PERSONAL ALGO-TRADING BOT STARTED</b>\n"
            f"<code>{format_multi_tz_display(now_utc())}</code>\n"
            f"• Mode: <b>{mode_label}</b>\n"
            f"• Target Watchlist: <b>{', '.join(settings.target_symbol_list)}</b>\n"
            f"• Tranche Budget: <b>${settings.TRADE_BUDGET_PER_TRANCHE_USD:.2f}</b>\n"
            f"• Max Daily Loss: <b>${settings.MAX_DAILY_LOSS_USD:.2f}</b>\n"
            f"• Status: <b>Online & Monitoring Market Clock</b>"
        )
        try:
            await dispatcher.notify_info(start_msg)
        except Exception as e:
            logger.warning("Failed to send bot startup notification", error=str(e))

        return True

    async def run(self) -> None:
        """Main event loop running continuously until shutdown."""
        initialized = await self.initialize()
        if not initialized:
            logger.critical("Bot initialization aborted.")
            return

        logger.info("Bot is active and running main trading loop.")

        try:
            while not self._stop_event.is_set():
                now = asyncio.get_event_loop().time()

                # Periodic Heartbeat
                if now - self._last_heartbeat_time >= self.heartbeat_interval_sec:
                    try:
                        await health_monitor.send_heartbeat()
                        self._last_heartbeat_time = now
                    except Exception as e:
                        logger.warning("Error dispatching periodic heartbeat", error=str(e))

                # Check Market Status
                market_status = await market_scheduler.get_market_status(force_refresh=True)

                if market_status.phase == MarketPhase.REGULAR_HOURS:
                    # Regular Trading Hours: run active trading pipeline
                    await self._run_regular_hours_pipeline()

                elif market_status.phase == MarketPhase.PRE_MARKET:
                    # Pre-market Window: run pre-market gap scanner once per trading day
                    today = market_status.timestamp_utc.date()
                    if self._last_pre_market_date != today:
                        logger.info("Pre-market window detected. Running Pre-Market Gap Scan...")
                        try:
                            await pre_market_scanner.run_scan()
                            self._last_pre_market_date = today
                        except Exception as e:
                            logger.error("Pre-market scan encountered error", error=str(e))
                            await safe_mode_manager.record_error("PreMarketScanError", str(e))

                    logger.info(
                        "Market in Pre-Market phase. Waiting for regular open.",
                        next_open=format_multi_tz_display(market_status.next_open_utc),
                        seconds_left=round(market_status.time_to_open_seconds, 1),
                    )

                else:
                    # Market Closed or After-Hours: Idle state
                    hours_to_open = round(market_status.time_to_open_seconds / 3600.0, 2)
                    logger.info(
                        "Market is CLOSED. Bot idle.",
                        phase=market_status.phase.value,
                        hours_to_open=hours_to_open,
                        next_open=format_multi_tz_display(market_status.next_open_utc),
                    )

                if self.single_cycle:
                    logger.info("Single cycle mode completed. Exiting event loop.")
                    break

                # Sleep before next iteration or until stop event
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.scan_interval_sec,
                    )
                except asyncio.TimeoutError:
                    pass

        except asyncio.CancelledError:
            logger.info("Main bot task cancelled.")
        except Exception as e:
            logger.critical("Unhandled exception in bot main loop", error=str(e), exc_info=True)
            await safe_mode_manager.record_error("BotMainLoopCrash", str(e))
        finally:
            await self.shutdown()

    async def _run_regular_hours_pipeline(self) -> None:
        """Execute one complete trading evaluation cycle across watchlist."""
        logger.info("Commencing regular hours pipeline evaluation...")

        # 1. State Reconciliation
        try:
            recon = await state_manager.reconcile_state()
            equity = recon.account_equity
            buying_power = recon.buying_power
            pdt_count = recon.pdt_daytrade_count
        except Exception as e:
            logger.error("State reconciliation failed during pipeline cycle", error=str(e))
            await safe_mode_manager.record_error("StateReconcileError", str(e))
            return

        # 2. Check Safe Mode Status
        if not safe_mode_manager.can_trade:
            logger.warning(
                "Trading suspended by SafeModeManager",
                state=safe_mode_manager.state.value,
            )
            return

        # 3. Retrieve currently open positions and open orders from Alpaca
        open_positions: List[str] = []
        open_order_symbols: List[str] = []
        try:
            positions = await alpaca_trading_client.get_all_positions()
            open_positions = [p.symbol.upper() for p in positions]

            orders = await alpaca_trading_client.get_open_orders()
            open_order_symbols = [o.symbol.upper() for o in orders]
        except Exception as e:
            logger.error("Failed to query open positions/orders from Alpaca", error=str(e))
            await safe_mode_manager.record_error("AlpacaQueryError", str(e))
            return

        # Calculate current daily loss from today's trades if DB available
        current_daily_loss = 0.0
        if db_manager.is_connected:
            try:
                row = await db_manager.fetchrow(
                    """
                    SELECT COALESCE(SUM(realized_pl), 0.0) as today_pl
                    FROM trades_log
                    WHERE exit_time >= CURRENT_DATE AND exit_time IS NOT NULL
                    """
                )
                if row and row["today_pl"] < 0:
                    current_daily_loss = abs(float(row["today_pl"]))
            except Exception as e:
                logger.warning("Could not calculate current daily loss from DB", error=str(e))

        # 4. Iterate over Watchlist Symbols
        for symbol in settings.target_symbol_list:
            symbol = symbol.upper()
            try:
                await self._evaluate_symbol(
                    symbol=symbol,
                    equity=equity,
                    buying_power=buying_power,
                    current_daily_loss=current_daily_loss,
                    open_positions=open_positions,
                    open_order_symbols=open_order_symbols,
                    pdt_count=pdt_count,
                )
            except Exception as e:
                logger.error("Error evaluating symbol", symbol=symbol, error=str(e), exc_info=True)
                await safe_mode_manager.record_error(f"SymbolEvalError_{symbol}", str(e))

    async def _evaluate_symbol(
        self,
        symbol: str,
        equity: float,
        buying_power: float,
        current_daily_loss: float,
        open_positions: List[str],
        open_order_symbols: List[str],
        pdt_count: int,
    ) -> None:
        """Full pipeline evaluation for an individual symbol."""
        # Avoid duplicate checks early
        if symbol in open_positions:
            logger.debug(f"{symbol} already in open positions. Skipping.", symbol=symbol)
            return

        if symbol in open_order_symbols:
            logger.debug(f"{symbol} has an existing open order. Skipping duplicate.", symbol=symbol)
            return

        # 1. Indicator Warmup & Data Fetching (>= 100 bars requirement)
        logger.debug("Fetching market data for evaluation", symbol=symbol)
        df_1h = await market_data_client.get_historical_bars(
            symbol=symbol,
            timeframe=TimeFrame.Hour,
            limit=WARMUP_BARS_MIN + 20,  # e.g. 120 bars
        )

        if len(df_1h) < WARMUP_BARS_MIN:
            logger.warning(
                f"Indicator warmup incomplete for {symbol} ({len(df_1h)}/{WARMUP_BARS_MIN} bars). Skipping signal generation.",
                symbol=symbol,
                bars=len(df_1h),
            )
            return

        # Fetch Daily data for higher-timeframe trend confirmation
        df_1d = await market_data_client.get_historical_bars(
            symbol=symbol,
            timeframe=TimeFrame.Day,
            limit=60,
        )

        # 2. Strategy Engine Evaluation
        signal: TradingSignal = swing_strategy.evaluate(
            symbol=symbol,
            df_ltf=df_1h,
            df_htf=df_1d if len(df_1d) >= 30 else None,
        )

        if signal.signal_type != SignalType.BUY:
            logger.debug(f"Strategy returned {signal.signal_type.value} for {symbol}", reason=signal.reason)
            return

        logger.info(
            "BUY Signal generated by Strategy Engine",
            symbol=symbol,
            entry=signal.entry_price,
            tp=signal.take_profit,
            sl=signal.stop_loss,
            rr=signal.risk_reward_ratio,
            reason=signal.reason,
        )

        # 3. AI Sentiment Gatekeeper (OpenRouter Google Gemini 3.8 Flash)
        ai_decision = await ai_gatekeeper.evaluate_signal_gatekeeper(signal)
        if not ai_decision.approved:
            logger.warning(
                "BUY Signal VETOED by AI Gatekeeper",
                symbol=symbol,
                reason=ai_decision.reason,
            )
            return

        logger.info("AI Gatekeeper APPROVED BUY signal", symbol=symbol)

        # 4. Risk Engine Validation (PDT Rule + Daily Loss + Gap Risk)
        risk_res = risk_engine.validate_signal(
            signal=signal,
            equity=equity,
            current_daily_loss=current_daily_loss,
            open_positions=open_positions,
            open_order_symbols=open_order_symbols,
            pdt_count_5_days=pdt_count,
        )

        if not risk_res.approved:
            logger.warning(
                "Signal rejected by Risk Engine",
                symbol=symbol,
                reason=risk_res.reason,
            )
            return

        # 5. Position Sizing Calculation
        size_res = position_calculator.calculate(
            equity=equity,
            buying_power=buying_power,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            risk_factor=risk_res.risk_factor,
        )

        if not size_res.is_valid or size_res.shares <= 0:
            logger.warning(
                "Position sizing rejected order",
                symbol=symbol,
                reason=size_res.reason,
            )
            return

        logger.info(
            "Executing Trade via Order Engine",
            symbol=symbol,
            shares=size_res.shares,
            notional=size_res.notional_usd,
            risk=size_res.risk_usd,
            entry=signal.entry_price,
            tp=signal.take_profit,
            sl=signal.stop_loss,
        )

        # 6. Order Placement (Bracket Order)
        if self.dry_run:
            logger.info(
                "[DRY-RUN] Simulating Bracket BUY order placement without sending to broker",
                symbol=symbol,
                qty=size_res.shares,
                entry=signal.entry_price,
                tp=signal.take_profit,
                sl=signal.stop_loss,
            )
            return

        order_report = await order_engine.submit_bracket_buy(
            symbol=symbol,
            qty=size_res.shares,
            expected_price=signal.entry_price,
            take_profit_price=signal.take_profit,
            stop_loss_price=signal.stop_loss,
        )

        if order_report.alpaca_order_id:
            logger.info(
                "Bracket order submitted. Monitoring fill asynchronously...",
                order_id=order_report.alpaca_order_id,
                symbol=symbol,
            )
            # Async fill monitoring
            filled_order = await order_engine.monitor_order_fill(
                alpaca_order_id=order_report.alpaca_order_id,
                timeout_seconds=30,
            )
            logger.info(
                "Order monitoring concluded",
                symbol=symbol,
                status=getattr(filled_order, "status", "unknown"),
            )

            # Reconcile state after order completion
            await state_manager.reconcile_state()

    async def shutdown(self) -> None:
        """Clean up connections and finalize logs."""
        logger.info("Shutting down Trading Bot gracefully...")
        try:
            stop_msg = (
                f"🛑 <b>TRADING BOT STOPPED</b>\n"
                f"<code>{format_multi_tz_display(now_utc())}</code>\n"
                f"Bot process terminated safely."
            )
            await dispatcher.notify_info(stop_msg)
        except Exception as e:
            logger.warning("Could not dispatch stop notification", error=str(e))

        # Disconnect Database Pool
        try:
            await db_manager.disconnect()
            logger.info("Database pool disconnected.")
        except Exception as e:
            logger.warning("Error disconnecting DB pool", error=str(e))

        logger.info("Trading Bot shutdown completed.")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Personal Algo-Trading Bot Daemon")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without placing real orders with Alpaca",
    )
    parser.add_argument(
        "--single-cycle",
        action="store_true",
        help="Execute a single pipeline evaluation cycle and exit immediately",
    )
    parser.add_argument(
        "--pre-market-only",
        action="store_true",
        help="Run pre-market scan diagnostics and exit immediately",
    )
    parser.add_argument(
        "--health-only",
        action="store_true",
        help="Run system health diagnostics, send Telegram heartbeat, and exit immediately",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_arguments()

    if args.health_only:
        print("Running Health Diagnostics & Heartbeat...")
        await health_monitor.send_heartbeat()
        print("Heartbeat sent.")
        return

    if args.pre_market_only:
        print("Running Pre-Market Gap Scan...")
        summary = await pre_market_scanner.run_scan()
        print(f"Pre-market scan complete. Scanned {len(summary.scanned_symbols)} symbols.")
        return

    bot = TradingBot(dry_run=args.dry_run, single_cycle=args.single_cycle)

    # Attach signal handlers for graceful shutdown on POSIX systems
    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, bot.trigger_shutdown)
    else:
        # On Windows, Ctrl+C handled via KeyboardInterrupt
        pass

    try:
        await bot.run()
    except KeyboardInterrupt:
        bot.trigger_shutdown()
        await bot.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot process terminated by user (Ctrl+C).")
