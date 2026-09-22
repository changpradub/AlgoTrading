"""
Structured Logging Setup using structlog
Outputs JSON to log files and colored human-readable text to stdout.
Ensures all log timestamps are timezone-aware UTC.
"""

import logging
import os
import sys
from pathlib import Path
import structlog
from structlog.types import EventDict

from utils.timezone import now_utc

# Ensure logs directory exists
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

BOT_LOG_PATH = LOGS_DIR / "bot.log"
TRADES_LOG_PATH = LOGS_DIR / "trades.log"
ERRORS_LOG_PATH = LOGS_DIR / "errors.log"


def add_utc_timestamp(logger, method_name: str, event_dict: EventDict) -> EventDict:
    """Inject UTC ISO timestamp into every log entry."""
    event_dict["timestamp"] = now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    return event_dict


def filter_trades_only(logger, method_name: str, event_dict: EventDict) -> EventDict:
    """Pass-through for trade specific log entries."""
    if event_dict.get("log_type") == "trade":
        return event_dict
    raise structlog.DropEvent


def filter_errors_only(logger, method_name: str, event_dict: EventDict) -> EventDict:
    """Filter for warnings and errors only."""
    level = event_dict.get("level", "").lower()
    if level in ("warning", "error", "critical", "exception"):
        return event_dict
    raise structlog.DropEvent


def configure_logging(log_level: str = "INFO"):
    """
    Configures standard library logging and structlog processors.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=numeric_level)

    # Common processors for formatting event dictionary
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_utc_timestamp,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Attach file handlers to root logger
    root_logger = logging.getLogger()

    # 1. Main Bot Log (JSON)
    bot_handler = logging.FileHandler(BOT_LOG_PATH, encoding="utf-8")
    bot_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.processors.JSONRenderer()],
    )
    bot_handler.setFormatter(bot_formatter)
    bot_handler.setLevel(numeric_level)
    root_logger.addHandler(bot_handler)

    # 2. Errors Log (JSON, Warning+)
    err_handler = logging.FileHandler(ERRORS_LOG_PATH, encoding="utf-8")
    err_handler.setFormatter(bot_formatter)
    err_handler.setLevel(logging.WARNING)
    root_logger.addHandler(err_handler)


def get_trade_logger(name: str = "trades"):
    """Get a logger explicitly tagged for trades."""
    logger = structlog.get_logger(name)
    return logger.bind(log_type="trade")


# Initial setup on module import
configure_logging()
logger = structlog.get_logger("bot")
