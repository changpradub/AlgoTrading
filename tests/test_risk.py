"""
Unit tests for core/risk_engine.py
"""

import pytest

from core.risk_engine import RiskEngine
from core.strategy import TradingSignal, SignalType


@pytest.fixture
def sample_buy_signal():
    return TradingSignal(
        symbol="NVDA",
        signal_type=SignalType.BUY,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        risk_reward_ratio=2.0,
        timeframe="1H",
        indicator_snapshot={"atr": 2.5},
    )


def test_daily_loss_limit_exceeded(sample_buy_signal):
    engine = RiskEngine(max_daily_loss_usd=14.0)

    # Within loss limit
    res_ok = engine.validate_signal(
        signal=sample_buy_signal,
        equity=700.0,
        current_daily_loss=5.0,
        open_positions=[],
        open_order_symbols=[],
        pdt_count_5_days=0,
    )
    assert res_ok.approved is True

    # Breaching loss limit -> Must reject and trigger kill switch
    res_breach = engine.validate_signal(
        signal=sample_buy_signal,
        equity=680.0,
        current_daily_loss=15.0,
        open_positions=[],
        open_order_symbols=[],
        pdt_count_5_days=0,
    )
    assert res_breach.approved is False
    assert "Max daily loss breached" in res_breach.reason
    assert engine.is_kill_switched is True


def test_duplicate_order_prevention(sample_buy_signal):
    engine = RiskEngine()
    res = engine.validate_signal(
        signal=sample_buy_signal,
        equity=700.0,
        current_daily_loss=0.0,
        open_positions=[],
        open_order_symbols=["NVDA"],  # Already an open order for NVDA
        pdt_count_5_days=0,
    )
    assert res.approved is False
    assert "Preventing duplicate" in res.reason


def test_max_positions_limit(sample_buy_signal):
    engine = RiskEngine(max_positions=3)
    res = engine.validate_signal(
        signal=sample_buy_signal,
        equity=700.0,
        current_daily_loss=0.0,
        open_positions=["AAPL", "MSFT", "TSM"],  # 3 positions open
        open_order_symbols=[],
        pdt_count_5_days=0,
    )
    assert res.approved is False
    assert "Max concurrent positions reached" in res.reason


def test_gap_risk_factor_adjustment(sample_buy_signal):
    engine = RiskEngine()

    # Normal ATR (2.5% of 100) -> factor = 1.0
    factor_normal, _ = engine.assess_gap_risk(atr=2.5, price=100.0)
    assert factor_normal == 1.0

    # Elevated ATR (4.0% of 100) -> factor = 0.75
    factor_moderate, _ = engine.assess_gap_risk(atr=4.0, price=100.0)
    assert factor_moderate == 0.75

    # High ATR (6.0% of 100) -> factor = 0.5
    factor_high, _ = engine.assess_gap_risk(atr=6.0, price=100.0)
    assert factor_high == 0.5
