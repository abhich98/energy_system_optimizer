REST API for household day-ahead battery scheduling built on top of `esms`.

Production base URL: `https://esms-chft.onrender.com`
Local base URL: `http://localhost:8000`

## Deterministic vs stochastic API: purpose and methodology

- **Deterministic API** (`/dayahead/deterministic`): use this when you have one best estimate for tomorrow (`pv`, `load`, `import_price`) and want a schedule based on that single forecast.
- **Stochastic API** (`/dayahead/stochastic`): use this when tomorrow is uncertain. It combines recent `pv/load` history, next-day prices, and a champion policy (optionally overridden) to produce an expected schedule that is usually more robust.
- **Quick rule of thumb**:
  - choose deterministic for a single trusted forecast;
  - choose stochastic when uncertainty is significant and you want robustness.

## Local development
Run locally with Docker:

```bash
docker compose up -d
curl -s http://localhost:8000/health | jq
```

Open docs:

```bash
xdg-open http://localhost:8000/docs
```

## 📡 Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Service, solver, and champion-policy status |
| `/dayahead/deterministic` | POST | Deterministic day-ahead scheduling (JSON body) |
| `/dayahead/deterministic/upload` | POST | Deterministic scheduling from uploaded files (CSV output) |
| `/dayahead/stochastic` | POST | Stochastic day-ahead scheduling (JSON body) |
| `/dayahead/stochastic/upload` | POST | Stochastic scheduling from uploaded files (CSV output) |
| `/docs` | GET | Interactive OpenAPI docs |

### Recommended usage pattern

- Use JSON-body endpoints for programmatic clients and automation code.
- Use upload endpoints for CLI/file-based workflows (`curl -F ... @file`).

## Request contracts

### 1) POST `/dayahead/deterministic` (JSON)

Body fields:
- `batteries` (array of battery objects)
- `forecasts_csv` (string; CSV text)
- `timestep_hours` (optional float)

`forecasts_csv` must include columns:
- `pv`, `load`, `import_price`
- optional `Date` (if missing, pass `timestep_hours`)

Example:

```python
import requests

base_url = "https://esms-chft.onrender.com"
payload = {
  "batteries": [
    {
      "id": "battery_1",
      "capacity": 10.0,
      "max_charge": 5.0,
      "max_discharge": 5.0,
      "charge_efficiency": 0.95,
      "discharge_efficiency": 0.95,
      "initial_soc": 5.0,
    }
  ],
  "forecasts_csv": "Date,pv,load,import_price\n2026-01-01 00:00:00,0.0,1.5,0.18\n",
  "timestep_hours": 0.25,
}

response = requests.post(f"{base_url}/dayahead/deterministic", json=payload, timeout=120)
response.raise_for_status()
print(response.json())
```

Response: JSON object with column arrays (schedule table by columns).

### 2) POST `/dayahead/deterministic/upload` (multipart)

Form parts:
- `batteries_json` (JSON file)
- `forecasts_csv` (CSV file)
- `timestep_hours` (optional float)

Example:

```bash
curl -X POST https://esms-chft.onrender.com/dayahead/deterministic/upload \
  -F "batteries_json=@resources/api/batteries.json" \
  -F "forecasts_csv=@resources/api/forecasts.csv" \
  -F "timestep_hours=0.25" \
  -o dayahead_deterministic_schedule.csv
```

Response: downloadable CSV file.

### 3) POST `/dayahead/stochastic` (JSON)

Body fields:
- `batteries` (array of battery objects)
- `history_csv` (string; CSV text)
- `ahead_prices_csv` (string; CSV text)
- `policy_override` (optional object)
- `timestep_hours` (optional float)

Required CSV columns:
- `history_csv`: `pv`, `load` (+ optional `Date`)
- `ahead_prices_csv`: `import_price` (+ optional `Date`)

If `Date` exists in both CSVs, timesteps must match and history must end before ahead period.
If `Date` is missing, pass `timestep_hours`.

Example:

```python
import requests

base_url = "https://esms-chft.onrender.com"
payload = {
  "batteries": [
    {
      "id": "battery_1",
      "capacity": 10.0,
      "max_charge": 5.0,
      "max_discharge": 5.0,
      "charge_efficiency": 0.95,
      "discharge_efficiency": 0.95,
      "initial_soc": 5.0,
    }
  ],
  "history_csv": "Date,pv,load\n2025-12-31 00:00:00,0.0,1.2\n",
  "ahead_prices_csv": "Date,import_price\n2026-01-01 00:00:00,0.18\n",
  "policy_override": {
    "history_days": 3,
    "num_scenarios": 10,
    "pv_coeff": 0.5,
    "load_coeff": 0.5,
    "solver": "scip",
  },
  "timestep_hours": 0.25,
}

response = requests.post(f"{base_url}/dayahead/stochastic", json=payload, timeout=120)
response.raise_for_status()
print(response.json())
```

Response: JSON object with column arrays (schedule table by columns).

### 4) POST `/dayahead/stochastic/upload` (multipart)

Form parts:
- `batteries_json` (JSON file)
- `history_csv` (CSV file)
- `ahead_prices_csv` (CSV file)
- `policy_override_json` (optional JSON file)
- `timestep_hours` (optional float)

Example:

```bash
curl -X POST https://esms-chft.onrender.com/dayahead/stochastic/upload \
  -F "batteries_json=@resources/api/batteries.json" \
  -F "history_csv=@resources/api/history.csv" \
  -F "ahead_prices_csv=@resources/api/ahead_prices.csv" \
  -F "policy_override_json=@resources/api/policy_override.json" \
  -F "timestep_hours=0.25" \
  -o dayahead_stochastic_schedule.csv
```

Response: downloadable CSV file.

## Health response

`GET /health` returns:
- service metadata and version
- `available_solvers`
- `champion_policy.exists`
- overall status (`Healthy`, `Degraded`, or `Unhealthy`)

## Error handling

- `400`: validation or scheduling failure
- `503`: champion policy missing (stochastic endpoint)
- `500`: unexpected health-check failure

## Notes

- Stochastic endpoint requires a valid champion policy file on the server.
- Ensure all uploaded/text CSVs are UTF-8 encoded.
- Use `/docs` for the latest schema as code evolves.
