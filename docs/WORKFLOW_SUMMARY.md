# Modelling Notes

## Problem Statement

This project investigates day-ahead battery dispatch scheduling for a German residential household with rooftop PV generation. The objective is to minimize electricity costs under dynamic tariffs derived from wholesale electricity market prices while accounting for uncertainty in future household demand and PV generation.

---

## Data Sources

The study combines two independent datasets:

* **Household Load and PV Data (2019)**
  German single-family household electricity consumption and heat pump load profiles from:

  Schlemminger, M., Ohrdes, T., Schneider, E. et al. *Dataset on electrical single-family house and heat pump load profiles in Germany*. Scientific Data, 9, 56 (2022).

* **Electricity Prices (2025)**
  German day-ahead spot market prices obtained from SMARD and transformed into synthetic household dynamic tariffs.

The analysis assumes that household consumption and PV generation patterns observed in 2019 remain representative under 2025 market conditions.

---

## Scenario Generation

For each target day (d), uncertainty is represented using historical observations from the previous (N) days (typically 30–90 days).

Each historical day is represented by:

* 24-hour PV generation profile
* 24-hour household load profile

Representative scenarios are generated using **K-medoids clustering**. Distances between daily PV profiles and load profiles are computed separately and combined using user-defined weights. The clustering process produces 3–9 representative scenarios, each associated with a probability based on cluster membership.

Import prices are assumed to be known and identical across all scenarios.

---

## Stochastic Day-Ahead Scheduling

The battery scheduling problem is formulated as a two-stage stochastic optimization problem.

### First-stage decision

The first-stage decision is a single battery charge/discharge schedule that must be shared across all scenarios:

* Battery charging power
* Battery discharging power
* Battery state of charge

These decisions are made before the future PV and load realizations are known.

### Recourse decisions

For each scenario, grid interactions are determined through recourse variables:

* Grid import
* Grid export

The optimizer therefore seeks a battery schedule that performs well across all representative scenarios while minimizing expected operating cost.

---

## Ex-Post Evaluation

After a day-ahead battery schedule has been obtained, its performance is evaluated using the realized PV generation and household load for the target day.

During evaluation:

* The battery schedule is fixed.
* Dynamic tariff information is assumed known.
* Grid imports and exports are computed using the realized conditions.

This provides an estimate of the actual cost incurred by the stochastic policy.

---

## Perfect Foresight Benchmark

A deterministic perfect foresight optimization is solved as a baseline.

The benchmark assumes complete knowledge of:

* Future PV generation
* Future household demand
* Electricity prices

for the entire scheduling horizon.

The resulting cost represents a theoretical lower bound on achievable operating cost.

---

## Performance Assessment

The primary evaluation metric is the cost difference between:

1. **Perfect foresight optimization**
2. **Ex-post evaluated stochastic scheduling policy**

This comparison quantifies the economic impact of uncertainty and provides insight into the effectiveness of the scenario-based scheduling approach.