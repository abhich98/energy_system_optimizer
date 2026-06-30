from __future__ import annotations

import random
from typing import Tuple
import pandas as pd


def make_noncontiguous_holdout(
    dates: pd.DatetimeIndex, holdout_days: int, seed: int
) -> Tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Sample non-contiguous holdout days from a date index (unique days).

    Returns (holdout_dates, backtest_dates) where both are day-level indices.
    """
    rng = random.Random(seed)
    unique_days = pd.to_datetime(pd.Series(dates.date).unique())
    if holdout_days >= len(unique_days):
        raise ValueError("holdout_days must be less than total unique days")

    sampled = rng.sample(list(unique_days), holdout_days)
    holdout = pd.DatetimeIndex(sorted(sampled))
    backtest = unique_days.difference(holdout)
    return holdout, backtest


def persist_split(
    holdout: pd.DatetimeIndex, backtest: pd.DatetimeIndex, out_dir: str
) -> None:
    from pathlib import Path

    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    pd.Series(holdout).to_csv(p / "holdout_days.csv", index=False, header=["Date"])
    pd.Series(backtest).to_csv(p / "backtest_days.csv", index=False, header=["Date"])
