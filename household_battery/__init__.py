"""Household day-ahead scheduling (use-case layer).

This package builds on the general `esms` optimization core to provide:
- Policy specs for champion–challenger evaluation
- Seeded holdout/backtest splits
- Rolling-origin backtesting utilities
- KPI computation and promotion rules

Note: Keep domain-agnostic logic in `esms/*`. Put household-specific
workflow glue here.
"""

__all__ = [
    "policies",
    "split",
    "backtest",
    "metrics",
    "selection",
]
