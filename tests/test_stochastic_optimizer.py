"""
Test script for stochastic optimizer.

"""

import logging

import numpy as np
import pytest

from esms.models import Battery
from esms.optimization import StochasticEnergyOptimizer
from esms.utils import get_available_pyomo_solvers

from test_deterministic_optimizer import test_germany_data, optimize_with_esms

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def optimize_with_stochastic_esms(
    pv_kw,
    load_kw,
    price_eur_per_kwh,
    battery_config,
    timestep_hours=1.0,
):
    """Run the stochastic optimizer in deterministic-equivalent mode.

    Uses a single scenario with probability 1.0 and sets the real-time prices
    equal to the day-ahead prices. Under this setup, the stochastic formulation
    should reduce to the deterministic one.
    """
    batteries = [Battery(**bc) for bc in battery_config]

    available_solvers = get_available_pyomo_solvers()
    solver_to_use = available_solvers[0] if available_solvers else "glpk"
    solver_args = {}
    if solver_to_use == "scip":
        solver_args = {"solver_io": "nl"}

    load_scenarios = np.asarray(load_kw, dtype=float).reshape(1, -1)
    pv_scenarios = np.asarray(pv_kw, dtype=float).reshape(1, -1)
    price_rt_scenarios = np.asarray(price_eur_per_kwh, dtype=float).reshape(1, -1)

    optimizer = StochasticEnergyOptimizer(
        batteries=batteries,
        load_scenarios=load_scenarios,
        pv_scenarios=pv_scenarios,
        import_price_ahead=price_eur_per_kwh,
        import_price_rt_scenarios=price_rt_scenarios,
        scenario_probabilities=[1.0],
        timestep_hours=timestep_hours,
    )

    results = optimizer.solve(solver_name=solver_to_use, verbose=False, **solver_args)
    return results["total_cost"]


def optimize_with_stochastic_as_recourse_esms(
    pv_kw,
    load_kw,
    price_eur_per_kwh,
    battery_config,
    timestep_hours=1.0,
):
    """Run the stochastic optimizer in deterministic-equivalent mode, but treating day-ahead decisions as recourse/real-time decisions.

    Uses a single scenario with probability 1.0 and sets the real-time prices
    equal to the day-ahead prices. Under this setup, the stochastic formulation
    should reduce to the deterministic one.
    """
    batteries = [Battery(**bc) for bc in battery_config]

    available_solvers = get_available_pyomo_solvers()
    solver_to_use = available_solvers[0] if available_solvers else "glpk"
    solver_args = {}
    if solver_to_use == "scip":
        solver_args = {"solver_io": "nl"}

    load_scenarios = np.asarray(load_kw, dtype=float).reshape(1, -1)
    pv_scenarios = np.asarray(pv_kw, dtype=float).reshape(1, -1)
    price_rt_scenarios = np.asarray(price_eur_per_kwh, dtype=float).reshape(1, -1)

    optimizer = StochasticEnergyOptimizer(
        batteries=batteries,
        load_scenarios=load_scenarios,
        pv_scenarios=pv_scenarios,
        import_price_ahead=np.zeros_like(price_eur_per_kwh),
        import_price_rt_scenarios=price_rt_scenarios,
        scenario_probabilities=[1.0],
        timestep_hours=timestep_hours,
    )

    optimizer.build_model(
        grid_import_ahead_values=np.zeros_like(price_eur_per_kwh),
        grid_export_ahead_values=np.zeros_like(price_eur_per_kwh),
    )

    results = optimizer.solve(solver_name=solver_to_use, verbose=False, **solver_args)
    return results["total_cost"]


def test_deterministic_vs_stochastic_single_scenario(test_germany_data):
    """Test stochastic optimizer collapses to deterministic optimizer.

    With one scenario of probability 1.0 and identical ahead and real-time
    prices, both formulations should produce the same optimal objective value
    up to normal solver tolerances.
    """
    logger.info("=" * 60)
    logger.info("Testing deterministic vs stochastic optimizer equivalence")
    logger.info(
        "Selected day: %s (index %s)",
        test_germany_data["date"],
        test_germany_data["day_idx"],
    )
    logger.info("=" * 60)

    timestep_hours = (test_germany_data["hours"][1] - test_germany_data["hours"][0]).total_seconds() / 3600.0

    logger.info("Running deterministic optimization...")
    deterministic_cost = optimize_with_esms(
        pv_kw=test_germany_data["pv_forecast"],
        load_kw=test_germany_data["load_forecast"],
        price_eur_per_kwh=test_germany_data["price_forecast_kwh"],
        battery_config=test_germany_data["batteries"],
        timestep_hours=timestep_hours,
    )
    logger.info("Deterministic optimal cost: %.6f EUR", deterministic_cost)

    # Calculating the stochastic cost with one scenario should give the same result as the deterministic optimization
    logger.info("Running stochastic optimization with one scenario...")
    stochastic_cost = optimize_with_stochastic_esms(
        pv_kw=test_germany_data["pv_forecast"],
        load_kw=test_germany_data["load_forecast"],
        price_eur_per_kwh=test_germany_data["price_forecast_kwh"],
        battery_config=test_germany_data["batteries"],
        timestep_hours=timestep_hours,
    )
    logger.info("Stochastic optimal cost: %.6f EUR", stochastic_cost)

    absolute_diff = abs(deterministic_cost - stochastic_cost)
    relative_diff = absolute_diff / max(
        abs(deterministic_cost), abs(stochastic_cost), 1e-9
    )

    logger.info("Absolute difference: %.6f EUR", absolute_diff)
    logger.info("Relative difference: %.6f%%", relative_diff * 100.0)
    logger.info("=" * 60)

    assert absolute_diff < 1.0 or relative_diff < 0.01, (
        "Deterministic and stochastic results differ significantly: "
        f"deterministic={deterministic_cost:.6f} EUR, "
        f"stochastic={stochastic_cost:.6f} EUR"
    )

    # Also test the version where day-ahead decisions are treated as recourse/real-time decisions
    stochastic_recourse_cost = optimize_with_stochastic_as_recourse_esms(
        pv_kw=test_germany_data["pv_forecast"],
        load_kw=test_germany_data["load_forecast"],
        price_eur_per_kwh=test_germany_data["price_forecast_kwh"],
        battery_config=test_germany_data["batteries"],
        timestep_hours=timestep_hours,
    )
    logger.info("Stochastic (recourse) optimal cost: %.6f EUR", stochastic_recourse_cost)

    absolute_diff = abs(deterministic_cost - stochastic_recourse_cost)
    relative_diff = absolute_diff / max(
        abs(deterministic_cost), abs(stochastic_recourse_cost), 1e-9
    )

    logger.info("Absolute difference: %.6f EUR", absolute_diff)
    logger.info("Relative difference: %.6f%%", relative_diff * 100.0)
    logger.info("=" * 60)

    assert absolute_diff < 1.0 or relative_diff < 0.01, (
        "Deterministic and stochastic (recourse) results differ significantly: "
        f"deterministic={deterministic_cost:.6f} EUR, "
        f"stochastic (recourse)={stochastic_recourse_cost:.6f} EUR"
    )


if __name__ == "__main__":
    # Allow running directly for debugging
    pytest.main([__file__, "-v", "-s"])
