from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from household_battery.api.main import app


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_API_DIR = ROOT / "examples" / "api"
BATTERIES_PATH = ROOT / "config" / "sonnenBatterie10.json"
HISTORY_PATH = EXAMPLES_API_DIR / "20250325_20250423_german_household.csv"
AHEAD_DAY_PATH = EXAMPLES_API_DIR / "20250424_german_household.csv"

client = TestClient(app)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_batteries() -> list[dict]:
    with BATTERIES_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _ahead_prices_csv_text_from_day_ahead(day_ahead_csv_text: str) -> str:
    day_df = pd.read_csv(io.StringIO(day_ahead_csv_text))
    ahead_df = day_df[["Date", "import_price"]].copy()
    return ahead_df.to_csv(index=False)


def _json_response_to_df(response_json: dict) -> pd.DataFrame:
    df = pd.DataFrame(response_json)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
    return df


def _csv_response_to_df(response_text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(response_text))
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
    return df


def _assert_battery_schedule_match(df_left: pd.DataFrame, df_right: pd.DataFrame) -> None:
    battery_cols = [col for col in df_left.columns if "battery" in col.lower()]
    assert battery_cols, "No battery schedule columns found in response"
    assert set(battery_cols).issubset(df_right.columns)

    for col in battery_cols:
        left = pd.to_numeric(df_left[col], errors="coerce").to_numpy()
        right = pd.to_numeric(df_right[col], errors="coerce").to_numpy()
        assert left.shape == right.shape, f"Mismatched shape for {col}"
        assert np.allclose(left, right, rtol=1e-6, atol=1e-6), f"Mismatch in column {col}"


def test_deterministic_json_and_upload_return_same_battery_schedule():
    batteries = _load_batteries()
    day_ahead_csv_text = _read_text(AHEAD_DAY_PATH)

    json_payload = {
        "batteries": batteries,
        "forecasts_csv": day_ahead_csv_text,
    }
    json_response = client.post("/dayahead/deterministic", json=json_payload)
    assert json_response.status_code == 200, json_response.text
    json_df = _json_response_to_df(json_response.json())

    upload_response = client.post(
        "/dayahead/deterministic/upload",
        files={
            "batteries_json": ("batteries.json", json.dumps(batteries), "application/json"),
            "forecasts_csv": (AHEAD_DAY_PATH.name, day_ahead_csv_text, "text/csv"),
        },
    )
    assert upload_response.status_code == 200, upload_response.text
    upload_df = _csv_response_to_df(upload_response.text)

    _assert_battery_schedule_match(json_df, upload_df)


def test_stochastic_json_and_upload_return_same_battery_schedule_with_override():
    batteries = _load_batteries()
    history_csv_text = _read_text(HISTORY_PATH)
    day_ahead_csv_text = _read_text(AHEAD_DAY_PATH)
    ahead_prices_csv_text = _ahead_prices_csv_text_from_day_ahead(day_ahead_csv_text)

    policy_override = {
        "history_days": 3,
        "num_scenarios": 3,
    }

    json_payload = {
        "batteries": batteries,
        "history_csv": history_csv_text,
        "ahead_prices_csv": ahead_prices_csv_text,
        "policy_override": policy_override,
    }
    json_response = client.post("/dayahead/stochastic", json=json_payload)
    assert json_response.status_code == 200, json_response.text
    json_df = _json_response_to_df(json_response.json())

    upload_response = client.post(
        "/dayahead/stochastic/upload",
        files={
            "batteries_json": ("batteries.json", json.dumps(batteries), "application/json"),
            "history_csv": (HISTORY_PATH.name, history_csv_text, "text/csv"),
            "ahead_prices_csv": ("ahead_prices.csv", ahead_prices_csv_text, "text/csv"),
            "policy_override_json": (
                "policy_override.json",
                json.dumps(policy_override),
                "application/json",
            ),
        },
    )
    assert upload_response.status_code == 200, upload_response.text
    upload_df = _csv_response_to_df(upload_response.text)

    _assert_battery_schedule_match(json_df, upload_df)
