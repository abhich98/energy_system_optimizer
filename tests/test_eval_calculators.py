"""Tests for deterministic cost and performance calculation methods.

Tests cover:
- DeterministicPerformanceCalculator (performance_calculation.py)
- OptimizationCostCalculator deterministic mode (cost_calculation.py)

Test data is modeled after resources/api/dayahead_deterministic_schedule.csv
with columns: Date, pv, load, import_price, export_price, grid_import,
grid_export, battery_1_charge, battery_1_discharge, battery_1_soc.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from esms.eval.cost_calculation import OptimizationCostCalculator
from esms.eval.performance_calculation import DeterministicPerformanceCalculator

ROOT = Path(__file__).resolve().parents[1]
BATTERIES_PATH = ROOT / "config" / "sonnenBatterie10.json"
SCHEDULE_CSV = ROOT / "resources" / "api" / "dayahead_deterministic_schedule.csv"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def batteries() -> list[dict]:
    with BATTERIES_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def degradation_costs(batteries: list[dict]) -> dict[str, float]:
    return {str(b["id"]): float(b.get("degradation_cost", 0.0)) for b in batteries}


@pytest.fixture
def dt_hours() -> float:
    """15-minute timestep from the reference CSV."""
    return 0.25


@pytest.fixture
def small_schedule_df() -> pd.DataFrame:
    """A compact 4-row schedule modeled after the real CSV schema."""
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(
                [
                    "2025-04-24 00:00:00",
                    "2025-04-24 00:15:00",
                    "2025-04-24 00:30:00",
                    "2025-04-24 00:45:00",
                ]
            ),
            "pv": [0.0, 0.0, 2.0, 3.0],
            "load": [1.0, 0.8, 0.5, 1.0],
            "import_price": [0.30, 0.30, 0.35, 0.35],
            "export_price": [0.0, 0.0, 0.05, 0.05],
            "grid_import": [1.0, 0.8, 0.0, 0.0],
            "grid_export": [0.0, 0.0, 0.5, 1.0],
            "battery_1_charge": [0.0, 0.0, 1.0, 2.0],
            "battery_1_discharge": [0.0, 0.0, 0.0, 0.0],
            "battery_1_soc": [1.0, 1.0, 2.0, 4.0],
        }
    )


@pytest.fixture
def real_schedule_df() -> pd.DataFrame:
    """Load the actual reference CSV if available."""
    if not SCHEDULE_CSV.exists():
        pytest.skip(f"Reference CSV not found at {SCHEDULE_CSV}")
    return pd.read_csv(SCHEDULE_CSV)


# ---------------------------------------------------------------------------
# Performance calculation tests
# ---------------------------------------------------------------------------


class TestDeterministicPerformanceCalculator:
    """Tests for DeterministicPerformanceCalculator."""

    def test_total_load_kwh(self, small_schedule_df: pd.DataFrame, dt_hours: float):
        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(small_schedule_df)

        expected_load = float(small_schedule_df["load"].sum() * dt_hours)
        assert math.isclose(result.total_load_kwh, expected_load)

    def test_total_pv_generation_kwh(
        self, small_schedule_df: pd.DataFrame, dt_hours: float
    ):
        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(small_schedule_df)

        expected_pv = float(small_schedule_df["pv"].sum() * dt_hours)
        assert math.isclose(result.total_pv_generation_kwh, expected_pv)

    def test_grid_import_export_kwh(
        self, small_schedule_df: pd.DataFrame, dt_hours: float
    ):
        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(small_schedule_df)

        expected_import = float(small_schedule_df["grid_import"].sum() * dt_hours)
        expected_export = float(small_schedule_df["grid_export"].sum() * dt_hours)
        assert math.isclose(result.total_grid_import_kwh, expected_import)
        assert math.isclose(result.total_grid_export_kwh, expected_export)

    def test_self_consumption_ratio(
        self, small_schedule_df: pd.DataFrame, dt_hours: float
    ):
        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(small_schedule_df)

        pv = small_schedule_df["pv"]
        grid_export = small_schedule_df["grid_export"]
        pv_self_consumed = float((pv - grid_export).clip(lower=0.0).sum() * dt_hours)
        pv_total = float(pv.sum() * dt_hours)
        expected_ratio = pv_self_consumed / pv_total if pv_total > 0 else float("nan")

        assert math.isclose(result.self_consumption_ratio, expected_ratio)

    def test_self_sufficiency_ratio(
        self, small_schedule_df: pd.DataFrame, dt_hours: float
    ):
        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(small_schedule_df)

        load = small_schedule_df["load"]
        grid_import = small_schedule_df["grid_import"]
        load_served_locally = float(
            (load - grid_import).clip(lower=0.0).sum() * dt_hours
        )
        total_load = float(load.sum() * dt_hours)
        expected = load_served_locally / total_load if total_load > 0 else float("nan")

        assert math.isclose(result.self_sufficiency_ratio, expected)

    def test_battery_throughput(
        self, small_schedule_df: pd.DataFrame, dt_hours: float
    ):
        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(small_schedule_df)

        charge = float(small_schedule_df["battery_1_charge"].sum() * dt_hours)
        discharge = float(small_schedule_df["battery_1_discharge"].sum() * dt_hours)
        expected_throughput = charge + discharge

        assert math.isclose(result.battery_charge_kwh, charge)
        assert math.isclose(result.battery_discharge_kwh, discharge)
        assert math.isclose(result.battery_throughput_kwh, expected_throughput)

    def test_peak_grid_import_kw(
        self, small_schedule_df: pd.DataFrame, dt_hours: float
    ):
        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(small_schedule_df)

        assert math.isclose(result.peak_grid_import_kw, float(small_schedule_df["grid_import"].max()))
        assert math.isclose(result.peak_grid_export_kw, float(small_schedule_df["grid_export"].max()))

    def test_pv_spillage_kwh(self, small_schedule_df: pd.DataFrame, dt_hours: float):
        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(small_schedule_df)

        pv = small_schedule_df["pv"].to_numpy(dtype=float)
        load = small_schedule_df["load"].to_numpy(dtype=float)
        charge = small_schedule_df["battery_1_charge"].to_numpy(dtype=float)
        grid_export = small_schedule_df["grid_export"].to_numpy(dtype=float)
        spillage_power = (pv - load - charge - grid_export).clip(min=0.0)
        expected_spillage = float(np.sum(spillage_power) * dt_hours)

        assert math.isclose(result.pv_spillage_kwh, expected_spillage)

    def test_estimated_equivalent_cycles(
        self, small_schedule_df: pd.DataFrame, dt_hours: float
    ):
        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(small_schedule_df)

        charge_kwh = float(small_schedule_df["battery_1_charge"].sum() * dt_hours)
        discharge_kwh = float(small_schedule_df["battery_1_discharge"].sum() * dt_hours)
        soc = small_schedule_df["battery_1_soc"]
        usable = float(soc.max() - soc.min())
        expected_cycles = (charge_kwh + discharge_kwh) / (2.0 * usable) if usable > 0 else 0.0

        assert math.isclose(result.estimated_equivalent_cycles, expected_cycles)

    def test_to_dict_roundtrip(
        self, small_schedule_df: pd.DataFrame, dt_hours: float
    ):
        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(small_schedule_df)
        d = result.to_dict()

        assert d["mode"] == "deterministic"
        assert d["dt_hours"] == dt_hours
        assert "total_load_kwh" in d
        assert "components" in d
        assert isinstance(d["warnings"], list)

    def test_invalid_dt_hours_raises(self):
        with pytest.raises(ValueError, match="dt_hours must be positive"):
            DeterministicPerformanceCalculator(dt_hours=0.0)

    def test_missing_required_columns_raises(self, dt_hours: float):
        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        bad_df = pd.DataFrame({"pv": [1.0], "load": [1.0]})
        with pytest.raises(ValueError, match="missing required columns"):
            calc.calculate_from_dataframe(bad_df)

    def test_calculate_from_file(
        self, small_schedule_df: pd.DataFrame, dt_hours: float, tmp_path: Path
    ):
        csv_path = tmp_path / "schedule.csv"
        small_schedule_df.to_csv(csv_path, index=False)

        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_file(csv_path)

        assert result.mode == "deterministic"
        assert result.dt_hours == dt_hours

    def test_real_csv_loads_and_computes(
        self, real_schedule_df: pd.DataFrame, dt_hours: float
    ):
        calc = DeterministicPerformanceCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(real_schedule_df)

        assert result.total_load_kwh > 0
        assert result.total_pv_generation_kwh > 0
        assert result.battery_throughput_kwh >= 0
        assert result.peak_grid_import_kw >= 0


# ---------------------------------------------------------------------------
# Cost calculation tests
# ---------------------------------------------------------------------------


class TestOptimizationCostCalculator:
    """Tests for OptimizationCostCalculator in deterministic mode."""

    def test_deterministic_import_cost(
        self,
        small_schedule_df: pd.DataFrame,
        dt_hours: float,
        degradation_costs: dict[str, float],
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(
            small_schedule_df,
            degradation_costs=degradation_costs,
            mode="deterministic",
        )

        expected_import = float(
            (
                small_schedule_df["import_price"] * small_schedule_df["grid_import"]
            ).sum()
            * dt_hours
        )
        assert math.isclose(result.import_cost, expected_import)

    def test_deterministic_export_revenue(
        self,
        small_schedule_df: pd.DataFrame,
        dt_hours: float,
        degradation_costs: dict[str, float],
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(
            small_schedule_df,
            degradation_costs=degradation_costs,
            mode="deterministic",
        )

        expected_export = float(
            (
                small_schedule_df["export_price"] * small_schedule_df["grid_export"]
            ).sum()
            * dt_hours
        )
        assert math.isclose(result.export_revenue, expected_export)

    def test_deterministic_net_energy_cost(
        self,
        small_schedule_df: pd.DataFrame,
        dt_hours: float,
        degradation_costs: dict[str, float],
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(
            small_schedule_df,
            degradation_costs=degradation_costs,
            mode="deterministic",
        )

        expected_net = result.import_cost - result.export_revenue
        assert math.isclose(result.net_energy_cost, expected_net)

    def test_deterministic_degradation_cost(
        self,
        small_schedule_df: pd.DataFrame,
        dt_hours: float,
        degradation_costs: dict[str, float],
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(
            small_schedule_df,
            degradation_costs=degradation_costs,
            mode="deterministic",
        )

        deg_rate = degradation_costs["battery_1"]
        charge = float(small_schedule_df["battery_1_charge"].sum())
        discharge = float(small_schedule_df["battery_1_discharge"].sum())
        expected_deg = deg_rate * (charge + discharge) * dt_hours

        assert math.isclose(result.degradation_cost, expected_deg)
        assert "battery_1" in result.battery_degradation

    def test_deterministic_total_cost(
        self,
        small_schedule_df: pd.DataFrame,
        dt_hours: float,
        degradation_costs: dict[str, float],
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(
            small_schedule_df,
            degradation_costs=degradation_costs,
            mode="deterministic",
        )

        expected_total = result.net_energy_cost + result.degradation_cost
        assert math.isclose(result.total_cost, expected_total)

    def test_deterministic_mode_label(
        self,
        small_schedule_df: pd.DataFrame,
        dt_hours: float,
        degradation_costs: dict[str, float],
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(
            small_schedule_df,
            degradation_costs=degradation_costs,
            mode="deterministic",
        )
        assert result.mode == "deterministic"

    def test_to_dict_contains_all_keys(
        self,
        small_schedule_df: pd.DataFrame,
        dt_hours: float,
        degradation_costs: dict[str, float],
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_dataframe(
            small_schedule_df,
            degradation_costs=degradation_costs,
            mode="deterministic",
        )
        d = result.to_dict()

        expected_keys = {
            "mode",
            "dt_hours",
            "import_cost",
            "export_revenue",
            "net_energy_cost",
            "degradation_cost",
            "total_cost",
            "components",
            "battery_degradation",
            "warnings",
            "scenario_costs",
        }
        assert expected_keys.issubset(d.keys())

    def test_calculate_from_files(
        self,
        small_schedule_df: pd.DataFrame,
        dt_hours: float,
        tmp_path: Path,
    ):
        csv_path = tmp_path / "schedule.csv"
        small_schedule_df.to_csv(csv_path, index=False)

        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_files(
            optimization_result_file=csv_path,
            battery_file=BATTERIES_PATH,
            mode="deterministic",
        )

        assert result.mode == "deterministic"
        assert result.total_cost >= 0

    def test_invalid_dt_hours_raises(self):
        with pytest.raises(ValueError, match="dt_hours must be positive"):
            OptimizationCostCalculator(dt_hours=-1.0)

    def test_empty_dataframe_raises(self, dt_hours: float, degradation_costs: dict[str, float]):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        with pytest.raises(ValueError, match="results_df is empty"):
            calc.calculate_from_dataframe(
                pd.DataFrame(),
                degradation_costs=degradation_costs,
                mode="deterministic",
            )

    def test_missing_degradation_source_raises(
        self, small_schedule_df: pd.DataFrame, dt_hours: float
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        with pytest.raises(ValueError, match="Either battery_file or degradation_costs"):
            calc.calculate_from_dataframe(
                small_schedule_df,
                battery_file=None,
                degradation_costs=None,
                mode="deterministic",
            )

    def test_missing_price_column_raises(
        self, small_schedule_df: pd.DataFrame, dt_hours: float, degradation_costs: dict[str, float]
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        bad_df = small_schedule_df.drop(columns=["import_price"])
        with pytest.raises(ValueError, match="import_price"):
            calc.calculate_from_dataframe(
                bad_df,
                degradation_costs=degradation_costs,
                mode="deterministic",
            )

    def test_unsupported_mode_raises(
        self, small_schedule_df: pd.DataFrame, dt_hours: float, degradation_costs: dict[str, float]
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        with pytest.raises(ValueError, match="Unsupported mode"):
            calc.calculate_from_dataframe(
                small_schedule_df,
                degradation_costs=degradation_costs,
                mode="invalid_mode",
            )

    def test_real_csv_loads_and_computes(
        self,
        real_schedule_df: pd.DataFrame,
        dt_hours: float,
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        result = calc.calculate_from_files(
            optimization_result_file=SCHEDULE_CSV,
            battery_file=BATTERIES_PATH,
            mode="deterministic",
        )

        assert result.mode == "deterministic"
        assert result.import_cost > 0
        assert result.total_cost > 0
        assert "battery_1" in result.battery_degradation


# ---------------------------------------------------------------------------
# Periodic cost tests
# ---------------------------------------------------------------------------


class TestPeriodicDeterministicCosts:
    """Tests for calculate_periodic_deterministic_costs."""

    def test_daily_periodic_costs(
        self,
        small_schedule_df: pd.DataFrame,
        dt_hours: float,
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        result = calc.calculate_periodic_deterministic_costs(
            small_schedule_df,
            battery_file=BATTERIES_PATH,
            period="day",
        )

        assert len(result) >= 1
        assert "total_cost" in result.columns
        assert "import_cost" in result.columns
        assert "export_revenue" in result.columns

    def test_monthly_periodic_costs(
        self,
        small_schedule_df: pd.DataFrame,
        dt_hours: float,
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        result = calc.calculate_periodic_deterministic_costs(
            small_schedule_df,
            battery_file=BATTERIES_PATH,
            period="month",
        )

        assert len(result) >= 1
        assert "total_cost" in result.columns

    def test_invalid_period_raises(
        self,
        small_schedule_df: pd.DataFrame,
        dt_hours: float,
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        with pytest.raises(ValueError, match="period must be either"):
            calc.calculate_periodic_deterministic_costs(
                small_schedule_df,
                battery_file=BATTERIES_PATH,
                period="week",
            )

    def test_real_csv_periodic_costs(
        self,
        real_schedule_df: pd.DataFrame,
        dt_hours: float,
    ):
        calc = OptimizationCostCalculator(dt_hours=dt_hours)
        result = calc.calculate_periodic_deterministic_costs(
            real_schedule_df,
            battery_file=BATTERIES_PATH,
            period="day",
        )

        assert len(result) == 1  # single day in the CSV
        assert result["total_cost"].iloc[0] > 0
