"""Run config-driven rolling stochastic optimization on a continuous yearly dataset."""

from __future__ import annotations

import argparse
import datetime
import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

import kmedoids
import numpy as np
import pandas as pd
import yaml
from joblib import Parallel, delayed
from sklearn.metrics.pairwise import manhattan_distances
import wandb

from esms.eval import OptimizationCostCalculator
from esms.optimization import StochasticEnergyOptimizer
from esms.utils import get_available_pyomo_solvers
from perfect_foresight_optimization import build_batteries 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Stochastic Optim.")


def load_config(config_path: str) -> dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def _normalized(matrix: np.ndarray) -> np.ndarray:
    max_val = float(np.max(matrix))
    if np.isclose(max_val, 0.0):
        return np.zeros_like(matrix)
    return matrix / max_val


def generate_daily_scenarios(
    history_df: pd.DataFrame,
    time_points_per_day: int,
    num_scenarios: int,
    pv_coeff: float,
    load_coeff: float,
    random_state: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    load_hist = (
        history_df["Consumption (kW)"]
        .to_numpy(dtype=float)
        .reshape(-1, time_points_per_day)
    )
    pv_hist = (
        history_df["PV generation (kW)"]
        .to_numpy(dtype=float)
        .reshape(-1, time_points_per_day)
    )

    pv_distances = manhattan_distances(pv_hist)
    load_distances = manhattan_distances(load_hist)
    hist_distance = (
        pv_coeff * _normalized(pv_distances)
        + load_coeff * _normalized(load_distances)
    )

    model = kmedoids.KMedoids(
        n_clusters=num_scenarios,
        metric="precomputed",
        random_state=random_state,
    )
    model.fit(hist_distance)

    medoid_indices = model.medoid_indices_
    label_counts = np.bincount(model.labels_, minlength=num_scenarios)
    probabilities = label_counts / np.sum(label_counts)

    load_scenarios = load_hist[medoid_indices]
    pv_scenarios = pv_hist[medoid_indices]

    return load_scenarios, pv_scenarios, probabilities


def _solve_single_day(
    day_idx: int,
    data_df: pd.DataFrame,
    battery_specs: list[dict[str, Any]],
    time_points_per_day: int,
    history_days: int,
    num_scenarios: int,
    pv_coeff: float,
    load_coeff: float,
    random_state: int,
    solver: str,
    timestep_hours: float,
    save_scenario_results: bool,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:

    logging.getLogger("esms.optimization").setLevel(logging.WARNING)
    logging.getLogger("pyomo.core").setLevel(logging.ERROR)

    day_start = day_idx * time_points_per_day
    day_end = (day_idx + 1) * time_points_per_day
    history_start = (day_idx - history_days) * time_points_per_day
    day_df = data_df.iloc[day_start:day_end].copy()
    history_df = data_df.iloc[history_start:day_start].copy()

    load_scenarios, pv_scenarios, probabilities = generate_daily_scenarios(
        history_df=history_df,
        time_points_per_day=time_points_per_day,
        num_scenarios=num_scenarios,
        pv_coeff=pv_coeff,
        load_coeff=load_coeff,
        random_state=random_state + day_idx,
    )

    import_price_rt_day = day_df["Energy price (EUR/kWh)"].to_numpy(dtype=float)
    import_price_rt = np.tile(import_price_rt_day, (num_scenarios, 1))
    import_price_ahead = np.zeros(time_points_per_day)
    export_price_ahead = np.zeros(time_points_per_day)
    export_price_rt = np.zeros_like(import_price_rt)

    solver_args: dict[str, Any] = {}
    if solver == "scip":
        solver_args = {"solver_io": "nl"}

    stochastic_optimizer = StochasticEnergyOptimizer(
        batteries=build_batteries(deepcopy(battery_specs)),
        load_scenarios=load_scenarios,
        pv_scenarios=pv_scenarios,
        import_price_ahead=import_price_ahead,
        export_price_ahead=export_price_ahead,
        import_price_rt_scenarios=import_price_rt,
        export_price_rt_scenarios=export_price_rt,
        scenario_probabilities=probabilities,
        timestep_hours=timestep_hours,
    )

    stochastic_optimizer.build_model(
        grid_import_ahead_values=np.zeros(time_points_per_day),
        grid_export_ahead_values=np.zeros(time_points_per_day),
        charge_realtime_values=np.zeros((len(battery_specs), num_scenarios, time_points_per_day)),
        discharge_realtime_values=np.zeros((len(battery_specs), num_scenarios, time_points_per_day))
    )

    stochastic_results = stochastic_optimizer.solve(
        solver_name=solver,
        verbose=False,
        **solver_args,
    )

    expected_df = stochastic_optimizer.results_to_dataframe(stochastic_results)
    expected_df.index = pd.to_datetime(day_df["Date"].to_numpy())
    expected_df.index.name = "Date"

    scenario_df: pd.DataFrame | None = None
    if save_scenario_results:
        scenario_df = stochastic_optimizer.scenario_results_to_dataframe(stochastic_results)
        day_dates = pd.to_datetime(day_df["Date"].to_numpy())
        scenario_df["Date"] = scenario_df["timestep"].astype(int).map(
            dict(enumerate(day_dates))
        )
        scenario_df.index.name = "Date"

    return expected_df, scenario_df


def _init_wandb(config: dict[str, Any]):
    wandb_cfg = config.get("wandb", {})
    if not wandb_cfg.get("enabled", True):
        return None

    return wandb.init(
        project=wandb_cfg.get("project", "esms-stochastic-optimization"),
        entity=wandb_cfg.get("entity"),
        name=wandb_cfg.get("run_name"),
        tags=wandb_cfg.get("tags", ["stochastic"]),
        config=config,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run rolling stochastic optimization using config parameters."
    )
    parser.add_argument(
        "--data_file", type=str, required=True, help="Path to the dataset Excel file"
    )
    parser.add_argument(
        "--config_file",
        type=str, 
        required=True,
        help="Path to YAML configuration file.",
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
        "--num_scenarios",
        type=int,
        default=3,
        required=False,
        help="Number of scenarios to generate per day",
    )
    parser.add_argument(
        "--scenario_output_file",
        type=str,
        default=None,
        required=False,
        help="Path to save scenario-wise results CSV (optional)",
    )
    parser.add_argument(
        "--output_file",
        type=str,
        default="stochastic_optimization_results.csv",
        required=False,
        help="Path to save expected results CSV (optional)",
    )

    args = parser.parse_args()

    config = load_config(args.config_file)

    # CLI args override config file values
    data_file = config["data_file"] = args.data_file
    battery_file = config["battery_file"] = args.battery_file
    output_expected_file = config["output_file"] = args.output_file

    year = config["year"] = args.year
    num_scenarios = config["num_scenarios"] = args.num_scenarios
    if args.scenario_output_file is not None:
        config["save_scenario_results"] = True
    else:
        config["save_scenario_results"] = False
    output_scenario_file = config["scenario_output_file"] = args.scenario_output_file

    # Extract other config parameters
    start_day_index = int(config["start_day_index"])
    num_days = int(config["num_days"])
    history_days = int(config["history_days"])

    pv_coeff = float(config["pv_coeff"])
    load_coeff = float(config["load_coeff"])

    solver_to_use = str(config.get("solver", "scip"))
    n_jobs = int(config.get("n_jobs", -1))
    random_state = int(config.get("random_state", 3))

    if not np.isclose(pv_coeff + load_coeff, 1.0):
        raise ValueError("pv_coeff + load_coeff must equal 1.0")

    logger.info("Loading dataset from %s", data_file)
    data_df = pd.read_excel(data_file, sheet_name=f"{year} data", usecols="A:F")

    time_series = pd.Series(pd.to_datetime(data_df["Date"].unique())).sort_values(
        ignore_index=True
    )
    time_series_diff_hours = time_series.diff().dt.total_seconds() / 3600.0
    timestep_hours = float(time_series_diff_hours.mode(dropna=True)[0])
    time_points_per_day = int(24 / timestep_hours)

    if start_day_index < history_days:
        raise ValueError(
            "start_day_index must be >= history_days so each optimized day has enough history"
        )

    total_days = len(data_df) // time_points_per_day
    if start_day_index + num_days > total_days:
        raise ValueError("Requested day range exceeds available dataset days")

    logger.info("Loading battery configuration from %s", battery_file)
    with Path(battery_file).open("r", encoding="utf-8") as f:
        battery_specs = json.load(f)

    if solver_to_use not in get_available_pyomo_solvers():
        logger.warning(
            "Solver '%s' is not available. Falling back to 'glpk'.", solver_to_use
        )
        solver_to_use = "glpk"

    day_indices = list(range(start_day_index, start_day_index + num_days))
    start_date = data_df.iloc[day_indices[0] * time_points_per_day]["Date"].date()
    end_date = data_df.iloc[(day_indices[-1] + 1) * time_points_per_day - 1][
        "Date"
    ].date()

    logger.info("=" * 60)
    logger.info("EsMS Stochastic Optimization (Rolling History Scenarios)")
    logger.info("Date range: %s to %s", start_date, end_date)
    logger.info("Days: %s | History days: %s", num_days, history_days)
    logger.info("Scenarios/day: %s", num_scenarios)
    logger.info("Resolution: %s h (%s points/day)", timestep_hours, time_points_per_day)
    logger.info("Solver: %s", solver_to_use)
    logger.info("=" * 60)

    wandb_run = _init_wandb(config)

    start_time = datetime.datetime.now()
    day_outputs = Parallel(n_jobs=n_jobs)(
        delayed(_solve_single_day)(
            day_idx=day_idx,
            data_df=data_df,
            battery_specs=battery_specs,
            time_points_per_day=time_points_per_day,
            history_days=history_days,
            num_scenarios=num_scenarios,
            pv_coeff=pv_coeff,
            load_coeff=load_coeff,
            random_state=random_state,
            solver=solver_to_use,
            timestep_hours=timestep_hours,
            save_scenario_results=config["save_scenario_results"],
        )
        for day_idx in day_indices
    )

    expected_frames = [result[0] for result in day_outputs]
    expected_results_df = pd.concat(expected_frames, axis=0).sort_index()
    Path(output_expected_file).parent.mkdir(parents=True, exist_ok=True)
    expected_results_df.to_csv(output_expected_file)

    scenario_results_df: pd.DataFrame | None = None
    if config["save_scenario_results"]:
        scenario_frames = [result[1] for result in day_outputs if result[1] is not None]
        scenario_results_df = pd.concat(scenario_frames, axis=0, ignore_index=True)
        if output_scenario_file:
            Path(output_scenario_file).parent.mkdir(parents=True, exist_ok=True)
            scenario_results_df.to_csv(output_scenario_file, index=False)

    elapsed_time = datetime.datetime.now() - start_time
    logger.info("Optimization completed in %s", elapsed_time)
    logger.info(
        "Expected-policy output rows: %s (days: %s)",
        len(expected_results_df),
        len(expected_results_df) // time_points_per_day,
    )
    logger.info("Expected-policy results saved to %s", output_expected_file)
    if config["save_scenario_results"] and output_scenario_file:
        logger.info("Scenario-wise results saved to %s", output_scenario_file)

    calculator = OptimizationCostCalculator(dt_hours=timestep_hours)
    cost_breakdown = calculator.calculate_from_dataframe(
        expected_results_df.reset_index(),
        battery_file=battery_file,
        mode="stochastic_expected",
    )
    logger.info("Final total cost: %.6f EUR", cost_breakdown.total_cost)

    if wandb_run is not None:
        wandb_run.log(
            {
                "final_cost/total": cost_breakdown.total_cost,
                "final_cost/net_energy": cost_breakdown.net_energy_cost,
                "final_cost/import": cost_breakdown.import_cost,
                "final_cost/export_revenue": cost_breakdown.export_revenue,
                "final_cost/degradation": cost_breakdown.degradation_cost,
                "run/elapsed_seconds": elapsed_time.total_seconds(),
                "run/output_expected_rows": len(expected_results_df),
                "run/output_scenario_rows": len(scenario_results_df)
                if scenario_results_df is not None
                else 0,
            }
        )
        wandb_run.finish()


if __name__ == "__main__":
    main()
