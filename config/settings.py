"""
Application Settings and Configuration Loader
Loads environment variables from .env with validation and sane defaults.
"""

from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 1. Alpaca Trading API Configuration
    ALPACA_API_KEY: str = Field(default="", description="Alpaca API Key ID (Trade Only)")
    ALPACA_SECRET_KEY: str = Field(default="", description="Alpaca Secret Key")
    ALPACA_BASE_URL: str = Field(
        default="https://paper-api.alpaca.markets",
        description="Base URL: paper-api or api.alpaca.markets",
    )
    ALPACA_DATA_FEED: str = Field(default="iex", description="Alpaca Market Data feed: iex or sip")
    TRADING_MODE: str = Field(default="paper", description="Trading mode: paper or live")

    # 2. Database Configuration (PostgreSQL)
    DB_HOST: str = Field(default="localhost")
    DB_PORT: int = Field(default=5432)
    DB_NAME: str = Field(default="algo_trading")
    DB_USER: str = Field(default="postgres")
    DB_PASSWORD: str = Field(default="")
    DB_MIN_CONNECTIONS: int = Field(default=2)
    DB_MAX_CONNECTIONS: int = Field(default=10)

    # 3. Notification Configuration (Telegram Bot)
    TELEGRAM_BOT_TOKEN: str = Field(default="")
    TELEGRAM_CHAT_ID: str = Field(default="")
    TELEGRAM_ENABLED: bool = Field(default=False)

    # 4. AI Gatekeeper (OpenRouter API) — Phase 3
    OPENROUTER_API_KEY: str = Field(default="")
    OPENROUTER_MODEL: str = Field(default="openai/gpt-4o-mini")

    # 5. Risk Management & Portfolio
    INITIAL_CAPITAL_USD: float = Field(default=700.0)
    MAX_DAILY_LOSS_USD: float = Field(default=14.0)
    MAX_POSITION_SIZE_USD: float = Field(default=140.0)
    TRADE_BUDGET_PER_TRANCHE_USD: float = Field(default=20.0)
    MAX_CONCURRENT_POSITIONS: int = Field(default=3)
    TARGET_SYMBOLS: str = Field(default="NVDA,TSM")

    # 6. System & Logging
    LOG_LEVEL: str = Field(default="INFO")
    APP_ENV: str = Field(default="development")

    @property
    def target_symbol_list(self) -> List[str]:
        """Return target symbols as a cleaned uppercase list."""
        return [s.strip().upper() for s in self.TARGET_SYMBOLS.split(",") if s.strip()]

    @property
    def is_paper_trading(self) -> bool:
        """Verify if running in paper trading mode."""
        return self.TRADING_MODE.lower() == "paper"

    @property
    def db_dsn(self) -> str:
        """PostgreSQL DSN string."""
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


# Singleton instance
settings = Settings()
