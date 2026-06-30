from __future__ import annotations

from typing import Dict, Any, Tuple
import time
import numpy as np
import pandas as pd
import logging

from esms.models import Battery
from esms.optimization import StochasticEnergyOptimizer, EnergyOptimizer
from sklearn.metrics.pairwise import manhattan_distances

import kmedoids

from .policies import PolicySpec

logging.getLogger("esms.optimization").setLevel(logging.WARNING)
logging.getLogger("pyomo.core").setLevel(logging.ERROR)


def _day_slice(frame: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame:
    start = pd.Timestamp(day).normalize()
    end = start + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return frame[(frame["Date"] >= start) & (frame["Date"] <= end)].copy()


def _history_slice(
    frame: pd.DataFrame, day: pd.Timestamp, history_days: int
) -> pd.DataFrame:
    end = pd.Timestamp(day).normalize()
    start = end - pd.Timedelta(days=history_days)
    return frame[(frame["Date"] >= start) & (frame["Date"] < end)].copy()


def _get_solver_args(solver_name: str) -> Dict[str, Any]:
    """Return solver-specific arguments for Pyomo solver."""
    if solver_name == "scip":
        return {"solver_io": "nl"}
    else:
        return {}


def generate_daily_scenarios(
    policy: PolicySpec,
    history_df: pd.DataFrame,
    time_points_per_day: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    load_hist = (
        history_df["load"].to_numpy(dtype=float).reshape(-1, time_points_per_day)
    )
    pv_hist = history_df["pv"].to_numpy(dtype=float).reshape(-1, time_points_per_day)

    def _normalized(m: np.ndarray) -> np.ndarray:
        mx = float(np.max(m))
        return np.zeros_like(m) if np.isclose(mx, 0.0) else (m / mx)

    pv_distances = manhattan_distances(pv_hist)
    load_distances = manhattan_distances(load_hist)
    hist_distance = policy.pv_coeff * _normalized(
        pv_distances
    ) + policy.load_coeff * _normalized(load_distances)

    num_scenarios = policy.num_scenarios
    if load_hist.shape[0] < policy.num_scenarios:
        logging.warning(
            f"Number of history days ({load_hist.shape[0]}) is less than the number of requested scenarios ({policy.num_scenarios}). "
            "Reducing the number of scenarios!"
        )
        num_scenarios = load_hist.shape[0]
    model = kmedoids.KMedoids(
        n_clusters=num_scenarios,
        metric="precomputed",
        random_state=policy.seed,
    )
    model.fit(hist_distance)

    medoid_indices = model.medoid_indices_
    label_counts = np.bincount(model.labels_, minlength=num_scenarios)
    probabilities = label_counts / np.sum(label_counts)

    load_scenarios = load_hist[medoid_indices]
    pv_scenarios = pv_hist[medoid_indices]

    return load_scenarios, pv_scenarios, probabilities


def run_expected_schedule(
    policy: PolicySpec,
    day: pd.Timestamp,
    dataset: pd.DataFrame,
    batteries: list[Battery],
    time_points_per_day: int,
) -> Tuple[pd.DataFrame, float]:
    """Build expected schedule for a single day using last-P scenarios.

    Returns (expected_df, runtime_sec)
    """
    day_df = _day_slice(dataset, day)
    hist_df = _history_slice(dataset, day, policy.history_days)

    load_scen, pv_scen, probs = generate_daily_scenarios(
        policy, hist_df, time_points_per_day
    )

    import_price_rt_day = day_df["import_price"].to_numpy(dtype=float)
    import_price_rt = np.tile(import_price_rt_day, (policy.num_scenarios, 1))
    export_price_rt = np.zeros_like(import_price_rt)
    import_price_ahead = np.zeros(time_points_per_day)
    export_price_ahead = np.zeros(time_points_per_day)

    opt = StochasticEnergyOptimizer(
        batteries=batteries,
        load_scenarios=load_scen,
        pv_scenarios=pv_scen,
        import_price_ahead=import_price_ahead,
        export_price_ahead=export_price_ahead,
        import_price_rt_scenarios=import_price_rt,
        export_price_rt_scenarios=export_price_rt,
        scenario_probabilities=probs,
        timestep_hours=float(24 / time_points_per_day),
    )

    t0 = time.time()
    opt.build_model(
        grid_import_ahead_values=np.zeros(time_points_per_day),
        grid_export_ahead_values=np.zeros(time_points_per_day),
        charge_realtime_values=np.zeros(
            (len(batteries), policy.num_scenarios, time_points_per_day)
        ),
        discharge_realtime_values=np.zeros(
            (len(batteries), policy.num_scenarios, time_points_per_day)
        ),
    )
    res = opt.solve(
        solver_name=policy.solver, verbose=False, **_get_solver_args(policy.solver)
    )
    runtime = time.time() - t0

    expected_df = opt.results_to_dataframe(res)
    expected_df.index = pd.to_datetime(day_df["Date"].to_numpy())
    expected_df.index.name = "Date"
    return expected_df, runtime


def run_deterministic_schedule(
    day: pd.Timestamp,
    dataset: pd.DataFrame,
    batteries: list[Battery],
    time_points_per_day: int,
) -> Tuple[pd.DataFrame, float]:
    day_df = _day_slice(dataset, day)
    pv = day_df["pv"].to_numpy(dtype=float)
    load = day_df["load"].to_numpy(dtype=float)
    price = day_df["import_price"].to_numpy(dtype=float)

    opt = EnergyOptimizer(
        batteries=batteries,
        load_forecast=load,
        pv_forecast=pv,
        import_price_forecast=price,
        timestep_hours=float(24 / time_points_per_day),
    )
    t0 = time.time()
    opt.build_model()
    res = opt.solve(solver_name="scip", verbose=False, **_get_solver_args("scip"))
    runtime = time.time() - t0

    df = opt.results_to_dataframe(res)
    df.index = pd.to_datetime(day_df["Date"].to_numpy())
    df.index.name = "Date"
    return df, runtime


def evaluate_expected_schedule(
    day: pd.Timestamp,
    dataset: pd.DataFrame,
    batteries: list[Battery],
    battery_sched: pd.DataFrame,
    time_points_per_day: int,
) -> Tuple[pd.DataFrame, float]:
    day_df = _day_slice(dataset, day)
    pv = day_df["pv"].to_numpy(dtype=float)
    load = day_df["load"].to_numpy(dtype=float)
    price = day_df["import_price"].to_numpy(dtype=float)

    # Schedule values for battery charge/discharge
    bess_charge_values = np.zeros((len(batteries), time_points_per_day))
    bess_discharge_values = np.zeros((len(batteries), time_points_per_day))
    for b_idx, battery in enumerate(batteries):
        bess_charge_values[b_idx, :] = battery_sched[
            f"{battery.id}_charge_ahead"
        ].to_numpy(dtype=float)
        bess_discharge_values[b_idx, :] = battery_sched[
            f"{battery.id}_discharge_ahead"
        ].to_numpy(dtype=float)

    opt = EnergyOptimizer(
        batteries=batteries,
        load_forecast=load,
        pv_forecast=pv,
        import_price_forecast=price,
        timestep_hours=float(24 / time_points_per_day),
    )
    t0 = time.time()
    opt.build_model(
        charge_values=np.clip(bess_charge_values, 0, None),
        discharge_values=np.clip(bess_discharge_values, 0, None),
    )
    res = opt.solve(solver_name="scip", verbose=False, **_get_solver_args("scip"))
    runtime = time.time() - t0

    df = opt.results_to_dataframe(res)
    df.index = pd.to_datetime(day_df["Date"].to_numpy())
    df.index.name = "Date"
    return df, runtime
