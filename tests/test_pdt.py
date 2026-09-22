"""
Unit tests for Pattern Day Trading (PDT) Rule compliance in core/risk_engine.py
"""

import pytest
from core.risk_engine import RiskEngine


def test_pdt_under_25k_blocks_excessive_day_trades():
    engine = RiskEngine(pdt_limit=3, pdt_equity_threshold=25000.0)

    # 1. Under $25k with 2 day trades -> Allowed
    ok, msg = engine.check_pdt_compliance(equity=700.0, pdt_count_5_days=2, intending_day_trade=True)
    assert ok is True

    # 2. Under $25k with 3 day trades and trying to day trade -> Blocked
    blocked, msg = engine.check_pdt_compliance(equity=700.0, pdt_count_5_days=3, intending_day_trade=True)
    assert blocked is False
    assert "PDT Limit reached" in msg

    # 3. Under $25k with 3 day trades but entering Swing (holding overnight) -> Allowed with warning
    swing_ok, msg = engine.check_pdt_compliance(equity=700.0, pdt_count_5_days=3, intending_day_trade=False)
    assert swing_ok is True


def test_pdt_above_25k_is_exempt():
    engine = RiskEngine(pdt_limit=3, pdt_equity_threshold=25000.0)

    # Over $25k equity -> Exempt from PDT restriction
    ok, msg = engine.check_pdt_compliance(equity=30000.0, pdt_count_5_days=5, intending_day_trade=True)
    assert ok is True
    assert "PDT exempt" in msg
