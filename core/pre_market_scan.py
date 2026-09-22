"""
Pre-Market Gap Scanner Module
Executes prior to Regular Market Hours (04:00-09:30 ET) to detect breaking news,
assess overnight gap risk, and dispatch critical Telegram alerts.
See UNIFIED_PLAN.md Section 4.4 & Section 4.5.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog

from config.settings import settings
from core.ai_sentiment import ai_gatekeeper, AISentimentReport, SentimentType, GatekeeperAction
from core.alpaca_client import alpaca_trading_client
from core.news_fetcher import news_fetcher
from notifications.notifier import dispatcher
from utils.timezone import now_utc, format_multi_tz_display

logger = structlog.get_logger(__name__)


@dataclass
class PreMarketScanSummary:
    timestamp_utc: datetime
    scanned_symbols: List[str]
    gap_warnings: List[Dict[str, Any]] = field(default_factory=list)
    sentiment_reports: Dict[str, AISentimentReport] = field(default_factory=dict)

    @property
    def has_high_risk_events(self) -> bool:
        return len(self.gap_warnings) > 0


class PreMarketScanner:
    """Scans watchlist and active positions before market open."""

    async def run_scan(self, custom_symbols: Optional[List[str]] = None) -> PreMarketScanSummary:
        """
        Execute comprehensive pre-market news scan across all target symbols and held positions.
        """
        logger.info("Initiating Pre-Market News & Gap Risk Scan...")
        timestamp = now_utc()

        # 1. Determine list of symbols to scan
        symbols_to_scan = set(custom_symbols or settings.target_symbol_list)

        # Include currently open positions from Alpaca if possible
        try:
            positions = await alpaca_trading_client.get_all_positions()
            for p in positions:
                symbols_to_scan.add(p.symbol.upper())
        except Exception as e:
            logger.warning("Could not query active positions for pre-market scan", error=str(e))

        symbol_list = sorted(list(symbols_to_scan))
        logger.info("Scanning symbols for pre-market gap risk", symbols=symbol_list)

        gap_warnings: List[Dict[str, Any]] = []
        sentiment_reports: Dict[str, AISentimentReport] = {}

        # 2. Concurrently fetch news and analyze via AI Gatekeeper
        for sym in symbol_list:
            articles = await news_fetcher.fetch_news_for_symbol(sym, limit=3)
            report = await ai_gatekeeper.analyze_news(sym, articles)
            sentiment_reports[sym] = report

            # Check if this qualifies as a Gap Risk Warning
            is_warning = (
                report.risk_event
                or report.action_recommendation == GatekeeperAction.BLOCK
                or (report.sentiment == SentimentType.NEGATIVE and report.impact in ("MEDIUM", "HIGH"))
            )

            if is_warning:
                warning_info = {
                    "symbol": sym,
                    "sentiment": report.sentiment.value,
                    "event_type": report.event_type,
                    "impact": report.impact,
                    "reasoning": report.reasoning,
                }
                gap_warnings.append(warning_info)

                logger.warning(
                    "PRE-MARKET GAP RISK DETECTED",
                    symbol=sym,
                    event_type=report.event_type,
                    impact=report.impact,
                )

        summary = PreMarketScanSummary(
            timestamp_utc=timestamp,
            scanned_symbols=symbol_list,
            gap_warnings=gap_warnings,
            sentiment_reports=sentiment_reports,
        )

        # 3. Dispatch Notification via Telegram
        await self._dispatch_scan_notification(summary)
        return summary

    async def _dispatch_scan_notification(self, summary: PreMarketScanSummary) -> None:
        """Format and send Telegram notification summarizing pre-market scan."""
        time_str = format_multi_tz_display(summary.timestamp_utc)

        if summary.has_high_risk_events:
            lines = [
                "⚠️ <b>PRE-MARKET GAP RISK ALERT</b>",
                f"<code>{time_str}</code>",
                f"Scanned {len(summary.scanned_symbols)} stocks before market open.\n",
                "<b>Potential Adverse Gap Events Detected:</b>",
            ]
            for w in summary.gap_warnings:
                lines.append(
                    f"• <b>{w['symbol']}</b>: [{w['impact']}] {w['event_type']}\n"
                    f"  <i>{w['reasoning']}</i>"
                )
            lines.append("\n🛡️ <i>AI Gatekeeper will veto new BUY signals for affected symbols today.</i>")
            msg = "\n".join(lines)
            await dispatcher.notify_warning(msg)

        else:
            lines = [
                "📗 <b>PRE-MARKET SCAN COMPLETED</b>",
                f"<code>{time_str}</code>",
                f"Scanned: {', '.join(summary.scanned_symbols)}",
                "Status: <b>All Clear. No High-Impact Risk Events Detected.</b>",
            ]
            msg = "\n".join(lines)
            await dispatcher.notify_info(msg)


# Global Pre-Market Scanner singleton
pre_market_scanner = PreMarketScanner()
