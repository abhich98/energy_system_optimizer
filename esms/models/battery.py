"""
Battery Energy Storage System (BESS) model.

Defines the data structure and validation for battery parameters
used in the optimization.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class Battery(BaseModel):
    """
    Represents a Battery Energy Storage System with its operational parameters.

    Attributes:
        id: Unique identifier for the battery
        capacity: Total energy capacity in kWh
        max_charge: Maximum charging power in kW
        max_discharge: Maximum discharging power in kW
        charge_efficiency: Charging efficiency (0 to 1)
        discharge_efficiency: Discharging efficiency (0 to 1)
        initial_soc: Initial state of charge in kWh
        min_soc: Minimum allowed state of charge in kWh (defaults to 0 kWh)
        max_soc: Maximum allowed state of charge in kWh (defaults to capacity)
        degradation_cost: Cost per kWh of battery throughput to account for degradation (EUR/kWh)
    """

    id: str = Field(..., description="Unique battery identifier")
    capacity: float = Field(..., gt=0, description="Total energy capacity (kWh)")
    max_charge: float = Field(..., gt=0, description="Maximum charging power (kW)")
    max_discharge: float = Field(
        ..., gt=0, description="Maximum discharging power (kW)"
    )
    charge_efficiency: float = Field(
        ..., gt=0, le=1, description="Charging efficiency (0-1)"
    )
    discharge_efficiency: float = Field(
        ..., gt=0, le=1, description="Discharging efficiency (0-1)"
    )
    initial_soc: float = Field(..., ge=0, description="Initial state of charge (kWh)")
    min_soc: float = Field(
        default=0.0, ge=0, description="Minimum allowed state of charge (kWh)"
    )
    max_soc: Optional[float] = Field(
        default=None, ge=0, description="Maximum allowed state of charge (kWh)"
    )
    degradation_cost: float = Field(
        ..., ge=0, description="Cost per kWh of battery throughput to account for degradation (EUR/kWh)"
    )

    @field_validator("max_soc")
    @classmethod
    def validate_max_soc(cls, v, info):
        """Set max_soc to capacity if not provided."""
        if v is None and "capacity" in info.data:
            return info.data["capacity"]
        return v

    @model_validator(mode="after")
    def validate_soc_limits(self):
        """Validate SOC limits and initial SOC."""
        if not 0 <= self.min_soc < self.max_soc <= self.capacity:
            raise ValueError(
                f"Battery {self.id}: SOC limits must satisfy "
                f"0 <= min_soc ({self.min_soc}) < max_soc ({self.max_soc}) <= capacity ({self.capacity})"
            )

        if not self.min_soc <= self.initial_soc <= self.max_soc:
            raise ValueError(
                f"Battery {self.id}: initial_soc ({self.initial_soc}) must be "
                f"between min_soc ({self.min_soc}) and max_soc ({self.max_soc})"
            )

        return self

    @model_validator(mode="after")
    def validate_degradation_cost(self):
        """Validate degradation cost."""
        if self.degradation_cost < 0:
            raise ValueError(
                f"Battery {self.id}: degradation_cost must be non-negative"
            )
        return self

    @property
    def round_trip_efficiency(self) -> float:
        """Calculate round-trip efficiency."""
        return self.charge_efficiency * self.discharge_efficiency
