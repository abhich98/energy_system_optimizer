from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, List

from esms.models.battery import Battery


class DeterministicRequest(BaseModel):
    batteries: List[Battery]
    forecasts_csv: str = Field(..., description="CSV content as text")
    timestep_hours: Optional[float] = None


class ChampionPolicy(BaseModel):
    id: Optional[str] = None
    history_days: Optional[int] = None
    num_scenarios: Optional[int] = None
    pv_coeff: Optional[float] = None
    load_coeff: Optional[float] = None
    solver: Optional[str] = None
    seed: Optional[int] = None


class ChampionRequest(BaseModel):
    batteries: List[Battery]
    history_csv: str = Field(
        ..., description="CSV content with past days of pv/load as text"
    )
    ahead_prices_csv: str = Field(
        ..., description="CSV content with next-day ahead prices as text"
    )
    policy_override: Optional[ChampionPolicy] = None
    timestep_hours: Optional[float] = None
