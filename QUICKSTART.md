## Installation
- Supported Python: 3.11 to 3.14
- Recommended environment manager: `uv`

```bash
pip install --no-cache-dir uv
uv sync
```

## Python package (`esms`)

Deterministic ahead schedule:

```python
import numpy as np
from esms.models import Battery
from esms.optimization import EnergyOptimizer

batteries = [
    Battery(
        id="battery_1",
        capacity=10.0,
        max_charge=5.0,
        max_discharge=5.0,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        initial_soc=5.0,
        min_soc=1.0,
        max_soc=10.0,
        degradation_cost=0.04,
    )
]

T = 96
opt = EnergyOptimizer(
    batteries=batteries,
    load_forecast=np.full(T, 1.5),
    pv_forecast=np.zeros(T),
    import_price_forecast=np.linspace(0.10, 0.20, T),
    timestep_hours=0.25,
)
opt.build_model()
res = opt.solve(solver_name="scip", verbose=False)
print(opt.results_to_dataframe(res).head())
```

Stochastic expected schedule from explicit scenarios:

```python
import numpy as np
from esms.optimization import StochasticEnergyOptimizer

S, T = 3, 96
opt = StochasticEnergyOptimizer(
    batteries=batteries,
    load_scenarios=np.full((S, T), 1.5),
    pv_scenarios=np.zeros((S, T)),
    import_price_ahead=np.zeros(T),
    export_price_ahead=np.zeros(T),
    import_price_rt_scenarios=np.tile(np.linspace(0.10, 0.20, T), (S, 1)),
    export_price_rt_scenarios=np.zeros((S, T)),
    scenario_probabilities=np.array([0.4, 0.4, 0.2]),
    timestep_hours=0.25,
)
opt.build_model()
res = opt.solve(solver_name="scip", verbose=False)
print(opt.results_to_dataframe(res).head())
```

## REST API

Base URL (deployed): `https://esms-chft.onrender.com`
Base URL (local): `http://localhost:8000`


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

For complete contract details: [docs/API_README.md](docs/API_README.md)

## Streamlit frontend

Live frontend: `https://esms-house-battery-schedule.streamlit.app/`

Run locally:

```bash
uv sync --group frontend
streamlit run app/main_scheduling.py
```

## Makefile automation

The project includes a Makefile for automating tasks such as frontend deployment (`make app`), injesting and preprocessing data, and running challenge experiments (`make challenge`). 

The Makefile not be only relevant for users interested in development and running household analysis experiments.

## Notes
- Deterministic input CSV must include `pv`, `load`, `import_price`.
- Stochastic history CSV must include `pv`, `load`.
- Stochastic ahead-prices CSV must include `import_price`.
- Include `Date` to infer timestep automatically; otherwise pass `timestep_hours`.