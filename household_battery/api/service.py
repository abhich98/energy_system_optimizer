from __future__ import annotations

import io
import logging
import math
from typing import List

import pandas as pd

from esms.models import Battery
from household_battery.schedule import run_deterministic_schedule, run_expected_schedule
from household_battery.policies import PolicySpec, load_champion_local

from .errors import DataValidationError

logger = logging.getLogger(__name__)


def _batteries_from_specs(specs: List[dict]) -> List[Battery]:
    return [Battery(**spec) for spec in specs]


def _read_csv_text(csv_text: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(csv_text))


def _require_columns(df: pd.DataFrame, required: list[str], name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataValidationError(f"{name} missing required columns: {missing}")


def run_dayahead_deterministic(
    batteries_specs: List[dict], forecasts_csv_text: str, timestep_hours: float | None
) -> pd.DataFrame:
    df = _read_csv_text(forecasts_csv_text)
    _require_columns(df, ["pv", "load", "import_price"], "forecasts")

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        if not df["Date"].is_monotonic_increasing:
            raise DataValidationError("Date column must be sorted in ascending order")
        timestep_hours = (
            df["Date"].diff().dt.total_seconds().mode(dropna=True)[0] / 3600.0
        )
    else:
        if timestep_hours is None:
            raise DataValidationError(
                "timestep_hours must be provided if 'Date' column is missing"
            )
        df["Date"] = pd.date_range(
            start="2026-01-01", periods=len(df), freq=f"{timestep_hours}h"
        )

    T = int(round(24.0 / timestep_hours))
    bats = _batteries_from_specs(batteries_specs)

    # Calculate schedule for single-day
    day = pd.Timestamp(df["Date"].min().date())
    sched, _ = run_deterministic_schedule(day, df, bats, T)

    return sched.reset_index()


def run_dayahead_stochastic(
    batteries_specs: List[dict],
    history_csv_text: str,
    ahead_prices_csv_text: str,
    policy_override: dict | None,
    champion_path: str,
    timestep_hours: float | None,
) -> pd.DataFrame:
    hist = _read_csv_text(history_csv_text)
    ahead = _read_csv_text(ahead_prices_csv_text)
    _require_columns(hist, ["pv", "load"], "history")
    _require_columns(ahead, ["import_price"], "ahead_prices")

    if "Date" in hist.columns and "Date" in ahead.columns:
        hist["Date"] = pd.to_datetime(hist["Date"])
        ahead["Date"] = pd.to_datetime(ahead["Date"])

        if not hist["Date"].is_monotonic_increasing:
            raise DataValidationError(
                "History 'Date' column must be sorted in ascending order"
            )
        if not ahead["Date"].is_monotonic_increasing:
            raise DataValidationError(
                "Ahead prices 'Date' column must be sorted in ascending order"
            )
        if not math.isclose(
            hist["Date"].diff().dt.total_seconds().mode(dropna=True)[0],
            ahead["Date"].diff().dt.total_seconds().mode(dropna=True)[0],
        ):
            raise DataValidationError(
                "History and ahead prices 'Date' columns must have the same timestep"
            )
        # Ensure history period precedes ahead period
        if hist["Date"].max() >= ahead["Date"].min():
            raise DataValidationError(
                "History dates must precede ahead prices dates (max(history) < min(ahead))"
            )

        timestep_hours = (
            hist["Date"].diff().dt.total_seconds().mode(dropna=True)[0] / 3600.0
        )

    else:
        if timestep_hours is None:
            raise DataValidationError(
                "timestep_hours must be provided if 'Date' column is missing in history or ahead prices"
            )
        # Build ahead starting at a fixed anchor, and history ending just before it
        ahead_start = pd.Timestamp("2026-01-01 00:00:00")
        freq = pd.to_timedelta(f"{timestep_hours}h")
        ahead["Date"] = pd.date_range(start=ahead_start, periods=len(ahead), freq=freq)
        hist_end = ahead_start - freq
        hist_start = hist_end - (len(hist) - 1) * freq
        hist["Date"] = pd.date_range(start=hist_start, end=hist_end, freq=freq)

    import os

    if not os.path.exists(champion_path):
        raise FileNotFoundError("Champion policy file not found")
    spec = load_champion_local(champion_path)
    if policy_override:
        spec = PolicySpec(**{**spec.to_dict(), **policy_override})

    day = pd.Timestamp(ahead["Date"].min().date())
    T = int(round(24.0 / timestep_hours))

    # Create a synthetic dataset combining history + day prices placeholders
    hist["import_price"] = 0.0
    ahead["pv"] = 0.0
    ahead["load"] = 0.0
    dataset = pd.concat([hist, ahead], axis=0, ignore_index=True)
    logger.info(
        "Running champion policy '%s' on day %s with history_days=%d, num_scenarios=%d",
        spec.id,
        day.strftime("%Y-%m-%d"),
        spec.history_days,
        spec.num_scenarios,
    )
    logger.info(
        "Provided %s days of history data, shape: %s",
        hist["Date"].dt.date.nunique(),
        hist.shape,
    )

    # Calculate schedule for single-day using champion policy
    bats = _batteries_from_specs(batteries_specs)
    try:
        sched, _ = run_expected_schedule(spec, day, dataset, bats, T)
    except ValueError:
        # Mask backend ValueErrors as generic failures; routes will return a generic message
        raise RuntimeError("backend failure")
    return sched.reset_index()
