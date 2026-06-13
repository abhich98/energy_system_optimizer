REST API for day-ahead or long-term energy optimization with multi-battery systems, PV generation, and grid interaction.

## 🚀 Quick Start

### Using Docker (Recommended)

```bash
# Build and start the API
docker-compose up -d

# Check health
curl http://localhost:8000/health

# View API documentation
open http://localhost:8000/docs
```

### Local Development

```bash
# Install dependencies
uv sync

# Run API server
uvicorn esms.api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📡 API Usage

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/optimize` | POST | Run energy optimization |
| `/stochastic-optimize` | POST | Run stochastic optimization from explicit scenarios |
| `/docs` | GET | Interactive API documentation |

### Optimization Request

**Required Files:**
1. `batteries.json` - Battery configuration
2. `forecasts.csv` - Time series forecasts
3. `fix_decision_vars.csv` (optional) - Fix certain decision variables during optimization
4. `config.json` - Solver configuration (optional)

#### Example Request

```bash
curl -X POST http://localhost:8000/optimize \
  -F "batteries_json=@batteries.json" \
  -F "forecasts_csv=@forecasts.csv" \
  -F "fix_decision_vars_csv=@fix_decision_vars.csv" \
  -F "config_json=@config.json" \
  -o schedule.csv
```

#### Using Python

```python
import requests

files = {
    'batteries_json': open('batteries.json', 'rb'),
    'forecasts_csv': open('forecasts.csv', 'rb'),
    'fix_decision_vars_csv': open('fix_decision_vars.csv', 'rb'),
    'config_json': open('config.json', 'rb')
}

response = requests.post('http://localhost:8000/optimize', files=files)

with open('schedule.csv', 'wb') as f:
    f.write(response.content)
```

### Stochastic Optimization Request

**Required Files:**
1. `batteries.json` - Battery configuration
2. `scenarios.csv` - Explicit scenario inputs
3. `ahead_prices.csv` - Shared ahead prices per timestep
4. `config.json` - Solver configuration (optional)

#### Example Request

```bash
curl -X POST http://localhost:8000/stochastic-optimize \
  -F "batteries_json=@batteries.json" \
  -F "scenarios_csv=@scenarios.csv" \
  -F "ahead_prices_csv=@ahead_prices.csv" \
  -F "config_json=@config.json" \
  -o stochastic_schedule.csv
```

---

## 📄 Input File Formats

### 1. batteries.json

Array of battery configurations:

```json
[
  {
    "id": "battery_1",
    "capacity": 100.0,
    "max_charge": 50.0,
    "max_discharge": 50.0,
    "charge_efficiency": 0.95,
    "discharge_efficiency": 0.95,
    "initial_soc": 50.0,
    "min_soc": 10.0,
    "max_soc": 100.0,
    "degradation_cost": 0.04,
  }
]
```

**Fields:**
- `id` (string): Unique battery identifier
- `capacity` (float): Total energy capacity in kWh
- `max_charge` (float): Maximum charging power in kW
- `max_discharge` (float): Maximum discharging power in kW
- `charge_efficiency` (float): Charging efficiency (0-1)
- `discharge_efficiency` (float): Discharging efficiency (0-1)
- `initial_soc` (float): Initial state of charge in kWh
- `min_soc` (float, optional): Minimum SOC in kWh (default: 0)
- `max_soc` (float, optional): Maximum SOC in kWh (default: capacity)
- `degradation_cost` (float, optional): Degradation cost per kWh cycled in EUR/kWh (default: 0)

### 2. forecasts.csv

Time series with required columns:

```csv
timestep,pv,load,price,export_price
0,0.0,30.0,0.10,0.08
1,5.0,32.0,0.11,0.08
...
```

**Columns:**

### 3. scenarios.csv

Scenario-wise time series with required columns:

```csv
timestamp,scenario,probability,pv,load,import_price_rt,export_price_rt
2025-01-01 00:00:00,0,0.5,0.0,30.0,0.12,0.00
2025-01-01 00:15:00,0,0.5,0.1,29.5,0.13,0.00
2025-01-01 00:00:00,1,0.5,0.0,31.0,0.11,0.00
...
```

**Columns:**
- `timestamp` or `Date`: Timestep timestamp. Must match across scenarios.
- `scenario`: Scenario identifier.
- `probability`: Scenario probability. Must be constant within each scenario and sum to 1 across scenarios.
- `pv`: PV generation in kW.
- `load`: Load in kW.
- `import_price_rt` or `import_price_realtime`: Real-time import price in EUR/kWh.
- `export_price_rt` or `export_price_realtime` (optional): Real-time export price in EUR/kWh. Defaults to 0.

### 4. ahead_prices.csv

Shared ahead-price time series:

```csv
timestamp,import_price_ahead,export_price_ahead
2025-01-01 00:00:00,0.10,0.00
2025-01-01 00:15:00,0.11,0.00
...
```

**Columns:**
- `timestamp` or `Date`: Timestep timestamp. Must match the scenario timestamps exactly.
- `import_price_ahead`: Ahead import price in EUR/kWh.
- `export_price_ahead` (optional): Ahead export price in EUR/kWh. Defaults to 0.
- `pv` (float): PV generation forecast in kW
- `load` (float): Load demand forecast in kW
- `price` (float): Electricity import price in EUR/kWh
- `export_price` (float, optional): Export price in EUR/kWh

### 3. config.json (Optional)

Solver configuration:

```json
{
  "solver": "scip",
  "timestep_hours": 1.0,
  "verbose": false,
  "opts": {
    "mip_gap": 0.01,
    "time_limit": 60
  }
}
```

**Fields:**
- `solver` (string): Solver name - `scip` (default), `glpk`, `cbc`
- `timestep_hours` (float): Duration of each timestep in hours (default: 1.0)
- `verbose` (bool): Show solver output (default: false)
- `opts` (dict): Additional solver options (e.g., `mip_gap`, `time_limit`)

## 📤 Output Format

Returns CSV with optimization schedule:

```csv
timestep,pv,load,price,export_price,battery_1_battery_power,battery_1_soc,grid_import,grid_export
0,0.0,30.0,0.10,0.08,25.0,75.0,5.0,0.0
1,5.0,32.0,0.11,0.08,-10.0,65.0,37.0,0.0
...
```

**Columns:**
- Input data: `pv`, `load`, `price`, `export_price`
- Per battery: `{battery_id}_battery_power`, `{battery_id}_soc`
  - `battery_power`: Positive = charging, Negative = discharging (kW)
  - `soc`: State of charge (kWh)
- Grid: `grid_import`, `grid_export` (kW)

---

## 🐳 Docker Details

### Included Solvers

- **SCIP 9.2.0** - High-performance academic/non-commercial solver (recommended)
- **GLPK**

### Build Locally

```bash
docker build -t esms-optimizer .
```

### Run Container

```bash
docker run -d \
  -p 8000:8000 \
  --name esms-api \
  esms-optimizer
```

---

## 🧪 Testing

### Example Files

Sample input files are in `examples/api/`:

```bash
cd examples/api
./test_api.sh
```

### Manual Test

```bash
# 1. Health check
curl http://localhost:8000/health

# 2. Run optimization
curl -X POST http://localhost:8000/optimize \
  -F "batteries_json=@examples/api/batteries.json" \
  -F "forecasts_csv=@examples/api/forecasts.csv" \
  -F "config_json=@examples/api/config.json" \
  -o schedule.csv

# 3. View results
head -20 schedule.csv
```
