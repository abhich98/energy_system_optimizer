"""
Pytest test to compare optimization results between EsMS and PyPSA.
Tests that both optimizers produce similar objective function values for the same problem.
"""

import pandas as pd
import logging
import json
import pytest

import pypsa

from esms.models import Battery
from esms.optimization import EnergyOptimizer
from esms.utils import get_available_pyomo_solvers

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def optimize_with_pypsa(pv_mw, load_mw, price_eur_per_mwh, battery_config, hours):
    """
    Run optimization using PyPSA with proper unit conversions.

    Args:
        pv_mw: PV generation in MW
        load_mw: Load consumption in MW
        price_eur_per_mwh: Energy price in EUR/MWh
        battery_config: Battery configuration dictionary
        hours: DatetimeIndex for timestamps

    Returns:
        Optimal cost in EUR
    """

    # Create network
    network = pypsa.Network()
    network.set_snapshots(hours)

    # Add single bus
    network.add("Bus", "electricity")

    # Add load
    network.add("Load", "load", bus="electricity", p_set=load_mw)

    # Add PV generator (must-run)
    pv_max = pv_mw.max()
    if pv_max > 0:
        network.add(
            "Generator",
            "pv",
            bus="electricity",
            p_max_pu=pv_mw / pv_max,  # normalize
            p_nom=pv_max,  # peak capacity in MW
            marginal_cost=0,
        )

    # Add grid import (price-based)
    network.add(
        "Generator",
        "grid",
        bus="electricity",
        p_nom_extendable=True,
        marginal_cost=price_eur_per_mwh,
    )

    # Add batteries storage
    for bc in battery_config:
        network.add(
            "StorageUnit",
            bc["id"],
            bus="electricity",
            p_nom=bc["max_charge"],
            max_hours=bc["capacity"] / bc["max_charge"],
            efficiency_store=bc["charge_efficiency"],
            efficiency_dispatch=bc["discharge_efficiency"],
            state_of_charge_initial=bc["initial_soc"],
            state_of_charge_initial_per_period=True,
        )

    # Run optimization
    network.optimize(include_objective_constant=False)

    return network.objective


def optimize_with_esms(
    pv_kw, load_kw, price_eur_per_kwh, battery_config, timestep_hours=1.0
):
    """
    Run optimization using EsMS.

    Args:
        pv_kw: PV generation in kW
        load_kw: Load consumption in kW
        price_eur_per_kwh: Energy price in EUR/kWh
        battery_config: Battery configuration dictionary
        timestep_hours: Timestep duration in hours

    Returns:
        Optimal cost in EUR
    """
    # Create battery instance
    batteries = [Battery(**bc) for bc in battery_config]

    # Get available solver
    available_solvers = get_available_pyomo_solvers()
    solver_to_use = available_solvers[0] if len(available_solvers) else "glpk"
    solver_args = {}
    if solver_to_use == "scip":
        solver_args = {"solver_io": "nl"}

    # Create optimizer
    optimizer = EnergyOptimizer(
        batteries=batteries,
        load_forecast=load_kw,
        pv_forecast=pv_kw,
        import_price_forecast=price_eur_per_kwh,
        timestep_hours=timestep_hours,
    )

    # Solve
    results = optimizer.solve(solver_name=solver_to_use, verbose=False, **solver_args)

    return results["total_cost"]


@pytest.fixture
def test_gecad_data():
    """Load test data for optimization comparison."""
    # Load forecast data
    forecast_df = pd.read_excel(
        "data/data_GECAD_portugal/Dataset.xlsx", sheet_name="2023 data", usecols="A:F", nrows=8762
    )

    # Load battery configuration
    with open("config/sample_BESS.json", "r") as f:
        batteries = json.load(f)

    # Select a specific day for reproducibility
    day_idx = 123
    date = forecast_df.iloc[day_idx * 24]["Date"].date()
    forecast_df_day = forecast_df.iloc[day_idx * 24 : (day_idx + 1) * 24]

    # Adjust battery configuration for the test, to ensure it is consistent between esms and pypsa
    for bc in batteries:
        bc["max_discharge"] = bc["max_charge"]  # Ensure max discharge equals max charge
        bc["min_soc"] = 0.0  # Set min SOC to 0 for both optimizers
        bc["degradation_cost"] = 0.0  # Set degradation cost to 0 for both optimizers

    # Extract forecasts
    pv_forecast = forecast_df_day["PV generation (kW)"].values
    load_forecast = forecast_df_day["Consumption (kW)"].values
    price_forecast_mwh = forecast_df_day["Energy price (EUR/MWh)"].values
    price_forecast_kwh = price_forecast_mwh / 1000.0  # Convert EUR/MWh to EUR/kWh
    hours = pd.DatetimeIndex(forecast_df_day["Date"])

    return {
        "pv_forecast": pv_forecast,
        "load_forecast": load_forecast,
        "price_forecast_mwh": price_forecast_mwh,
        "price_forecast_kwh": price_forecast_kwh,
        "batteries": batteries,
        "hours": hours,
        "date": date,
        "day_idx": day_idx,
    }

@pytest.fixture
def test_germany_data():
    """Load test data for optimization comparison from Germany dataset."""
    # Load forecast data
    data_version = "1.2.0"
    data_year = 2025
    time_res_hrs = 0.25

    forecast_df = pd.read_excel(
        f"data/data_household_germany/Dataset_v{data_version}.xlsx", sheet_name=f"{data_year} data"
    )

    # Load battery configuration
    with open("config/sonnenBatterie10.json", "r") as f:
        batteries = json.load(f)

    # Select a specific day for reproducibility
    day_idx = 123
    date = forecast_df.iloc[day_idx * int(24 / time_res_hrs)]["Date"].date()
    forecast_df_day = forecast_df.iloc[day_idx * int(24 / time_res_hrs) : (day_idx + 1) * int(24 / time_res_hrs)]

    # Extract forecasts
    pv_forecast = forecast_df_day["PV generation (kW)"].values
    load_forecast = forecast_df_day["Consumption (kW)"].values
    price_forecast_mwh = forecast_df_day["Energy price (EUR/MWh)"].values
    price_forecast_kwh = price_forecast_mwh / 1000.0  # Convert EUR/MWh to EUR/kWh
    hours = pd.DatetimeIndex(forecast_df_day["Date"])

    return {
        "pv_forecast": pv_forecast,
        "load_forecast": load_forecast,
        "price_forecast_mwh": price_forecast_mwh,
        "price_forecast_kwh": price_forecast_kwh,
        "batteries": batteries,
        "hours": hours,
        "date": date,
        "day_idx": day_idx,
    }


def test_esms_vs_pypsa_optimization(test_gecad_data):
    """
    Test that EsMS and PyPSA produce similar optimization results.

    Compares the optimal objective function values from both solvers.
    PyPSA works optimally in MW/MWh while EsMS works in kW/kWh, so proper unit
    conversion is applied before comparison.
    """
    logger.info("=" * 40)
    logger.info("Testing EsMS vs PyPSA Optimization Comparison")
    logger.info(f"Selected day: {test_gecad_data['date']} (index {test_gecad_data['day_idx']})")
    logger.info("=" * 40)

    # Run EsMS optimization
    logger.info("Running EsMS optimization...")
    timestep_hours = (test_gecad_data["hours"][1] - test_gecad_data["hours"][0]).total_seconds() / 3600.0
    logger.info(f"Timestep duration: {timestep_hours:.2f} hours")
    esms_cost = optimize_with_esms(
        pv_kw=test_gecad_data["pv_forecast"],
        load_kw=test_gecad_data["load_forecast"],
        price_eur_per_kwh=test_gecad_data["price_forecast_kwh"],
        battery_config=test_gecad_data["batteries"],
        timestep_hours=timestep_hours,
    )
    logger.info(f"EsMS optimal cost: {esms_cost:.2f} EUR")

    # Run PyPSA optimization
    logger.info("Running PyPSA optimization...")
    pypsa_cost = optimize_with_pypsa(
        # Note: PyPSA expects MW and EUR/MWh, so we pass the original data assuming that it in MW while it is in kW.
        pv_mw=test_gecad_data["pv_forecast"],
        load_mw=test_gecad_data["load_forecast"],
        price_eur_per_mwh=test_gecad_data["price_forecast_mwh"],
        battery_config=test_gecad_data["batteries"],
        hours=test_gecad_data["hours"],
    )
    pypsa_cost /= 1000.0  # Correction for passing kW data as MW to PyPSA
    logger.info(f"PyPSA optimal cost: {pypsa_cost:.2f} EUR")

    # Calculate relative difference
    relative_diff = abs(esms_cost - pypsa_cost) / abs(pypsa_cost)
    logger.info(f"Absolute difference: {abs(esms_cost - pypsa_cost):.2f} EUR")
    logger.info(f"Relative difference: {relative_diff * 100:.2f}%")
    logger.info("=" * 60)

    # Assert that costs are close (within 1% relative tolerance)
    # This accounts for potential solver differences and numerical precision
    assert (
        abs(esms_cost - pypsa_cost) < 1.0 or relative_diff < 0.01
    ), f"Optimization results differ significantly: EsMS={esms_cost:.2f} EUR, PyPSA={pypsa_cost:.2f} EUR"


if __name__ == "__main__":
    # Allow running directly for debugging
    pytest.main([__file__, "-v", "-s"])
