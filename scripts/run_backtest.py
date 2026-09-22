"""
Backtesting Runner Script
Executes strategy simulation on historical or realistic synthetic data.
Demonstrates Bracket Orders, Slippage modeling, and Overnight Gap Risk simulation.
Run with: .venv\\Scripts\\python scripts/run_backtest.py --symbol NVDA
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.engine import BacktestEngine
from backtest.reports import BacktestReporter
from config.settings import settings
from core.strategy import swing_strategy


def generate_realistic_market_data(symbol: str, bars: int = 400) -> pd.DataFrame:
    """
    Generates realistic 1-hour OHLCV market data covering trending,
    pullbacks, and occasional overnight gaps.
    """
    np.random.seed(101)
    dates = pd.date_range("2026-01-05 09:30", periods=bars, freq="1h")

    # Generate multi-regime price path (Bullish drift with oscillation)
    drift = np.linspace(120, 165, bars)
    noise = np.sin(np.linspace(0, 15, bars)) * 4.0 + np.random.randn(bars).cumsum() * 0.8
    close = np.maximum(50.0, drift + noise)

    open_p = close + np.random.uniform(-0.6, 0.6, bars)
    high = np.maximum(open_p, close) + np.random.uniform(0.3, 1.5, bars)
    low = np.minimum(open_p, close) - np.random.uniform(0.3, 1.5, bars)
    volume = np.random.uniform(50000, 2000000, bars)

    # Inject an occasional overnight gap to test Gap Risk handling
    for idx in range(20, bars, 60):
        low[idx] = low[idx] - 3.5
        open_p[idx] = open_p[idx] - 3.0

    df = pd.DataFrame({
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)

    return df


async def main():
    parser = argparse.ArgumentParser(description="Run Algo-Trading Strategy Backtest")
    parser.add_argument("--symbol", type=str, default="NVDA", help="Ticker symbol to backtest")
    parser.add_argument("--capital", type=float, default=700.0, help="Initial portfolio capital ($)")
    parser.add_argument("--slippage", type=float, default=0.001, help="Slippage percentage (0.001 = 0.1%)")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    print(f"\n[Backtest] Loading historical data for {symbol}...")

    # Attempt fetching from Alpaca if credentials are set, otherwise use synthetic dataset
    df = None
    if settings.ALPACA_API_KEY and settings.ALPACA_SECRET_KEY:
        try:
            from core.market_data import market_data_client
            print("  • Fetching live historical bars from Alpaca API...")
            df = await market_data_client.get_historical_bars(symbol=symbol, limit=250)
        except Exception as e:
            print(f"  • Alpaca API fetch notice ({e}); switching to synthetic dataset.")

    if df is None or df.empty or len(df) < 150:
        print("  • Utilizing realistic multi-regime dataset (400 bars) with Overnight Gap modeling...")
        df = generate_realistic_market_data(symbol, bars=400)

    print(f"  • Dataset ready: {len(df)} bars ({df.index[0]} to {df.index[-1]})")

    # Run Backtest
    engine = BacktestEngine(
        initial_capital=args.capital,
        slippage_pct=args.slippage,
        strategy=swing_strategy,
    )
    result = engine.run(symbol=symbol, df_ltf=df, warmup_bars=100)

    # Print Report
    BacktestReporter.print_summary(result)


if __name__ == "__main__":
    asyncio.run(main())
