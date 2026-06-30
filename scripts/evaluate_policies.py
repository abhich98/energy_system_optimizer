from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from dataclasses import asdict
import numpy as np
import pandas as pd
from tqdm import tqdm

from esms.eval import OptimizationCostCalculator, DeterministicPerformanceCalculator
from esms.utils import build_batteries
from household_battery.policies import PolicySpec, save_champion_local
from household_battery.metrics import DailyMetrics, aggregate_metrics
from household_battery.selection import should_promote, load_rules
from household_battery.backtest import run_expected_schedule, evaluate_expected_schedule


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Evaluate Policies")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate champion and challengers; decide promotion on holdout"
    )
    p.add_argument("--data_file", type=Path, required=True)
    p.add_argument("--battery_file", type=Path, required=True)
    p.add_argument("--year", type=int, default=2025)
    p.add_argument("--holdout_csv", type=Path, required=True)
    p.add_argument(
        "--champion_json", type=Path, default=Path("./artifacts/champion.json")
    )
    p.add_argument(
        "--challengers_json",
        type=Path,
        required=True,
        help="JSON list of PolicySpec dicts",
    )
    p.add_argument(
        "--promotion_config", type=Path, help="YAML file with promotion rules"
    )
    p.add_argument("--out_dir", type=Path, default=Path("./generated/eval"))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    data_df = pd.read_excel(
        args.data_file, sheet_name=f"{args.year} data", usecols="A:F"
    )
    data_df["Date"] = pd.to_datetime(data_df["Date"])
    rename = {
        "PV generation (kW)": "pv",
        "Consumption (kW)": "load",
        "Energy price (EUR/kWh)": "import_price",
    }
    data_df = data_df.rename(columns=rename)

    times = pd.Series(pd.to_datetime(data_df["Date"].unique())).sort_values(
        ignore_index=True
    )
    timestep_hrs = times.diff().dt.total_seconds().mode(dropna=True)[0] / 3600.0
    time_points_per_day = int(round(24.0 / timestep_hrs))

    holdout_days = pd.to_datetime(pd.read_csv(args.holdout_csv)["Date"]).dt.tz_localize(
        None
    )

    with args.battery_file.open("r", encoding="utf-8") as f:
        batteries_specs = json.load(f)
    batteries = build_batteries(batteries_specs)

    # champion
    if args.champion_json.exists():
        logger.info("Loading champion policy from %s", args.champion_json)
        champ_spec = PolicySpec(**json.loads(args.champion_json.read_text()))
    else:
        logger.info(
            "Champion policy file %s does not exist; using default champion spec",
            args.champion_json,
        )
        champ_spec = PolicySpec(id="champion_default", history_days=1, num_scenarios=1, pv_coeff=0.5, load_coeff=0.5, seed=3)

    # challengers
    clist = [PolicySpec(**d) for d in json.loads(args.challengers_json.read_text())]

    # evaluate helper
    def eval_policy(spec: PolicySpec) -> dict:
        logger.info(
            "Evaluating policy '%s' on %d holdout days", spec.id, len(holdout_days)
        )
        rows = []
        for day in tqdm(holdout_days, desc=f"Evaluating {spec.id}", unit="day"):
            try:
                sched, rt = run_expected_schedule(
                    spec, day, data_df, batteries, time_points_per_day
                )
                sched_eval, _ = evaluate_expected_schedule(
                    day, data_df, batteries, sched, time_points_per_day
                ) # evaluate the schedule with actual load and PV for the day

                # Calculate costs and KPIs using project calculators
                cost_calc = OptimizationCostCalculator(dt_hours=timestep_hrs)
                cost = cost_calc.calculate_from_dataframe(
                    sched_eval.reset_index(),
                    battery_file=str(args.battery_file),
                    mode="deterministic",
                )
                perf_calc = DeterministicPerformanceCalculator(dt_hours=timestep_hrs)
                perf = perf_calc.calculate_from_dataframe(sched_eval.reset_index())

                rows.append(
                    DailyMetrics(
                        date=day.strftime("%m/%d/%Y"),
                        total_cost=float(cost.total_cost),
                        net_energy_cost=float(cost.net_energy_cost),
                        degradation_cost=float(cost.degradation_cost),
                        self_consumption=float(perf.self_consumption_ratio),
                        self_sufficiency=float(perf.self_sufficiency_ratio),
                        grid_dependency=float(perf.grid_dependency_ratio),
                        runtime_sec=float(rt),
                        violations=0,
                    ).__dict__
                )
            except Exception as e:
                rows.append(
                    DailyMetrics(
                        date=day.strftime("%m/%d/%Y"),
                        total_cost=np.inf,
                        net_energy_cost=np.inf,
                        degradation_cost=0.0,
                        self_consumption=0.0,
                        self_sufficiency=0.0,
                        grid_dependency=0.0,
                        runtime_sec=1e9,
                        violations=1,
                    ).__dict__
                )
                logger.warning(
                    "Policy '%s' failed for day %s; recorded violation row. Error: %s",
                    spec.id,
                    pd.Timestamp(day).date(),
                    e
                )
        logger.info("Finished policy '%s'", spec.id)
        return {
            "spec": asdict(spec),
            "daily": rows,
            "summary": aggregate_metrics([DailyMetrics(**r) for r in rows]),
        }

    champ_res = eval_policy(champ_spec)
    results = {"champion": champ_res, "challengers": []}

    for spec in clist:
        cres = eval_policy(spec)
        # compute deltas vs champion per day (placeholder: using total_cost)
        df_ch = pd.DataFrame(champ_res["daily"]).set_index("date")
        df_cl = pd.DataFrame(cres["daily"]).set_index("date")
        common = df_ch.join(df_cl, lsuffix="_ch", rsuffix="_cl", how="inner")
        deltas = (common["total_cost_cl"] - common["total_cost_ch"]).to_numpy()
        mean_ch = float(df_ch["total_cost"].mean())
        mean_cl = float(df_cl["total_cost"].mean())
        mean_gain = (
            (mean_ch - mean_cl) / mean_ch
            if np.isfinite(mean_ch) and mean_ch > 0
            else 0.0
        )
        win_rate = float((deltas < 0.0).mean()) if len(deltas) else 0.0

        summary = cres["summary"]
        summary.update(
            {
                "mean_gain": mean_gain,
                "win_rate": win_rate,
                "daily_deltas": deltas.tolist(),
            }
        )
        cres["summary"] = summary
        results["challengers"].append(cres)

    # DECIDE PROMOTION

    rules = load_rules(args.promotion_config)
    promotable = [
        c for c in results["challengers"] if should_promote(c["summary"], rules)
    ]
    results["promoted"] = [c["spec"]["id"] for c in promotable]
    if promotable:
        # pick best by mean_gain
        best = max(promotable, key=lambda c: c["summary"]["mean_gain"])
        save_champion_local(PolicySpec(**best["spec"]), str(args.champion_json))
        logger.info(
            "Promoted new champion policy '%s' with mean_gain %.4f",
            best["spec"]["id"],
            best["summary"]["mean_gain"],
        )
    else:
        logger.info("No challengers met promotion criteria; champion remains '%s'", champ_spec.id)

    # write out
    (out_dir / "evaluation_results.json").write_text(json.dumps(results, indent=2))
    logger.info("Evaluation results written to %s", out_dir / "evaluation_results.json")


if __name__ == "__main__":
    main()
