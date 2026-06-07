# 🔋 EsMS - Energy Storage Management System

*Implementation of an energy management system (EMS) for optimizing the operation of a multi-asset entity with PV generation, battery storage, and grid exchange.*

Many countries, including Germany, offer residential customers the option to select flexible dynamic electricity contracts, where tariffs vary over time based on market conditions and supply-demand balance. At the same time, governments have encouraged the adoption of PV systems to increase renewable energy generation and self-consumption. In this context, an EMS can be used to schedule the battery energy storage system (BESS) so as to minimize energy costs by making better use of PV and other renewable generation, while accounting for the cost of importing from and exporting to the grid. The EMS can help reduce peak demand charges by strategically charging and discharging the battery based on the load profile and energy prices.

**A simple EMS generally consists of a forecasting module to predict future load, PV generation, and energy prices, and an optimization module that uses these forecasts to determine the optimal schedule for the battery and grid exchange.** Various powerful machine learning and optimization techniques have been developed to solve the EMS problem.  Below is an example pipeline of a typical EMS implementation:

```
[Historical Data & Real-Time Weather API] 
                 │
                 ▼
[Scenario Generation (GMMs / LSTMs / Markov Processes)]
                 │
                 ▼
[Scenario Reduction (e.g., K-Means or Backward Reduction)]
                 │
                 ▼
★★★★ PROJECT FOCUS [Two-Stage MILP Solver] ★★★★
                 └──► Minimizes: $Cost_{Grid} + Penalty_{Degradation}$
                 │
                 ▼
[Receding Horizon Execution (Apply Step 1, Repeat in 15 mins)]

```

This project mainly focuses on the **optimization module**, along with exploring different forecasting and scenario generation techniques. Here, MILP stands for **Mixed-Integer Linear Programming**, which is a powerful optimization technique that can handle both continuous and discrete decision variables, making it suitable for modeling the EMS problem with its various constraints and objectives.

## Project Objective

The objective of the project is to apply **deterministic optimization** and **scenario-based stochastic optimization** in the context of residential household energy management. This involves:

- ingesting and preprocessing historical data on load, PV generation from open source datasets [[1](https://doi.org/10.5281/zenodo.14918474), [2](https://doi.org/10.1038/s41597-022-01156-1)], and energy prices from SMARD
- comparing different optimization solvers (e.g., GLPK, SCIP) and using them via Pyomo
- implementing a two-stage stochastic optimization to optimize the battery schedule and grid exchange
- evaluating the performance of two-stage stochastic optimization against perfect foresight optimization
- implementing and comparing various machine learning techniques for forecasting and scenario generation

> For practical purposes, this project provides a Dockerized REST API for accessing the optimization service (example for day-ahead scheduling, read [API docs](./docs/API_README.md)).

## 🔧 Development and Analysis
### Python and libraries

The project is developed in Python, using libraries such as Pyomo for optimization modeling, FastAPI for web API development, and pandas for data manipulation. The project is structured in a modular way, with separate directories for optimization engines, models, API, and services.

`uv` is used to manage the virtual environment and dependencies.
Install `uv` with `pip` and then sync the environment with the dependencies specified in `pyproject.toml`:
```bash
> pip install --no-cache-dir uv
# cd to the project directory
> uv sync
```

[`Make`](./Makefile) is used to automate the data generation and analysis process, ensuring that the results are reproducible and can be easily updated when new data or parameters are available.

### Project Structure

```
esms/
├── optimization/      # Optimization engines
│   ├── base_optimizer.py
│   ├── optimizer.py       # Deterministic optimization
│   └── stochastic_optimizer.py    # Stochastic optimization and evaluation
├── models/            
|   └── battery.py   # Battery model with SOC and efficiency
├── api/                # FastAPI application
│   ├── main.py        # App initialization
│   ├── routes.py      # Endpoints
│   └── schemas.py     # Pydantic models
├── services/          # Business logic
│   ├── io_service.py
│   └── optimization_service.py
|── utils.py            # Utility functions
```
```
scripts/             # Data processing and analysis scripts
├── deterministic_optimization.py
├── stochastic_optimization.py
├── stochastic_policy_evaluation.py
├── rt_price_generation.py

data/
├── Dataset.xlsx     # Original dataset
├── generated/       # Generated real-time prices and optimization results

```
###  Data Source

The data used in this project comes from:
- Tayenne, L., Bruno, R., Pedro, F., Luis, G., & Zita, V. (2025). Dataset for daily energy management: Renewable generation, consumption, and storage (v1.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.14918474


To find more about the data, please refer to the [Data](./data/data_GECAD_portugal/README.md) document.


### Analysis Workflow
![](data_analysis_workflow.png)

- For a given day, the scenarios are generated by clustering the data from the same season (K-medoid clustering). This data is/was already available in the original dataset.

- The stochastic optimization aims to minimize the expected cost considering the uncertainty in real-time prices, and its performance is evaluated against the perfect foresight optimization to assess its effectiveness.

**Note**: The infographic is generated with ChatGPT. While the general workflow is correct, some details may be inaccurate. See the [scripts](./scripts/), [docs](./docs/) and the [make](./Makefile) file for the exact logic and data used in each step.


### MILP (Mixed-Integer Linear Programming)
_Pyomo_ is used for modeling the optimization problems, and different solvers depending on the size and complexity of the problem. The solvers need to be installed separately, read the corresponding documentation for installation instructions.
- [**GLPK**](https://www.gnu.org/software/glpk/): For small to medium-sized problems (e.g., deterministic optimization, stochastic optimization with a small number of scenarios, over days or weeks).
- [**SCIP**](https://scipopt.org/): For larger problems (e.g., stochastic optimization with a large number of scenarios, or when integer variables are involved, over months or longer).

## Results and Visualization
The cost incurred by the different optimization approaches is compared i.e. the cost of the perfect foresight optimization vs the cost of the stochastic optimization and its evaluation.
- When compared day to day, the cost of the perfect foresight optimization can be higher or lower than the stochastic optimization, depending on how well the scenarios capture the uncertainty and how the real-time prices evolve. However, when looking at the cumulative cost over a longer period (e.g., a year), the perfect foresight optimization should ideally have the lowest cost, as observed in the results, as it has complete information about the future.
- Using more scenenarios in the stochastic optimization generally leads to better performance (lower cost) as it captures a wider range of possible future outcomes, but it also increases computational complexity. **The results show that using 9 scenarios leads to a lower cost compared to using 3 scenarios.**

Based on one year data, where the optimization is performed day by day, with the assumed real-time price generation and example BESS parameters, the results are as follows:
| Optimization Approach | Total Cost (EUR) | Difference from Perfect Foresight (%) |
|-----------------------|------------------|---------------------------------------|
| Perfect Foresight     | €1,504,581.45 | 0.00% |
| Policy from Stochastic Optimization (3 scenarios) | €1,516,503.66 | +0.79% |
| Policy from Stochastic Optimization (9 scenarios) | €1,512,793.09 | +0.54% |


**Note:** The actual costs and differences may vary based on the specific data, parameters, and assumptions used in the optimization. The above values may differ slights with each run due to the noise simulation while generating real-time energy prices.

### Web App for Visualization
A web application is developed using [`Streamlit`](https://streamlit.io/) to visualize the results and compare the costs incurred by the different optimization approaches. The app allows users to select different time periods (e.g., start and end dates) and compare the costs incurred.

![](./screenshot_results_explorer.png)

To run the web app, use:
```bash
> make app
```
This could take a while to start on the first run, as it also generates the data if not already available. Once the app is running, you can access it at `http://localhost:8501/` in your web browser.