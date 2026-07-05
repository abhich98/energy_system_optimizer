from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]

API_BASE = "https://esms-chft.onrender.com"
DETERM_ENDPOINT = f"{API_BASE}/dayahead/deterministic"
STOCH_ENDPOINT = f"{API_BASE}/dayahead/stochastic"

DETERM_REQUIRED_COLS = ["pv", "load", "import_price"]
HIST_REQUIRED_COLS = ["pv", "load"]
AHEAD_REQUIRED_COLS = ["import_price"]

SAMPLE_SINGLE_BATTERY_PATH = ROOT_DIR / "config" / "sonnenBatterie10.json"


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


DEFAULT_BATTERY_VALUES_DICT = load_json_file(SAMPLE_SINGLE_BATTERY_PATH)[0]
DEFAULT_SOLVER_OPTS_DICT = {"timestep_hours": 1.0}

OPEN_SOURCE_DATASET_PATH = (
    ROOT_DIR / "data" / "data_household_germany" / "Dataset_v1.2.0.xlsx"
)
OPEN_SOURCE_SHEET = 0
OPEN_SOURCE_DATE_COL = "Date"
OPEN_SOURCE_PV_COL = "PV generation (kW)"
OPEN_SOURCE_LOAD_COL = "Consumption (kW)"
OPEN_SOURCE_PRICE_COL = "Energy price (EUR/kWh)"
OPEN_SOURCE_START_MONTH = 4
OPEN_SOURCE_END_MONTH = 12
OPEN_SOURCE_DEFAULT_HISTORY_DAYS = 3
