from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]

API_BASE = "http://localhost:8000"
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
