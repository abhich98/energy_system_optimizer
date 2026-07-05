from __future__ import annotations

import json

import pandas as pd
from fastapi.testclient import TestClient

from household_battery.api.main import app
import household_battery.api.routes as routes


client = TestClient(app)


def _sample_batteries() -> list[dict]:
    with open("config/sonnenBatterie10.json", "r", encoding="utf-8") as file:
        return json.load(file)


def _deterministic_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01 00:00:00", "2026-01-01 01:00:00"]),
            "pv": [0.0, 0.5],
            "load": [1.0, 1.2],
            "import_price": [0.18, 0.20],
            "grid_import": [1.0, 0.7],
        }
    )


def _stochastic_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01 00:00:00", "2026-01-01 01:00:00"]),
            "grid_import": [0.8, 0.6],
            "grid_export": [0.0, 0.0],
        }
    )


def test_dayahead_deterministic_json_returns_schedule(monkeypatch):
    # Patch the run_dayahead_deterministic function to return a predefined DataFrame for testing
    monkeypatch.setattr(routes, "run_dayahead_deterministic", lambda **_: _deterministic_df())

    payload = {
        "batteries": _sample_batteries(),
        "forecasts_csv": "Date,pv,load,import_price\n2026-01-01 00:00:00,0.0,1.0,0.18\n2026-01-01 01:00:00,0.5,1.2,0.20\n",
        "timestep_hours": 1.0,
    }

    response = client.post("/dayahead/deterministic", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert "Date" in body
    assert "grid_import" in body
    assert len(body["Date"]) == 2


def test_dayahead_deterministic_upload_returns_csv(monkeypatch):
    monkeypatch.setattr(routes, "run_dayahead_deterministic", lambda **_: _deterministic_df())

    batteries_json = json.dumps(_sample_batteries())
    forecasts_csv = "Date,pv,load,import_price\n2026-01-01 00:00:00,0.0,1.0,0.18\n2026-01-01 01:00:00,0.5,1.2,0.20\n"

    response = client.post(
        "/dayahead/deterministic/upload",
        files={
            "batteries_json": ("batteries.json", batteries_json, "application/json"),
            "forecasts_csv": ("forecasts.csv", forecasts_csv, "text/csv"),
        },
        data={"timestep_hours": "1.0"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=dayahead_deterministic_schedule.csv" in response.headers["content-disposition"]
    assert "grid_import" in response.text


def test_dayahead_stochastic_json_returns_503_when_champion_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(routes, "CHAMPION_POLICY_PATH", tmp_path / "missing_champion.json")

    payload = {
        "batteries": _sample_batteries(),
        "history_csv": (
            "Date,pv,load\n"
            "2025-12-31 00:00:00,0.0,1.0\n"
            "2025-12-31 01:00:00,0.1,1.1\n"
        ),
        "ahead_prices_csv": (
            "Date,import_price\n"
            "2026-01-01 00:00:00,0.18\n"
            "2026-01-01 01:00:00,0.20\n"
        ),
        "timestep_hours": 1.0,
    }

    response = client.post("/dayahead/stochastic", json=payload)

    assert response.status_code == 503
    assert response.json()["detail"] == "Champion policy is not configured on the server."


def test_dayahead_stochastic_upload_returns_csv(monkeypatch):
    monkeypatch.setattr(routes, "run_dayahead_stochastic", lambda **_: _stochastic_df())

    batteries_json = json.dumps(_sample_batteries())
    history_csv = "Date,pv,load\n2025-12-31 00:00:00,0.0,1.0\n"
    ahead_prices_csv = "Date,import_price\n2026-01-01 00:00:00,0.18\n"
    policy_override_json = json.dumps({"history_days": 3, "num_scenarios": 10})

    response = client.post(
        "/dayahead/stochastic/upload",
        files={
            "batteries_json": ("batteries.json", batteries_json, "application/json"),
            "history_csv": ("history.csv", history_csv, "text/csv"),
            "ahead_prices_csv": ("ahead.csv", ahead_prices_csv, "text/csv"),
            "policy_override_json": (
                "policy_override.json",
                policy_override_json,
                "application/json",
            ),
        },
        data={"timestep_hours": "1.0"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=dayahead_stochastic_schedule.csv" in response.headers["content-disposition"]
    assert "grid_import" in response.text
