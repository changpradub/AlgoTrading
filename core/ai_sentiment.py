"""
AI Sentiment Analysis & Gatekeeper Module
Integrates OpenRouter API (Google Gemini 3.8 Flash) to filter trading signals
and assess risk events before orders are dispatched.
Rule: AI functions strictly as a Gatekeeper/Filter — never initiates trades directly.
See UNIFIED_PLAN.md Section 4.4 & Section 7.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import aiohttp
import structlog

from config.settings import settings
from core.news_fetcher import NewsArticle, news_fetcher
from core.strategy import TradingSignal, SignalType
from db.connection import db_manager
from utils.timezone import now_utc

logger = structlog.get_logger(__name__)


class SentimentType(str, Enum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"


class GatekeeperAction(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"


@dataclass
class AISentimentReport:
    symbol: str
    sentiment: SentimentType
    confidence: float
    risk_event: bool
    event_type: str
    impact: str
    action_recommendation: GatekeeperAction
    reasoning: str
    raw_response: Dict[str, Any] = field(default_factory=dict)
    analyzed_at: datetime = field(default_factory=now_utc)


@dataclass
class GatekeeperDecision:
    approved: bool
    symbol: str
    action: GatekeeperAction
    sentiment_report: Optional[AISentimentReport]
    reason: str


SYSTEM_PROMPT = """You are a Senior Quantitative Risk Analyst and AI Gatekeeper for an Automated US Stock Trading Bot.
Your sole job is to evaluate recent financial news for a target stock and determine if it is safe to execute a BUY order, or if there is a severe risk event that warrants BLOCKING the trade.

Risk Events that MUST trigger action_recommendation = 'BLOCK':
1. Legal, regulatory, or criminal investigations (e.g., DOJ, SEC, antitrust subpoenas).
2. Major guidance or revenue forecast downgrades.
3. Accounting irregularities, auditor resignations, or financial restatements.
4. Sudden CEO/CFO departure under adverse circumstances.
5. Export bans, critical supply chain cancellations, or national security sanctions.

You must reply with a single valid JSON object strictly matching this schema:
{
  "symbol": "TICKER",
  "sentiment": "POSITIVE" | "NEUTRAL" | "NEGATIVE",
  "confidence": 0.0 to 1.0,
  "risk_event": true | false,
  "event_type": "none" | "earnings_downgrade" | "regulatory_probe" | "geopolitical" | "macro_concern" | "other",
  "impact": "LOW" | "MEDIUM" | "HIGH",
  "action_recommendation": "PASS" | "BLOCK",
  "reasoning": "Concise 1-2 sentence explanation of your decision."
}

Do NOT output any markdown commentary outside the JSON block. Output raw JSON only."""


class AISentimentGatekeeper:
    """Async AI Gatekeeper connecting to OpenRouter API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        fallback_model: str = "openai/gpt-4o-mini",
    ):
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.model = model or settings.OPENROUTER_MODEL
        self.fallback_model = fallback_model

    def _clean_json_response(self, text: str) -> Dict[str, Any]:
        """Extract and parse clean JSON from LLM output."""
        cleaned = text.strip()
        # Strip markdown fences if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
            cleaned = cleaned.strip()

        # Find first { and last }
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

        return json.loads(cleaned)

    async def analyze_news(
        self,
        symbol: str,
        articles: List[NewsArticle],
    ) -> AISentimentReport:
        """
        Send news articles to OpenRouter (Gemini 3.8 Flash) for risk & sentiment evaluation.
        """
        if not articles:
            # If no news available, default to neutral PASS
            return AISentimentReport(
                symbol=symbol.upper(),
                sentiment=SentimentType.NEUTRAL,
                confidence=0.5,
                risk_event=False,
                event_type="none",
                impact="LOW",
                action_recommendation=GatekeeperAction.PASS,
                reasoning="No recent news found. Defaulting to PASS.",
            )

        if not self.api_key:
            logger.warning("OpenRouter API Key not set. Defaulting to PASS without AI evaluation.")
            return AISentimentReport(
                symbol=symbol.upper(),
                sentiment=SentimentType.NEUTRAL,
                confidence=0.5,
                risk_event=False,
                event_type="none",
                impact="LOW",
                action_recommendation=GatekeeperAction.PASS,
                reasoning="OpenRouter API Key not configured.",
            )

        # Build news payload text
        news_text = ""
        for i, art in enumerate(articles[:5], 1):
            news_text += f"{i}. [{art.published_at.strftime('%Y-%m-%d %H:%M')}] {art.headline}\n   Summary: {art.summary}\n\n"

        user_content = f"Evaluate the following news articles for stock {symbol.upper()} to decide if a BUY order should be APPROVED (PASS) or BLOCKED:\n\n{news_text}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/changpradub/AlgoTrading",
            "X-Title": "Personal Algo-Trading Bot",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        # Attempt call with primary model, then fallback model if necessary
        models_to_try = [self.model, self.fallback_model]
        last_error = None

        for target_model in models_to_try:
            payload["model"] = target_model
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=15.0,
                    ) as resp:
                        if resp.status != 200:
                            err_body = await resp.text()
                            logger.warning(
                                "OpenRouter model failed",
                                model=target_model,
                                status=resp.status,
                                error=err_body,
                            )
                            last_error = f"HTTP {resp.status}: {err_body}"
                            continue

                        data = await resp.json()
                        content = data["choices"][0]["message"]["content"]
                        parsed = self._clean_json_response(content)

                        report = AISentimentReport(
                            symbol=symbol.upper(),
                            sentiment=SentimentType(parsed.get("sentiment", "NEUTRAL").upper()),
                            confidence=float(parsed.get("confidence", 0.5)),
                            risk_event=bool(parsed.get("risk_event", False)),
                            event_type=str(parsed.get("event_type", "none")),
                            impact=str(parsed.get("impact", "LOW")).upper(),
                            action_recommendation=GatekeeperAction(parsed.get("action_recommendation", "PASS").upper()),
                            reasoning=str(parsed.get("reasoning", "")),
                            raw_response=parsed,
                        )

                        logger.info(
                            "AI Sentiment Analysis completed",
                            symbol=symbol,
                            model=target_model,
                            action=report.action_recommendation.value,
                            sentiment=report.sentiment.value,
                            risk_event=report.risk_event,
                        )

                        # Save to DB if connected
                        await self._save_ai_analysis(report)
                        return report

            except Exception as e:
                logger.error("Error invoking OpenRouter API", model=target_model, error=str(e))
                last_error = str(e)

        # In case all models fail, fail-safe rule: PASS with warning rather than halting system,
        # but log critical warning
        logger.critical("All AI models failed on OpenRouter. Bypassing gatekeeper with warning.", error=last_error)
        return AISentimentReport(
            symbol=symbol.upper(),
            sentiment=SentimentType.NEUTRAL,
            confidence=0.0,
            risk_event=False,
            event_type="error_bypass",
            impact="LOW",
            action_recommendation=GatekeeperAction.PASS,
            reasoning=f"AI Gatekeeper offline ({last_error}). Trade allowed under standard Risk Engine controls.",
        )

    async def evaluate_signal_gatekeeper(
        self,
        signal: TradingSignal,
        articles: Optional[List[NewsArticle]] = None,
    ) -> GatekeeperDecision:
        """
        Evaluate a BUY signal through the AI Gatekeeper.
        Vetoes the signal if AI recommends BLOCK or detects a HIGH impact risk event.
        """
        if signal.signal_type != SignalType.BUY:
            return GatekeeperDecision(
                approved=False,
                symbol=signal.symbol,
                action=GatekeeperAction.BLOCK,
                sentiment_report=None,
                reason="Signal is not BUY.",
            )

        # Fetch recent news if not provided
        if articles is None:
            articles = await news_fetcher.fetch_news_for_symbol(signal.symbol, limit=5)

        report = await self.analyze_news(signal.symbol, articles)

        # Gatekeeper veto condition
        if report.action_recommendation == GatekeeperAction.BLOCK or (
            report.risk_event and report.impact == "HIGH"
        ):
            reason = f"AI Gatekeeper BLOCKED trade: {report.reasoning} (Impact: {report.impact})"
            logger.warning("BUY Signal VETOED by AI Gatekeeper", symbol=signal.symbol, reason=reason)
            return GatekeeperDecision(
                approved=False,
                symbol=signal.symbol,
                action=GatekeeperAction.BLOCK,
                sentiment_report=report,
                reason=reason,
            )

        return GatekeeperDecision(
            approved=True,
            symbol=signal.symbol,
            action=GatekeeperAction.PASS,
            sentiment_report=report,
            reason=f"AI Gatekeeper APPROVED: {report.reasoning}",
        )

    async def _save_ai_analysis(self, report: AISentimentReport) -> None:
        """Save AI analysis report to PostgreSQL ai_analysis table."""
        if not db_manager.is_connected:
            return

        try:
            await db_manager.execute(
                """
                INSERT INTO ai_analysis (symbol, headline, sentiment, confidence, risk_event, impact, raw_response)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                report.symbol,
                report.reasoning,
                report.sentiment.value,
                report.confidence,
                report.risk_event,
                report.impact,
                json.dumps(report.raw_response),
            )
        except Exception as e:
            logger.warning("Could not persist AI analysis to DB", error=str(e))


# Global AI Gatekeeper singleton
ai_gatekeeper = AISentimentGatekeeper()
