"""
Example usage of EsMS Energy Optimizer for day-ahead optimization.
Runs deterministic optimization for each day in a specified time period in parallel.
"""

import logging
import numpy as np
import pandas as pd
import json
import datetime
import argparse
from typing import Any, Dict, List
from copy import deepcopy

from joblib import Parallel, delayed

from esms.models import Battery
from esms.optimization import EnergyOptimizer
from esms.utils import get_available_pyomo_solvers

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Perfect Foresight Optim.")


def build_batteries(battery_specs: List[Dict[str, Any]]) -> List[Battery]:
    """Create Battery objects from specifications."""
    return [Battery(**spec) for spec in battery_specs]


def solve_day_deterministic(
    day_df: pd.DataFrame,
    battery_specs: List[Dict[str, Any]],
    solver: str = "scip",
    timestep_hours: float = 1.0,
) -> pd.DataFrame:
    """Optimize a single day with deterministic approach.

    Args:
        day_df: DataFrame with one day's forecast data (24 hours)
        battery_specs: List of battery configuration dictionaries
        solver: Pyomo solver name to use

    Returns:
        DataFrame with optimization results for the day
    """
    pv_forecast = day_df["PV generation (kW)"].to_numpy(dtype=float)
    load_forecast = day_df["Consumption (kW)"].to_numpy(dtype=float)
    import_price_forecast = day_df["Energy price (EUR/kWh)"].to_numpy(dtype=float)

    solver_args = {}
    if solver == "scip":
        solver_args = {"solver_io": "nl"}

    optimizer = EnergyOptimizer(
        batteries=build_batteries(battery_specs),
        load_forecast=load_forecast,
        pv_forecast=pv_forecast,
        import_price_forecast=import_price_forecast,
        timestep_hours=timestep_hours,
    )

    results = optimizer.solve(solver_name=solver, verbose=False, **solver_args)

    results_df = optimizer.results_to_dataframe(results)
    results_df.index = pd.to_datetime(day_df["Date"].to_numpy())
    results_df.index.name = "Date"

    return results_df


def main():
    """Run day-ahead deterministic optimization for a period of days."""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Run deterministic optimization for each day in a period."
    )

    parser.add_argument(
        "--data_file", type=str, required=True, help="Path to the dataset Excel file"
    )
    parser.add_argument(
        "--battery_file",
        type=str,
        required=True,
        help="Path to the battery configuration JSON file",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2025,
        required=False,
        help="Dataset year to use for analysis",
    )
    parser.add_argument(
        "--start_day_index",
        type=int,
        required=True,
        help="Index of the first day to optimize (0-364)",
    )
    parser.add_argument(
        "--num_days",
        type=int,
        default=1,
        required=False,
        help="Number of consecutive days to optimize",
    )
    parser.add_argument(
        "--solver",
        type=str,
        default="scip",
        required=False,
        help="Pyomo solver to use (e.g., 'glpk', 'scip')",
    )
    parser.add_argument(
        "--output_file",
        type=str,
        default="deterministic_optimization_results.csv",
        required=False,
        help="Path to save optimization results CSV",
    )

    args = parser.parse_args()

    # Load dataset
    logger.info("Loading dataset from %s", args.data_file)
    data_df = pd.read_excel(
        args.data_file, sheet_name=f"{args.year} data", usecols="A:F"
    )

    # Load battery specs
    logger.info("Loading battery configuration from %s", args.battery_file)
    with open(args.battery_file, "r") as f:
        def_battery_specs = json.load(f)

    # Validate solver
    day_idx = args.start_day_index
    num_days = args.num_days
    solver_to_use = args.solver
    if solver_to_use not in get_available_pyomo_solvers():
        logger.warning(
            f"Solver '{solver_to_use}' is not available. Falling back to 'glpk'."
        )
        solver_to_use = "glpk"

    time_series = pd.Series(pd.to_datetime(data_df["Date"].unique())).sort_values(
        ignore_index=True
    )
    time_series_diff_hours = time_series.diff().dt.total_seconds() / 3600.0
    time_res_hrs = time_series_diff_hours.mode()[0]
    time_points_per_day = int(24 / time_res_hrs)

    # Get date range
    start_date = data_df.iloc[day_idx * time_points_per_day]["Date"].date()
    end_date = data_df.iloc[(day_idx + num_days) * time_points_per_day - 1][
        "Date"
    ].date()

    logger.info("=" * 60)
    logger.info("EsMS Energy Optimizer - Deterministic Optimization (Parallel)")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Number of days: {num_days}")
    logger.info(f"Number of batteries: {len(def_battery_specs)}")
    logger.info(f"Solver: {solver_to_use}")
    logger.info("=" * 60)

    # Run optimization for each day in parallel
    logger.info("Starting optimization for %d days in parallel...", num_days)
    start_time = datetime.datetime.now()

    try:
        day_results = Parallel(n_jobs=-1)(
            delayed(solve_day_deterministic)(
                day_df=data_df.iloc[
                    day_idx * time_points_per_day
                    + i * time_points_per_day : day_idx * time_points_per_day
                    + (i + 1) * time_points_per_day
                ],
                battery_specs=deepcopy(def_battery_specs),
                solver=solver_to_use,
                timestep_hours=time_res_hrs,
            )
            for i in range(num_days)
        )

        # Concatenate results from all days
        results_df = pd.concat(day_results, axis=0)
        results_df.sort_index(inplace=True)

        end_time = datetime.datetime.now()
        elapsed_time = end_time - start_time

        logger.info("=" * 60)
        logger.info("OPTIMIZATION COMPLETED")
        logger.info("=" * 60)
        logger.info(f"Optimization completed in {elapsed_time}")
        logger.info(
            f"Generated output has {len(results_df) // time_points_per_day} days"
        )

        # Save results
        results_df.to_csv(args.output_file)
        logger.info(f"Results saved to {args.output_file}")

        logger.info(f"First 5 timesteps:")
        logger.info(results_df.head(5))
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        raise


if __name__ == "__main__":
    main()
