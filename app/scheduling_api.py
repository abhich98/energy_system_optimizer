from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import requests
from scheduling_config import API_BASE, DETERM_ENDPOINT, STOCH_ENDPOINT

from household_battery.api.models import (
    ChampionPolicy,
    DeterministicRequest,
    StochasticRequest,
)


LOCAL_TESTING = False  # Set to True for local testing without API calls
if LOCAL_TESTING:
    from fastapi.testclient import TestClient

    from household_battery.api.main import app

    requests = TestClient(app)  # type: ignore
    API_BASE = ""
    DETERM_ENDPOINT = f"{API_BASE}/dayahead/deterministic"
    STOCH_ENDPOINT = f"{API_BASE}/dayahead/stochastic"


def get_available_solvers() -> list[str]:
    try:
        response = requests.get(f"{API_BASE}/health", timeout=15)
        response.raise_for_status()
        payload = response.json()
        solvers = payload.get("available_solvers", [])
        if isinstance(solvers, list):
            return [str(solver) for solver in solvers if str(solver).strip()]
    except Exception:
        pass
    return []


def is_champion_healthy() -> bool:
    try:
        response = requests.get(f"{API_BASE}/health", timeout=15)
        return response.json().get("champion_policy", {}).get("exists", False)
    except Exception:
        return False


def call_deterministic_api(
    batteries: list[dict[str, Any]],
    forecasts_df: pd.DataFrame,
    timestep_hours: Optional[float],
) -> pd.DataFrame:
    request_model = DeterministicRequest(
        batteries=batteries,
        forecasts_csv=forecasts_df.to_csv(index=False),
        timestep_hours=timestep_hours,
    )
    payload = request_model.model_dump(exclude_none=True)
    response = requests.post(DETERM_ENDPOINT, json=payload, timeout=300)
    if response.status_code != 200:
        raise RuntimeError(f"API error {response.status_code}: {response.text}")

    schedule = pd.DataFrame(response.json())
    schedule["Date"] = pd.to_datetime(schedule["Date"])
    schedule.set_index("Date", inplace=True)
    return schedule


def call_stochastic_api(
    batteries: list[dict[str, Any]],
    history_df: pd.DataFrame,
    ahead_df: pd.DataFrame,
    policy_override: Optional[dict[str, Any]],
    timestep_hours: Optional[float],
) -> pd.DataFrame:
    override_model = ChampionPolicy(**policy_override) if policy_override else None
    request_model = StochasticRequest(
        batteries=batteries,
        history_csv=history_df.to_csv(index=False),
        ahead_prices_csv=ahead_df.to_csv(index=False),
        policy_override=override_model,
        timestep_hours=timestep_hours,
    )
    payload = request_model.model_dump(exclude_none=True)
    response = requests.post(STOCH_ENDPOINT, json=payload, timeout=300)
    if response.status_code != 200:
        raise RuntimeError(f"API error {response.status_code}: {response.text}")

    schedule = pd.DataFrame(response.json())
    schedule["Date"] = pd.to_datetime(schedule["Date"])
    schedule.set_index("Date", inplace=True)
    return schedule
