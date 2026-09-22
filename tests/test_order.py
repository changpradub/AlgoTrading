"""
Unit tests for core/order_execution.py and core/position_sizing.py
"""

import pytest
from alpaca.trading.enums import OrderSide, OrderClass, TimeInForce

from core.order_execution import OrderExecutionEngine
from core.position_sizing import PositionSizingCalculator


def test_bracket_order_builder_invariants():
    engine = OrderExecutionEngine()
    req = engine.build_bracket_order_request(
        symbol="NVDA",
        qty=0.15,
        take_profit_price=110.0,
        stop_loss_price=95.0,
        limit_price=100.0,
    )

    # Invariants: Must be Bracket order, Buy side, GTC time in force
    assert req.symbol == "NVDA"
    assert req.qty == 0.15
    assert req.side == OrderSide.BUY
    assert req.order_class == OrderClass.BRACKET
    assert req.time_in_force == TimeInForce.GTC
    assert req.take_profit is not None
    assert req.take_profit.limit_price == 110.0
    assert req.stop_loss is not None
    assert req.stop_loss.stop_price == 95.0


def test_position_sizing_fractional_shares():
    calc = PositionSizingCalculator(tranche_budget_usd=20.0, risk_per_trade_pct=0.02)
    # Entry at $140.0, SL at $133.0 (Risk per share = $7.0)
    # Tranche budget = $20.0 -> max shares by budget = 20 / 140 = ~0.1428 shares
    res = calc.calculate(
        equity=700.0,
        buying_power=700.0,
        entry_price=140.0,
        stop_loss=133.0,
        risk_factor=1.0,
    )

    assert res.is_valid is True
    assert res.shares > 0.0
    assert res.shares == round(res.shares, 4)
    assert res.notional_usd <= 20.0 + 0.10


def test_position_sizing_scaled_by_gap_risk():
    calc = PositionSizingCalculator(tranche_budget_usd=20.0)
    res_normal = calc.calculate(equity=700.0, buying_power=700.0, entry_price=100.0, stop_loss=95.0, risk_factor=1.0)
    res_gap_risk = calc.calculate(equity=700.0, buying_power=700.0, entry_price=100.0, stop_loss=95.0, risk_factor=0.5)

    assert res_gap_risk.shares < res_normal.shares
    assert abs(res_gap_risk.shares - (res_normal.shares * 0.5)) < 0.001
