"""
Energy optimization using Pyomo.

This class implements a Mixed-Integer Linear Programming (MILP) optimizer
for multi-battery energy management with PV generation, load, and grid connection.
The MILP formulation allows for modeling binary charge/discharge states and different charge/discharge efficiencies.
"""

import logging
from typing import List, Dict, Any, Optional, Sequence
from pyomo.environ import (
    ConcreteModel,
    Set,
    Var,
    Param,
    Objective,
    Constraint,
    Binary,
    NonNegativeReals,
    minimize,
    value,
)

from esms.models import Battery
from .base_optimizer import BaseEnergyOptimizer

logger = logging.getLogger(__name__)


class EnergyOptimizer(BaseEnergyOptimizer):
    """
    Energy optimizer using MILP.

    Optimizes battery charging/discharging and grid interaction
    to minimize total energy cost while satisfying load and constraints.
    """

    def __init__(
        self,
        batteries: List[Battery],
        load_forecast,
        pv_forecast,
        import_price_forecast,
        export_price_forecast: Optional[Sequence[float]] = None,
        timestep_hours: float = 1.0,
    ):
        """
        Initialize the optimizer.

        Args:
            batteries: List of Battery objects
            load_forecast: Load demand forecast (kW) for each timestep
            pv_forecast: PV generation forecast (kW) for each timestep
            import_price_forecast: Electricity import price forecast (EUR/kWh) for each timestep
            export_price_forecast: Electricity export price forecast (EUR/kWh) for each timestep
            timestep_hours: Duration of each timestep in hours (default: 1.0)
            solver: Solver to use ('glpk', 'cbc', 'gurobi', etc.)
        """
        super().__init__(
            batteries=batteries,
            load_forecast=load_forecast,
            pv_forecast=pv_forecast,
            import_price_forecast=import_price_forecast,
            export_price_forecast=export_price_forecast,
            timestep_hours=timestep_hours,
        )

    def build_model(
            self, 
            grid_import_values=None,
            grid_export_values=None,
            charge_values=None,
            discharge_values=None,
        ) -> ConcreteModel:
        """
        Build the Pyomo optimization model.

        Returns:
            Pyomo ConcreteModel
        """
        logger.info("Building optimization model...")

        model = ConcreteModel()

        # Sets
        n_timesteps = len(self.pv_forecast)
        model.T = Set(initialize=range(n_timesteps), doc="Timesteps")
        model.B = Set(initialize=range(len(self.batteries)), doc="Batteries")

        # Parameters
        model.Load = Param(
            model.T, initialize={t: self.load_forecast[t] for t in model.T}
        )
        model.PV = Param(model.T, initialize={t: self.pv_forecast[t] for t in model.T})
        model.ImportPrice = Param(
            model.T, initialize={t: self.import_price_forecast[t] for t in model.T}
        )
        model.ExportPrice = Param(
            model.T, initialize={t: self.export_price_forecast[t] for t in model.T}
        )
        model.dt = Param(initialize=self.timestep_hours)

        # Battery parameters
        def init_capacity(model, b):
            return self.batteries[b].capacity

        model.Capacity = Param(model.B, initialize=init_capacity)

        def init_max_charge(model, b):
            return self.batteries[b].max_charge

        model.MaxCharge = Param(model.B, initialize=init_max_charge)

        def init_max_discharge(model, b):
            return self.batteries[b].max_discharge

        model.MaxDischarge = Param(model.B, initialize=init_max_discharge)

        def init_charge_eff(model, b):
            return self.batteries[b].charge_efficiency

        model.ChargeEff = Param(model.B, initialize=init_charge_eff)

        def init_discharge_eff(model, b):
            return self.batteries[b].discharge_efficiency

        model.DischargeEff = Param(model.B, initialize=init_discharge_eff)

        def init_initial_soc(model, b):
            return self.batteries[b].initial_soc

        model.InitialSOC = Param(model.B, initialize=init_initial_soc)

        def init_min_soc(model, b):
            return self.batteries[b].min_soc

        model.MinSOC = Param(model.B, initialize=init_min_soc)

        def init_max_soc(model, b):
            return self.batteries[b].max_soc

        model.MaxSOC = Param(model.B, initialize=init_max_soc)

        def init_deg_cost(model, b):
            return self.batteries[b].degradation_cost

        model.DegCost = Param(model.B, initialize=init_deg_cost)

        # Decision Variables
        model.charge = Var(
            model.B, model.T, domain=NonNegativeReals, doc="Battery charge power (kW)"
        )
        model.discharge = Var(
            model.B,
            model.T,
            domain=NonNegativeReals,
            doc="Battery discharge power (kW)",
        )
        model.soc = Var(
            model.B, model.T, domain=NonNegativeReals, doc="State of charge (kWh)"
        )
        model.grid_import = Var(
            model.T, domain=NonNegativeReals, doc="Grid import power (kW)"
        )
        model.grid_export = Var(
            model.T, domain=NonNegativeReals, doc="Grid export power (kW)"
        )
        # Fix variables if values are provided (for warm-starting or policy evaluation)
        if grid_import_values is not None:
            for t in model.T:
                model.grid_import[t].fix(grid_import_values[t])
        if grid_export_values is not None:
            for t in model.T:
                model.grid_export[t].fix(grid_export_values[t])
        if charge_values is not None:
            for b in model.B:
                for t in model.T:
                    model.charge[b, t].fix(charge_values[b][t])
        if discharge_values is not None:
            for b in model.B:
                for t in model.T:
                    model.discharge[b, t].fix(discharge_values[b][t])

        # Binary variable for charge/discharge state (MILP constraint)
        model.u = Var(
            model.B,
            model.T,
            domain=Binary,
            doc="Charge state binary (1=can charge, 0=can discharge)",
        )

        model.v = Var(
            model.T,
            domain=Binary,
            doc="Grid interaction binary (1=can import, 0=can export)",
        )

        # Objective: Minimize total cost
        def objective_rule(model):
            return sum(
                (
                    model.grid_import[t] * model.ImportPrice[t]
                    - model.grid_export[t] * model.ExportPrice[t]
                )
                * model.dt
                + sum(
                    model.DegCost[b] * (model.charge[b, t] + model.discharge[b, t])
                    * model.dt
                    for b in model.B
                )
                for t in model.T
            )

        model.total_cost = Objective(rule=objective_rule, sense=minimize)

        # Constraints

        # 1. Energy balance at each timestep
        def energy_balance_rule(model, t):
            total_discharge = sum(model.discharge[b, t] for b in model.B)
            total_charge = sum(model.charge[b, t] for b in model.B)
            return (
                model.Load[t]
                == model.PV[t]
                + total_discharge
                + model.grid_import[t]
                - total_charge
                - model.grid_export[t]
            )

        model.energy_balance = Constraint(model.T, rule=energy_balance_rule)

        # 2. SOC dynamics for each battery
        def soc_dynamics_rule(model, b, t):
            if t == 0:
                # Initial SOC
                return model.soc[b, t] == (
                    model.InitialSOC[b]
                    + model.ChargeEff[b] * model.charge[b, t] * model.dt
                    - model.discharge[b, t] * model.dt / model.DischargeEff[b]
                )
            else:
                # SOC evolution
                return model.soc[b, t] == (
                    model.soc[b, t - 1]
                    + model.ChargeEff[b] * model.charge[b, t] * model.dt
                    - model.discharge[b, t] * model.dt / model.DischargeEff[b]
                )

        model.soc_dynamics = Constraint(model.B, model.T, rule=soc_dynamics_rule)

        # 3. SOC limits
        def soc_min_rule(model, b, t):
            return model.soc[b, t] >= model.MinSOC[b]

        model.soc_min = Constraint(model.B, model.T, rule=soc_min_rule)

        def soc_max_rule(model, b, t):
            return model.soc[b, t] <= model.MaxSOC[b]

        model.soc_max = Constraint(model.B, model.T, rule=soc_max_rule)

        # 4. Power limits with binary constraint (no simultaneous charge/discharge)
        def charge_limit_rule(model, b, t):
            return model.charge[b, t] <= model.MaxCharge[b] * model.u[b, t]

        model.charge_limit = Constraint(model.B, model.T, rule=charge_limit_rule)

        def discharge_limit_rule(model, b, t):
            return model.discharge[b, t] <= model.MaxDischarge[b] * (1 - model.u[b, t])

        model.discharge_limit = Constraint(model.B, model.T, rule=discharge_limit_rule)

        # 5. Grid interaction limits with binary constraint (no simultaneous import/export)
        def grid_import_limit_rule(model, t):
            return model.grid_import[t] <= 1e6 * model.v[t]  # Large constant

        def grid_export_limit_rule(model, t):
            return model.grid_export[t] <= 1e6 * (1 - model.v[t])  # Large constant

        model.grid_import_limit = Constraint(model.T, rule=grid_import_limit_rule)
        model.grid_export_limit = Constraint(model.T, rule=grid_export_limit_rule)

        self.model = model
        logger.info(
            f"Model built with {len(model.T)} timesteps and {len(model.B)} batteries"
        )

        return model

    def _extract_results(self) -> Dict[str, Any]:
        """Extract results from solved model."""
        model = self.model

        # Extract battery schedules
        battery_schedules = []
        for b in model.B:
            schedule = {
                "id": self.batteries[b].id,
                "charge": [value(model.charge[b, t]) for t in model.T],
                "discharge": [value(model.discharge[b, t]) for t in model.T],
                "soc": [value(model.soc[b, t]) for t in model.T],
                "binary_state": [value(model.u[b, t]) for t in model.T],
            }
            battery_schedules.append(schedule)

        # Extract grid schedule
        grid_import = [value(model.grid_import[t]) for t in model.T]
        grid_export = [value(model.grid_export[t]) for t in model.T]

        # Calculate total cost
        total_cost = value(model.total_cost)

        results = {
            "batteries": battery_schedules,
            "grid_import": grid_import,
            "grid_export": grid_export,
            "total_cost": total_cost,
            "solver_status": str(self.results.solver.termination_condition),
            "objective_value": total_cost,
        }

        logger.info(f"Total cost: {total_cost:.2f} EUR")

        return results

    def _add_battery_dataframe_columns(
        self, data: Dict[str, Any], results: Dict[str, Any]
    ) -> None:
        """Add battery-specific columns for the MILP model."""
        for b_result in results["batteries"]:
            b_id = b_result["id"]
            data[f"{b_id}_charge"] = b_result["charge"]
            data[f"{b_id}_discharge"] = b_result["discharge"]
            data[f"{b_id}_soc"] = b_result["soc"]
