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
CHAMPION_POLICY_PATH = ROOT_DIR / "artifacts" / "champion.json"


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


DEFAULT_BATTERY_VALUES_DICT = load_json_file(SAMPLE_SINGLE_BATTERY_PATH)[0]
DEFAULT_SOLVER_OPTS_DICT = {"timestep_hours": 1.0}

OPEN_SOURCE_DATASET_PATH = (
    ROOT_DIR / "data" / "data_household_germany" / "Dataset_v1.2.0.xlsx"
)
OPEN_SOURCE_DATASET_INFO = 'This dataset comes from the paper "Dataset on electrical single-family house and heat pump load profiles in Germany" (https://doi.org/10.1038/s41597-022-01156-1)'

OPEN_SOURCE_SHEET = 0
OPEN_SOURCE_DATE_COL = "Date"
OPEN_SOURCE_PV_COL = "PV generation (kW)"
OPEN_SOURCE_LOAD_COL = "Consumption (kW)"
OPEN_SOURCE_PRICE_COL = "Energy price (EUR/kWh)"

OPEN_SOURCE_START_MONTH = 4
OPEN_SOURCE_END_MONTH = 12

# Color palette for dark blue background
CHART_COLORS = {
    "pv": "#f59e0b",  # amber
    "load": "#22d3ee",  # cyan
    "price": "#a855f7",  # purple
    "export_price": "#94a3b8",  # slate
    "charge": "#34d399",  # emerald
    "discharge": "#fb7185",  # rose
    "soc": "#facc15",  # yellow
    "actual": "#60a5fa",  # blue
    "expected": "#f472b6",  # pink
}
