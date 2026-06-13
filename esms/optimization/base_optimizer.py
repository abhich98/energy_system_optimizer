"""Shared base class for energy optimizers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Sequence

import numpy as np
import pandas as pd
from pyomo.environ import ConcreteModel, SolverFactory

logger = logging.getLogger(__name__)


class BaseEnergyOptimizer(ABC):
    """
    Base class for energy optimizers.

    Provides common initialization, input validation, solver execution,
    and DataFrame conversion.
    """

    def __init__(
        self,
        batteries,
        load_forecast,
        pv_forecast,
        import_price_forecast,
        export_price_forecast: Optional[Sequence[float]] = None,
        timestep_hours: float = 1.0,
    ):
        self.batteries = batteries
        self.load_forecast = np.array(load_forecast)
        self.pv_forecast = np.array(pv_forecast)
        self.import_price_forecast = np.array(import_price_forecast)
        self.export_price_forecast = (
            np.array(export_price_forecast)
            if export_price_forecast is not None
            else np.zeros_like(import_price_forecast)
        )
        self.timestep_hours = timestep_hours

        # Validate inputs
        self._validate_inputs()

        # Model components
        self.model: Optional[ConcreteModel] = None
        self.results = None

    def _validate_inputs(self) -> None:
        """Validate input dimensions and values."""
        n_timesteps = len(self.load_forecast)

        if len(self.pv_forecast) != n_timesteps:
            raise ValueError("pv_forecast must have same length as load_forecast")

        if len(self.import_price_forecast) != n_timesteps:
            raise ValueError(
                "import_price_forecast must have same length as load_forecast"
            )

        if len(self.export_price_forecast) != n_timesteps:
            raise ValueError(
                "export_price_forecast must have same length as load_forecast"
            )

        if n_timesteps == 0:
            raise ValueError("Forecasts must have at least one timestep")

        if len(self.batteries) == 0:
            raise ValueError("At least one battery must be provided")

        if self.timestep_hours <= 0:
            raise ValueError("timestep_hours must be positive")

    @abstractmethod
    def build_model(self) -> ConcreteModel:
        """Build the Pyomo optimization model."""

    @abstractmethod
    def _extract_results(self) -> Dict[str, Any]:
        """Extract results from solved model."""

    @abstractmethod
    def _add_battery_dataframe_columns(
        self, data: Dict[str, Any], results: Dict[str, Any]
    ) -> None:
        """Add battery-specific columns to the results DataFrame data dict."""

    def solve(
        self, solver_name: str = "glpk", verbose: bool = False, **kwargs
    ) -> Dict[str, Any]:
        """
        Solve the optimization problem.

        Args:
            verbose: Whether to display solver output

        Returns:
            Dictionary containing the optimization results
        """
        if self.model is None:
            self.build_model()

        logger.info(f"Solving with {solver_name}...")

        solver = SolverFactory(solver_name, **kwargs)

        if not solver.available():
            raise RuntimeError(f"Solver '{solver_name}' is not available")

        self.results = solver.solve(self.model, tee=verbose)

        # Check solver status
        from pyomo.opt import SolverStatus, TerminationCondition

        if self.results.solver.status == SolverStatus.ok:
            if (
                self.results.solver.termination_condition
                == TerminationCondition.optimal
            ):
                logger.info("Optimal solution found")
                return self._extract_results()
            if (
                self.results.solver.termination_condition
                == TerminationCondition.feasible
            ):
                logger.warning("Feasible solution found (not proven optimal)")
                return self._extract_results()

        logger.error(f"Solver failed: {self.results.solver.status}")
        logger.error(
            f"Termination condition: {self.results.solver.termination_condition}"
        )

        raise RuntimeError(
            f"Optimization failed: {self.results.solver.status}, "
            f"{self.results.solver.termination_condition}"
        )

    def results_to_dataframe(
        self, results: Optional[Dict[str, Any]] = None
    ) -> pd.DataFrame:
        """
        Convert results to a pandas DataFrame for easy analysis.

        Args:
            results: Results dictionary from solve() (defaults to self.results)

        Returns:
            DataFrame with timestep-indexed results
        """
        if results is None:
            results = self._extract_results()

        if results is None:
            raise ValueError("No results available. Run solve() first.")

        n_timesteps = len(self.import_price_forecast)

        data: Dict[str, Any] = {
            "timestep": range(n_timesteps),
            "pv": self.pv_forecast,
            "load": self.load_forecast,
            "import_price": self.import_price_forecast,
            "export_price": self.export_price_forecast,
            "grid_import": results["grid_import"],
            "grid_export": results["grid_export"],
        }

        self._add_battery_dataframe_columns(data, results)

        df = pd.DataFrame(data)
        df.set_index("timestep", inplace=True)

        return df
