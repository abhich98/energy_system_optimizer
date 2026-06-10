from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PerformanceBreakdown:
    mode: str
    dt_hours: float
    total_load_kwh: float
    total_pv_generation_kwh: float
    total_grid_import_kwh: float
    total_grid_export_kwh: float
    pv_self_consumed_kwh: float
    load_served_locally_kwh: float
    self_consumption_ratio: float
    self_sufficiency_ratio: float
    grid_dependency_ratio: float
    pv_spillage_kwh: float
    battery_charge_kwh: float
    battery_discharge_kwh: float
    battery_throughput_kwh: float
    estimated_equivalent_cycles: float
    peak_grid_import_kw: float
    peak_grid_export_kw: float
    components: dict[str, float]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "dt_hours": self.dt_hours,
            "total_load_kwh": self.total_load_kwh,
            "total_pv_generation_kwh": self.total_pv_generation_kwh,
            "total_grid_import_kwh": self.total_grid_import_kwh,
            "total_grid_export_kwh": self.total_grid_export_kwh,
            "pv_self_consumed_kwh": self.pv_self_consumed_kwh,
            "load_served_locally_kwh": self.load_served_locally_kwh,
            "self_consumption_ratio": self.self_consumption_ratio,
            "self_sufficiency_ratio": self.self_sufficiency_ratio,
            "grid_dependency_ratio": self.grid_dependency_ratio,
            "pv_spillage_kwh": self.pv_spillage_kwh,
            "battery_charge_kwh": self.battery_charge_kwh,
            "battery_discharge_kwh": self.battery_discharge_kwh,
            "battery_throughput_kwh": self.battery_throughput_kwh,
            "estimated_equivalent_cycles": self.estimated_equivalent_cycles,
            "peak_grid_import_kw": self.peak_grid_import_kw,
            "peak_grid_export_kw": self.peak_grid_export_kw,
            "components": self.components,
            "warnings": self.warnings,
        }


class DeterministicPerformanceCalculator:
    """Compute deterministic performance KPIs from optimization result outputs."""

    def __init__(self, dt_hours: float):
        if dt_hours <= 0:
            raise ValueError("dt_hours must be positive")
        self.dt_hours = float(dt_hours)

    @staticmethod
    def _sum_series(df: pd.DataFrame, col: str) -> float:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in the given DataFrame")
        return float(pd.to_numeric(df[col], errors="coerce").fillna(0.0).sum())

    @staticmethod
    def _safe_ratio(num: float, den: float) -> float:
        if np.isclose(den, 0.0):
            return float("nan")
        return float(num / den)

    @staticmethod
    def _find_battery_columns(df: pd.DataFrame) -> list[str]:
        battery_ids: list[str] = []
        for col in df.columns:
            if not col.endswith("_charge"):
                continue
            candidate = col[: -len("_charge")]
            if candidate in {"grid", "expected_grid", "grid_import", "grid_export"}:
                continue
            discharge_col = f"{candidate}_discharge"
            if discharge_col in df.columns:
                battery_ids.append(candidate)
        return sorted(set(battery_ids))

    def calculate_from_dataframe(
        self, results_df: pd.DataFrame
    ) -> PerformanceBreakdown:
        required_cols = {"pv", "load", "grid_import", "grid_export"}
        missing = [c for c in required_cols if c not in results_df.columns]
        if missing:
            raise ValueError(
                f"Deterministic results are missing required columns: {missing}"
            )

        warnings: list[str] = []

        pv = pd.to_numeric(results_df["pv"], errors="coerce").fillna(0.0)
        load = pd.to_numeric(results_df["load"], errors="coerce").fillna(0.0)
        grid_import = pd.to_numeric(results_df["grid_import"], errors="coerce").fillna(
            0.0
        )
        grid_export = pd.to_numeric(results_df["grid_export"], errors="coerce").fillna(
            0.0
        )

        total_pv_generation_kwh = float(pv.sum() * self.dt_hours)
        total_load_kwh = float(load.sum() * self.dt_hours)
        total_grid_import_kwh = float(grid_import.sum() * self.dt_hours)
        total_grid_export_kwh = float(grid_export.sum() * self.dt_hours)

        pv_self_consumed_power = (pv - grid_export).clip(lower=0.0)
        load_served_locally_power = (load - grid_import).clip(lower=0.0)

        pv_self_consumed_kwh = float(pv_self_consumed_power.sum() * self.dt_hours)
        load_served_locally_kwh = float(load_served_locally_power.sum() * self.dt_hours)

        self_consumption_ratio = self._safe_ratio(
            pv_self_consumed_kwh, total_pv_generation_kwh
        )
        self_sufficiency_ratio = self._safe_ratio(
            load_served_locally_kwh, total_load_kwh
        )
        grid_dependency_ratio = self._safe_ratio(total_grid_import_kwh, total_load_kwh)

        battery_ids = self._find_battery_columns(results_df)
        battery_charge_kwh = 0.0
        battery_discharge_kwh = 0.0
        estimated_equivalent_cycles = 0.0

        if not battery_ids:
            warnings.append(
                "No battery charge/discharge columns found; battery KPIs are set to 0."
            )

        for battery_id in battery_ids:
            charge_col = f"{battery_id}_charge"
            discharge_col = f"{battery_id}_discharge"
            charge_kwh = self._sum_series(results_df, charge_col) * self.dt_hours
            discharge_kwh = self._sum_series(results_df, discharge_col) * self.dt_hours
            battery_charge_kwh += charge_kwh
            battery_discharge_kwh += discharge_kwh

            soc_col = f"{battery_id}_soc"
            if soc_col in results_df.columns:
                soc = pd.to_numeric(results_df[soc_col], errors="coerce").fillna(0.0)
                observed_usable_kwh = float((soc.max() - soc.min()))
                if observed_usable_kwh > 0:
                    estimated_equivalent_cycles += (charge_kwh + discharge_kwh) / (
                        2.0 * observed_usable_kwh
                    )
                else:
                    warnings.append(
                        f"Could not estimate cycles for {battery_id}: SOC range is zero."
                    )
            else:
                warnings.append(
                    f"Column '{soc_col}' not found; cycles for {battery_id} not estimated."
                )

        battery_throughput_kwh = battery_charge_kwh + battery_discharge_kwh

        total_charge_power = np.zeros(len(results_df), dtype=float)
        for battery_id in battery_ids:
            total_charge_power += (
                pd.to_numeric(results_df[f"{battery_id}_charge"], errors="coerce")
                .fillna(0.0)
                .to_numpy(dtype=float)
            )

        pv_spillage_power = (
            pv.to_numpy(dtype=float)
            - load.to_numpy(dtype=float)
            - total_charge_power
            - grid_export.to_numpy(dtype=float)
        ).clip(min=0.0)
        pv_spillage_kwh = float(np.sum(pv_spillage_power) * self.dt_hours)

        peak_grid_import_kw = float(grid_import.max())
        peak_grid_export_kw = float(grid_export.max())

        components = {
            "total_load_kwh": total_load_kwh,
            "total_pv_generation_kwh": total_pv_generation_kwh,
            "total_grid_import_kwh": total_grid_import_kwh,
            "total_grid_export_kwh": total_grid_export_kwh,
            "pv_self_consumed_kwh": pv_self_consumed_kwh,
            "load_served_locally_kwh": load_served_locally_kwh,
            "pv_spillage_kwh": pv_spillage_kwh,
            "battery_charge_kwh": battery_charge_kwh,
            "battery_discharge_kwh": battery_discharge_kwh,
            "battery_throughput_kwh": battery_throughput_kwh,
            "estimated_equivalent_cycles": estimated_equivalent_cycles,
            "peak_grid_import_kw": peak_grid_import_kw,
            "peak_grid_export_kw": peak_grid_export_kw,
        }

        return PerformanceBreakdown(
            mode="deterministic",
            dt_hours=self.dt_hours,
            total_load_kwh=total_load_kwh,
            total_pv_generation_kwh=total_pv_generation_kwh,
            total_grid_import_kwh=total_grid_import_kwh,
            total_grid_export_kwh=total_grid_export_kwh,
            pv_self_consumed_kwh=pv_self_consumed_kwh,
            load_served_locally_kwh=load_served_locally_kwh,
            self_consumption_ratio=self_consumption_ratio,
            self_sufficiency_ratio=self_sufficiency_ratio,
            grid_dependency_ratio=grid_dependency_ratio,
            pv_spillage_kwh=pv_spillage_kwh,
            battery_charge_kwh=battery_charge_kwh,
            battery_discharge_kwh=battery_discharge_kwh,
            battery_throughput_kwh=battery_throughput_kwh,
            estimated_equivalent_cycles=estimated_equivalent_cycles,
            peak_grid_import_kw=peak_grid_import_kw,
            peak_grid_export_kw=peak_grid_export_kw,
            components=components,
            warnings=warnings,
        )

    def calculate_from_file(
        self, optimization_result_file: str | Path
    ) -> PerformanceBreakdown:
        df = pd.read_csv(optimization_result_file)
        return self.calculate_from_dataframe(df)


def calculate_deterministic_performance(
    optimization_result_file: str | Path,
    dt_hours: float,
) -> dict[str, Any]:
    """Convenience function returning deterministic performance metrics as dictionary."""
    calculator = DeterministicPerformanceCalculator(dt_hours=dt_hours)
    return calculator.calculate_from_file(optimization_result_file).to_dict()
