from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pandas as pd


@dataclass(frozen=True)
class CostBreakdown:
    mode: str
    dt_hours: float
    import_cost: float
    export_revenue: float
    net_energy_cost: float
    degradation_cost: float
    total_cost: float
    components: dict[str, float]
    battery_degradation: dict[str, float]
    warnings: list[str]
    scenario_costs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "dt_hours": self.dt_hours,
            "import_cost": self.import_cost,
            "export_revenue": self.export_revenue,
            "net_energy_cost": self.net_energy_cost,
            "degradation_cost": self.degradation_cost,
            "total_cost": self.total_cost,
            "components": self.components,
            "battery_degradation": self.battery_degradation,
            "warnings": self.warnings,
            "scenario_costs": self.scenario_costs,
        }


class OptimizationCostCalculator:
    """Calculate deterministic/stochastic optimization costs from output CSV + battery JSON."""

    def __init__(self, dt_hours: float):
        if dt_hours <= 0:
            raise ValueError("dt_hours must be positive")
        self.dt_hours = float(dt_hours)

    @staticmethod
    def _load_battery_degradation_map(battery_file: str | Path) -> dict[str, float]:
        with Path(battery_file).open("r", encoding="utf-8") as f:
            batteries = json.load(f)

        if not isinstance(batteries, list) or len(batteries) == 0:
            raise ValueError("battery_file must contain a non-empty JSON list")

        mapping: dict[str, float] = {}
        for battery in batteries:
            battery_id = str(battery["id"])
            mapping[battery_id] = float(battery.get("degradation_cost", 0.0))
        return mapping

    @staticmethod
    def _sum_series(df: pd.DataFrame, col: str) -> float:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in the given DataFrame")
        return float(pd.to_numeric(df[col], errors="coerce").fillna(0.0).sum())

    @DeprecationWarning
    @staticmethod
    def _resolve_first_existing(df: pd.DataFrame, candidates: list[str]) -> str | None:
        for c in candidates:
            if c in df.columns:
                return c
        raise ValueError(
            f"None of the candidate columns {candidates} found in DataFrame"
        )

    @DeprecationWarning
    @staticmethod
    def _detect_mode(df: pd.DataFrame) -> str:
        cols = set(df.columns)

        if {"scenario", "probability", "grid_import_rt", "grid_export_rt"}.issubset(
            cols
        ):
            return "stochastic_scenario"

        if {
            "grid_import_ahead",
            "grid_export_ahead",
            "expected_grid_import_rt",
            "expected_grid_export_rt",
        }.issubset(cols):
            return "stochastic_expected"

        if {"grid_import", "grid_export"}.issubset(cols):
            return "deterministic"

        raise ValueError("Could not detect optimization result format from columns")

    def _deterministic_breakdown(
        self,
        df: pd.DataFrame,
        degradation_costs: dict[str, float],
    ) -> CostBreakdown:
        warnings: list[str] = []

        for col in ["import_price", "export_price"]:
            if col not in df.columns:
                raise ValueError(f"Deterministic cost calculation needs '{col}' column")

        import_cost = float(
            (
                pd.to_numeric(df["import_price"], errors="coerce").fillna(0.0)
                * pd.to_numeric(df["grid_import"], errors="coerce").fillna(0.0)
            ).sum()
            * self.dt_hours
        )
        export_revenue = float(
            (
                pd.to_numeric(df["export_price"], errors="coerce").fillna(0.0)
                * pd.to_numeric(df["grid_export"], errors="coerce").fillna(0.0)
            ).sum()
            * self.dt_hours
        )

        battery_deg: dict[str, float] = {}
        for battery_id, deg_cost in degradation_costs.items():
            charge_col = f"{battery_id}_charge"
            discharge_col = f"{battery_id}_discharge"

            if charge_col not in df.columns or discharge_col not in df.columns:
                warnings.append(
                    f"Missing '{charge_col}'/'{discharge_col}'; degradation for {battery_id} set to 0."
                )
                battery_deg[battery_id] = 0.0
                continue

            throughput_sum = self._sum_series(df, charge_col) + self._sum_series(
                df, discharge_col
            )
            battery_deg[battery_id] = deg_cost * throughput_sum * self.dt_hours

        degradation_cost = float(sum(battery_deg.values()))
        net_energy_cost = import_cost - export_revenue
        total_cost = net_energy_cost + degradation_cost

        return CostBreakdown(
            mode="deterministic",
            dt_hours=self.dt_hours,
            import_cost=import_cost,
            export_revenue=export_revenue,
            net_energy_cost=net_energy_cost,
            degradation_cost=degradation_cost,
            total_cost=total_cost,
            components={
                "energy_import": import_cost,
                "energy_export_revenue": export_revenue,
                "degradation": degradation_cost,
            },
            battery_degradation=battery_deg,
            warnings=warnings,
            scenario_costs=[],
        )

    def _stochastic_expected_breakdown(
        self,
        df: pd.DataFrame,
        degradation_costs: dict[str, float],
    ) -> CostBreakdown:
        warnings: list[str] = []

        for col in [
            "import_price_ahead",
            "export_price_ahead",
            "expected_import_price_rt",
            "expected_export_price_rt",
        ]:
            if col not in df.columns:
                raise ValueError(
                    f"Stochastic expected cost calculation needs '{col}' column"
                )

        import_ahead_cost = float(
            (
                pd.to_numeric(df["import_price_ahead"], errors="coerce").fillna(0.0)
                * pd.to_numeric(df["grid_import_ahead"], errors="coerce").fillna(0.0)
            ).sum()
            * self.dt_hours
        )
        import_rt_cost = float(
            (
                pd.to_numeric(df["expected_import_price_rt"], errors="coerce").fillna(
                    0.0
                )
                * pd.to_numeric(df["expected_grid_import_rt"], errors="coerce").fillna(
                    0.0
                )
            ).sum()
            * self.dt_hours
        )

        export_ahead_revenue = float(
            (
                pd.to_numeric(df["export_price_ahead"], errors="coerce").fillna(0.0)
                * pd.to_numeric(df["grid_export_ahead"], errors="coerce").fillna(0.0)
            ).sum()
            * self.dt_hours
        )

        export_rt_revenue = float(
            (
                pd.to_numeric(df["expected_export_price_rt"], errors="coerce").fillna(
                    0.0
                )
                * pd.to_numeric(df["expected_grid_export_rt"], errors="coerce").fillna(
                    0.0
                )
            ).sum()
            * self.dt_hours
        )

        battery_deg: dict[str, float] = {}
        for battery_id, deg_cost in degradation_costs.items():

            charge_col, discharge_col = (
                f"expected_{battery_id}_charge",
                f"expected_{battery_id}_discharge",
            )
            throughput_sum = self._sum_series(df, charge_col) + self._sum_series(
                df, discharge_col
            )
            battery_deg[battery_id] = deg_cost * throughput_sum * self.dt_hours

        degradation_cost = float(sum(battery_deg.values()))
        import_cost = import_ahead_cost + import_rt_cost
        export_revenue = export_ahead_revenue + export_rt_revenue
        net_energy_cost = import_cost - export_revenue
        total_cost = net_energy_cost + degradation_cost

        return CostBreakdown(
            mode="stochastic_expected",
            dt_hours=self.dt_hours,
            import_cost=import_cost,
            export_revenue=export_revenue,
            net_energy_cost=net_energy_cost,
            degradation_cost=degradation_cost,
            total_cost=total_cost,
            components={
                "ahead_import": import_ahead_cost,
                "rt_import_expected": import_rt_cost,
                "ahead_export_revenue": export_ahead_revenue,
                "rt_export_revenue_expected": export_rt_revenue,
                "degradation": degradation_cost,
            },
            battery_degradation=battery_deg,
            warnings=warnings,
            scenario_costs=[],
        )

    def _stochastic_scenario_breakdown(
        self,
        df: pd.DataFrame,
        degradation_costs: dict[str, float],
    ) -> CostBreakdown:
        """TODO: This method is not yet completley and does not consdier multiple days in the given dataframe properly."""
        warnings: list[str] = []

        required_cols = [
            "scenario",
            "probability",
            "import_price_ahead",
            "export_price_ahead",
            "import_price_rt",
            "export_price_rt",
            "grid_import_ahead",
            "grid_export_ahead",
            "grid_import_rt",
            "grid_export_rt",
        ]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Scenario-mode cost calculation needs '{col}' column")

        scenario_costs: list[dict[str, Any]] = []
        expected_battery_deg: dict[str, float] = {
            battery_id: 0.0 for battery_id in degradation_costs.keys()
        }

        expected_import_cost = 0.0
        expected_export_revenue = 0.0
        expected_degradation_cost = 0.0
        expected_import_ahead_cost = 0.0
        expected_import_rt_cost = 0.0
        expected_export_ahead_revenue = 0.0
        expected_export_rt_revenue = 0.0

        for scenario_id, scenario_df in df.groupby("scenario", sort=True):
            scenario_prob = float(
                pd.to_numeric(scenario_df["probability"], errors="coerce")
                .fillna(0.0)
                .iloc[0]
            )

            import_ahead_cost = float(
                (
                    pd.to_numeric(
                        scenario_df["import_price_ahead"], errors="coerce"
                    ).fillna(0.0)
                    * pd.to_numeric(
                        scenario_df["grid_import_ahead"], errors="coerce"
                    ).fillna(0.0)
                ).sum()
                * self.dt_hours
            )
            import_rt_cost = float(
                (
                    pd.to_numeric(
                        scenario_df["import_price_rt"], errors="coerce"
                    ).fillna(0.0)
                    * pd.to_numeric(
                        scenario_df["grid_import_rt"], errors="coerce"
                    ).fillna(0.0)
                ).sum()
                * self.dt_hours
            )

            export_ahead_revenue = float(
                (
                    pd.to_numeric(
                        scenario_df["export_price_ahead"], errors="coerce"
                    ).fillna(0.0)
                    * pd.to_numeric(
                        scenario_df["grid_export_ahead"], errors="coerce"
                    ).fillna(0.0)
                ).sum()
                * self.dt_hours
            )
            export_rt_revenue = float(
                (
                    pd.to_numeric(
                        scenario_df["export_price_rt"], errors="coerce"
                    ).fillna(0.0)
                    * pd.to_numeric(
                        scenario_df["grid_export_rt"], errors="coerce"
                    ).fillna(0.0)
                ).sum()
                * self.dt_hours
            )

            scenario_battery_deg: dict[str, float] = {}
            for battery_id, deg_cost in degradation_costs.items():
                charge_col, discharge_col = (
                    f"{battery_id}_charge",
                    f"{battery_id}_discharge",
                )
                if (
                    charge_col not in scenario_df.columns
                    or discharge_col not in scenario_df.columns
                ):
                    warnings.append(
                        f"Missing '{charge_col}'/'{discharge_col}' for scenario {scenario_id}; degradation for {battery_id} set to 0."
                    )
                    scenario_battery_deg[battery_id] = 0.0
                    continue
                throughput_sum = self._sum_series(
                    scenario_df, charge_col
                ) + self._sum_series(scenario_df, discharge_col)
                scenario_battery_deg[battery_id] = (
                    deg_cost * throughput_sum * self.dt_hours
                )

            scenario_degradation_cost = float(sum(scenario_battery_deg.values()))
            scenario_import_cost = import_ahead_cost + import_rt_cost
            scenario_export_revenue = export_ahead_revenue + export_rt_revenue
            scenario_net_energy_cost = scenario_import_cost - scenario_export_revenue
            scenario_total_cost = scenario_net_energy_cost + scenario_degradation_cost

            scenario_costs.append(
                {
                    "scenario": int(scenario_id),
                    "probability": scenario_prob,
                    "import_cost": scenario_import_cost,
                    "export_revenue": scenario_export_revenue,
                    "net_energy_cost": scenario_net_energy_cost,
                    "degradation_cost": scenario_degradation_cost,
                    "total_cost": scenario_total_cost,
                    "battery_degradation": scenario_battery_deg,
                    "components": {
                        "ahead_import": import_ahead_cost,
                        "rt_import": import_rt_cost,
                        "ahead_export_revenue": export_ahead_revenue,
                        "rt_export_revenue": export_rt_revenue,
                    },
                }
            )

            expected_import_cost += scenario_prob * scenario_import_cost
            expected_export_revenue += scenario_prob * scenario_export_revenue
            expected_degradation_cost += scenario_prob * scenario_degradation_cost
            expected_import_ahead_cost += scenario_prob * import_ahead_cost
            expected_import_rt_cost += scenario_prob * import_rt_cost
            expected_export_ahead_revenue += scenario_prob * export_ahead_revenue
            expected_export_rt_revenue += scenario_prob * export_rt_revenue
            for battery_id in expected_battery_deg:
                expected_battery_deg[
                    battery_id
                ] += scenario_prob * scenario_battery_deg.get(battery_id, 0.0)

        import_cost = float(expected_import_cost)
        export_revenue = float(expected_export_revenue)
        degradation_cost = float(expected_degradation_cost)
        net_energy_cost = import_cost - export_revenue
        total_cost = net_energy_cost + degradation_cost

        return CostBreakdown(
            mode="stochastic_scenarios",
            dt_hours=self.dt_hours,
            import_cost=import_cost,
            export_revenue=export_revenue,
            net_energy_cost=net_energy_cost,
            degradation_cost=degradation_cost,
            total_cost=total_cost,
            components={
                "ahead_import_expected": float(expected_import_ahead_cost),
                "rt_import_expected": float(expected_import_rt_cost),
                "ahead_export_revenue_expected": float(expected_export_ahead_revenue),
                "rt_export_revenue_expected": float(expected_export_rt_revenue),
                "degradation_expected": degradation_cost,
            },
            battery_degradation=expected_battery_deg,
            warnings=warnings,
            scenario_costs=scenario_costs,
        )

    def calculate_from_dataframe(
        self,
        results_df: pd.DataFrame,
        battery_file: str | Path,
        mode: str = "deterministic",
    ) -> CostBreakdown:
        if results_df.empty:
            raise ValueError("results_df is empty")

        degradation_map = self._load_battery_degradation_map(battery_file)

        match mode:
            case "deterministic":
                return self._deterministic_breakdown(results_df, degradation_map)
            case "stochastic_expected":
                return self._stochastic_expected_breakdown(results_df, degradation_map)
            case "stochastic_scenarios":
                return self._stochastic_scenario_breakdown(results_df, degradation_map)
            case _:
                raise ValueError(
                    f"Unsupported mode '{mode}'. Supported modes: deterministic, stochastic_expected, stochastic_scenarios."
                )

    def calculate_periodic_deterministic_costs(
        self,
        results_df: pd.DataFrame,
        battery_file: str | Path | None = None,
        period: Literal["day", "month"] = "day",
        datetime_col: str = "Date",
    ) -> pd.DataFrame:
        if results_df.empty:
            raise ValueError("results_df is empty")

        if period not in {"day", "month"}:
            raise ValueError("period must be either 'day' or 'month'")

        # Grid costs and revenue
        required_cols = ["import_price", "export_price", "grid_import", "grid_export"]
        missing_cols = [col for col in required_cols if col not in results_df.columns]
        if missing_cols:
            raise ValueError(
                "Deterministic periodic cost calculation needs columns: "
                f"{required_cols}. Missing: {missing_cols}"
            )

        if datetime_col in results_df.columns:
            timestamps = pd.to_datetime(results_df[datetime_col], errors="coerce")
        else:
            raise ValueError(
                f"datetime_col '{datetime_col}' not found and DataFrame index is not a DatetimeIndex"
            )

        if timestamps.isna().any():
            raise ValueError("Datetime conversion failed for one or more rows")

        work_df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "import_cost": (
                    pd.to_numeric(results_df["import_price"], errors="coerce").fillna(0.0)
                    * pd.to_numeric(results_df["grid_import"], errors="coerce").fillna(0.0)
                    * self.dt_hours
                ),
                "export_revenue": (
                    pd.to_numeric(results_df["export_price"], errors="coerce").fillna(0.0)
                    * pd.to_numeric(results_df["grid_export"], errors="coerce").fillna(0.0)
                    * self.dt_hours
                ),
            }
        )
        work_df["net_energy_cost"] = work_df["import_cost"] - work_df["export_revenue"]
        work_df["total_cost"] = work_df["net_energy_cost"]

        # Battery degradation costs
        if battery_file is not None:
            degradation_costs = self._load_battery_degradation_map(battery_file)
            battery_cols = []
            for battery_id, deg_cost in degradation_costs.items():
                charge_col = f"{battery_id}_charge"
                discharge_col = f"{battery_id}_discharge"

                if charge_col not in results_df.columns or discharge_col not in results_df.columns:
                    raise ValueError(
                        f"Missing '{charge_col}'/'{discharge_col}'; degradation for {battery_id} set to 0."
                    )

                work_df[f"{battery_id}_cost"] = (
                    pd.to_numeric(results_df[charge_col], errors="coerce").fillna(0.0)
                    + pd.to_numeric(results_df[discharge_col], errors="coerce").fillna(0.0)
                ) * deg_cost * self.dt_hours

                work_df["total_cost"] += work_df[f"{battery_id}_cost"]
                battery_cols.append(f"{battery_id}_cost")

        if period == "day":
            work_df["period_start"] = work_df["timestamp"].dt.floor("D")
        else:
            work_df["period_start"] = work_df["timestamp"].dt.to_period("M").dt.to_timestamp()

        return (
            work_df.groupby("period_start", as_index=False)[
                ["import_cost", "export_revenue", "net_energy_cost", "total_cost"] + battery_cols
            ]
            .sum()
            .sort_values("period_start")
            .reset_index(drop=True)
        )

    def calculate_from_files(
        self,
        optimization_result_file: str | Path,
        battery_file: str | Path,
        mode: str = "deterministic",
    ) -> CostBreakdown:
        df = pd.read_csv(optimization_result_file)
        return self.calculate_from_dataframe(df, battery_file=battery_file, mode=mode)


def calculate_final_cost(
    optimization_result_file: str | Path,
    battery_file: str | Path,
    dt_hours: float,
    mode: str = "auto",
) -> dict[str, Any]:
    """Convenience function returning a dictionary cost breakdown."""
    calculator = OptimizationCostCalculator(dt_hours=dt_hours)
    return calculator.calculate_from_files(
        optimization_result_file=optimization_result_file,
        battery_file=battery_file,
        mode=mode,
    ).to_dict()
