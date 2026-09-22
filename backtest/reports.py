"""
Backtest Performance Reporting Module
Formats backtesting results into readable summaries, markdown reports, and metrics tables.
See UNIFIED_PLAN.md Section 4.5.
"""

from backtest.engine import BacktestResult


class BacktestReporter:
    """Formats backtest performance results."""

    @staticmethod
    def print_summary(res: BacktestResult) -> None:
        """Print formatted metrics to stdout."""
        print("\n" + "=" * 65)
        print(f"  BACKTEST PERFORMANCE REPORT: {res.symbol.upper()}")
        print("=" * 65)
        print(f"  • Initial Capital:        ${res.initial_capital:,.2f}")
        print(f"  • Final Equity:           ${res.final_equity:,.2f}")
        print(f"  • Total Net P/L:          ${res.total_net_pnl:+,.2f} ({res.total_return_pct:+.2f}%)")
        print(f"  • Total Trades:           {res.total_trades}")
        print(f"  • Win / Loss:             {res.winning_trades} / {res.losing_trades}")
        print(f"  • Win Rate:               {res.win_rate_pct:.1f}%")
        print(f"  • Profit Factor:          {res.profit_factor:.2f}")
        print(f"  • Max Drawdown:           {res.max_drawdown_pct:.2f}%")
        print(f"  • Avg P/L per Trade:      ${res.avg_trade_pnl:+,.2f}")
        print("=" * 65)

        # Highlight gap risk events if any
        gap_trades = [t for t in res.trades if t.exit_reason == "gap_stop_loss"]
        if gap_trades:
            print(f"\n⚠️  [GAP RISK ALERT] {len(gap_trades)} trade(s) suffered overnight gap past Stop Loss:")
            for t in gap_trades:
                print(f"    - {t.symbol} exited at ${t.exit_price:.2f} due to gap (P/L: ${t.net_pnl:+.2f})")
            print("=" * 65)

    @staticmethod
    def generate_markdown(res: BacktestResult) -> str:
        """Generate markdown report string."""
        md = f"""# Backtest Report: {res.symbol.upper()}

| Metric | Result |
|---|---|
| **Initial Capital** | ${res.initial_capital:,.2f} |
| **Final Equity** | ${res.final_equity:,.2f} |
| **Net P/L** | **${res.total_net_pnl:+,.2f} ({res.total_return_pct:+.2f}%)** |
| **Total Trades** | {res.total_trades} |
| **Win Rate** | {res.win_rate_pct:.1f}% ({res.winning_trades}W / {res.losing_trades}L) |
| **Profit Factor** | {res.profit_factor:.2f} |
| **Max Drawdown** | {res.max_drawdown_pct:.2f}% |
| **Avg Trade P/L** | ${res.avg_trade_pnl:+,.2f} |

"""
        return md


reporter = BacktestReporter()
