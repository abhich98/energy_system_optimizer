"""Optimization service for orchestrating optimizer calls."""

import logging
from typing import List, Dict, Any
import pandas as pd
import numpy as np

from esms.models import Battery
from esms.optimization import EnergyOptimizer, StochasticEnergyOptimizer
from esms.api.schemas import SolverConfig

logger = logging.getLogger(__name__)


class OptimizationService:
    """Service for running energy optimization."""

    @staticmethod
    def _solver_kwargs(config: SolverConfig) -> Dict[str, Any]:
        solver_kwargs: Dict[str, Any] = {}
        if config.solver == "scip":
            solver_kwargs["solver_io"] = "nl"
        return solver_kwargs

    @staticmethod
    def optimize(
        batteries: List[Battery],
        forecasts: Dict[str, Any],
        fix_decision_vars: Dict[str, Any],
        config: SolverConfig,
    ) -> pd.DataFrame:
        """
        Run energy optimization.

        Args:
            batteries: List of Battery objects
            forecasts: Dictionary with pv, load, import_price, export_price arrays
            fix_decision_vars: Dictionary with decision variables to fix during optimization
            config: Solver configuration

        Returns:
            DataFrame with optimization results

        Raises:
            RuntimeError: If optimization fails
        """
        logger.info(f"Starting optimization with {config.solver}")
        logger.info(f"Number of batteries: {len(batteries)}")
        logger.info(f"Number of timesteps: {len(forecasts['pv'])}")

        try:
            # Initialize optimizer
            optimizer = EnergyOptimizer(
                batteries=batteries,
                load_forecast=forecasts["load"],
                pv_forecast=forecasts["pv"],
                import_price_forecast=forecasts["import_price"],
                export_price_forecast=forecasts["export_price"],
                timestep_hours=config.timestep_hours,
            )

            optimizer.build_model(**fix_decision_vars)

            # Run optimization
            results = optimizer.solve(
                solver_name=config.solver, verbose=config.verbose, **config.opts
            )

            # Convert to DataFrame
            results_df = optimizer.results_to_dataframe(results)

            logger.info(f"Optimization completed successfully")
            logger.info(f"Total cost: {results['total_cost']:.2f} EUR")
            logger.info(f"Solver status: {results['solver_status']}")

            return results_df

        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            raise RuntimeError(f"Optimization failed: {e}")

    @staticmethod
    def optimize_stochastic(
        batteries: List[Battery],
        scenarios: Dict[str, Any],
        ahead_prices: Dict[str, Any],
        schedule_bess: bool,
        config: SolverConfig,
    ) -> pd.DataFrame:
        """Run stochastic optimization using explicit scenario inputs."""
        logger.info("Starting stochastic optimization with %s", config.solver)
        logger.info("Number of batteries: %s", len(batteries))
        logger.info(
            "Scenarios: %s | Timesteps: %s",
            scenarios["load_scenarios"].shape[0],
            scenarios["load_scenarios"].shape[1],
        )

        try:
            # solver_kwargs = OptimizationService._solver_kwargs(config)

            optimizer = StochasticEnergyOptimizer(
                batteries=batteries,
                load_scenarios=scenarios["load_scenarios"],
                pv_scenarios=scenarios["pv_scenarios"],
                import_price_ahead=ahead_prices["import_price_ahead"],
                export_price_ahead=ahead_prices["export_price_ahead"],
                import_price_rt_scenarios=scenarios["import_price_rt_scenarios"],
                export_price_rt_scenarios=scenarios["export_price_rt_scenarios"],
                scenario_probabilities=scenarios["scenario_probabilities"],
                timestep_hours=config.timestep_hours,
            )

            if schedule_bess:
                # Only implementing a special case for now where we assume ahead prices are zero and battery exchange recourse is not allowed.
                optimizer.build_model(
                    grid_import_ahead_values=np.zeros_like(
                        ahead_prices["import_price_ahead"]
                    ),
                    grid_export_ahead_values=np.zeros_like(
                        ahead_prices["export_price_ahead"]
                    ),
                    charge_realtime_values=np.zeros_like(
                        (
                            len(batteries),
                            scenarios["load_scenarios"].shape[0],
                            scenarios["load_scenarios"].shape[1],
                        )
                    ),
                    discharge_realtime_values=np.zeros_like(
                        (
                            len(batteries),
                            scenarios["load_scenarios"].shape[0],
                            scenarios["load_scenarios"].shape[1],
                        )
                    ),
                )

            results = optimizer.solve(
                solver_name=config.solver,
                verbose=config.verbose,
                **config.opts,
            )

            results_df = optimizer.results_to_dataframe(results)
            timestamps = scenarios.get("timestamps")
            if timestamps is not None:
                results_df.index = pd.DatetimeIndex(timestamps)
                results_df.index.name = "Date"

            logger.info("Stochastic optimization completed successfully")
            logger.info("Expected total cost: %.2f EUR", results["total_cost"])
            logger.info("Solver status: %s", results["solver_status"])

            return results_df

        except Exception as e:
            logger.error(f"Stochastic optimization failed: {e}")
            raise RuntimeError(f"Stochastic optimization failed: {e}")
